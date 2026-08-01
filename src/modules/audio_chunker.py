"""
SmartAudioChunker - Pre-Processing Module for Audio Pipeline
=============================================================
Độc lập hoàn toàn, không phụ thuộc thư viện thứ 3 (ngoại trừ FFmpeg/FFprobe trên hệ thống).
Tự động kiểm tra dung lượng, phát hiện khoảng lặng (Silence) bằng FFmpeg Filter,
và chia nhỏ file audio một cách thông minh dưới ngưỡng 19.5 MB.
"""

from dataclasses import dataclass, field
import json
import logging
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


# ==============================================================================
# 1. LOGGING SETUP
# ==============================================================================
def setup_logger(name: str = "SmartAudioChunker") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


logger = setup_logger()


# ==============================================================================
# 2. CUSTOM EXCEPTIONS
# ==============================================================================
class SmartAudioChunkerError(Exception):
    """Ngoại lệ cơ sở cho toàn bộ module SmartAudioChunker."""

    pass


class DependencyNotFoundError(SmartAudioChunkerError):
    """Báo lỗi khi hệ thống thiếu FFmpeg hoặc FFprobe."""

    pass


class AudioFileNotFoundError(SmartAudioChunkerError):
    """Báo lỗi khi không tìm thấy file audio đầu vào."""

    pass


class AudioProbeError(SmartAudioChunkerError):
    """Lỗi xảy ra khi đọc metadata bằng FFprobe."""

    pass


class AudioProcessingError(SmartAudioChunkerError):
    """Lỗi xảy ra trong quá trình FFmpeg xử lý hoặc cắt audio."""

    pass


class PermissionOrIOError(SmartAudioChunkerError):
    """Lỗi cấp quyền đọc/ghi hoặc tạo thư mục."""

    pass


class ProjectIdExtractionError(SmartAudioChunkerError):
    """Lỗi khi không thể trích xuất Project ID từ tên file."""

    pass


# ==============================================================================
# 3. DATA MODELS & CONFIGURATION
# ==============================================================================
@dataclass(frozen=True)
class ChunkerConfig:
    """Cấu hình tham số hệ thống."""

    # Ngưỡng kích thước tối đa (19.5 MB)
    MAX_FILE_SIZE_BYTES: int = int(19.5 * 1024 * 1024)

    # Ngưỡng an toàn để tính mốc cắt dự kiến (18.0 MB)
    SAFETY_FILE_SIZE_BYTES: int = int(18.0 * 1024 * 1024)

    # FFmpeg Silence Detection Filter Pipeline
    SILENCE_PREPROCESS_FILTER: str = (
        "highpass=f=100,afftdn,loudnorm,silencedetect=n=-35dB:d=0.3"
    )

    # Cửa sổ quét tìm khoảng lặng (giây)
    INITIAL_SEARCH_WINDOW_SEC: float = 15.0
    EXTENDED_SEARCH_WINDOW_SEC: float = 30.0

    # Tên thư mục input/output (tương đối so với thư mục làm việc)
    INPUT_DIR_NAME: str = "original_audios"
    OUTPUT_DIR_NAME: str = "chunked_audio"

    # Hậu tố cần loại bỏ khi trích xuất Project ID
    PROJECT_ID_SUFFIX: str = "_Oaudio"

    # Timeout cho subprocess (giây)
    PROCESS_TIMEOUT_SEC: int = 600


@dataclass(frozen=True)
class AudioMetadata:
    duration_sec: float
    bitrate_bps: int
    size_bytes: int


@dataclass(frozen=True)
class SilenceInterval:
    start_sec: float
    end_sec: float

    @property
    def mid_sec(self) -> float:
        """Điểm chính giữa khoảng lặng (vị trí cắt lý tưởng)."""
        return (self.start_sec + self.end_sec) / 2.0


@dataclass
class ChunkInfo:
    index: int
    file_name: str
    offset_sec: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "file": self.file_name,
            "offset": round(self.offset_sec, 2),
        }


@dataclass
class ChunkMap:
    original_file: str
    project_id: str
    chunked: bool
    chunk_count: int
    chunks: List[ChunkInfo] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_file": self.original_file,
            "project_id": self.project_id,
            "chunked": self.chunked,
            "chunk_count": self.chunk_count,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }


# ==============================================================================
# 4. FFMPEG HELPER WRAPPER
# ==============================================================================
class FFmpegHelper:
    """Wrapper quản lý việc thực thi lệnh subprocess với FFmpeg và FFprobe."""

    @staticmethod
    def check_dependencies() -> None:
        """Kiểm tra sự tồn tại của ffmpeg và ffprobe trong System PATH."""
        for tool in ["ffmpeg", "ffprobe"]:
            if shutil.which(tool) is None:
                raise DependencyNotFoundError(
                    f"Công cụ '{tool}' chưa được cài đặt hoặc chưa được thêm vào System PATH."
                )

    @staticmethod
    def get_metadata(audio_path: Path, timeout: int) -> AudioMetadata:
        """Đọc duration, bitrate và size bằng FFprobe."""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            str(audio_path),
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=timeout
            )
            data = json.loads(result.stdout)
            fmt = data.get("format", {})

            duration = float(fmt.get("duration", 0.0))
            bitrate = int(fmt.get("bit_rate", 0))
            size = int(fmt.get("size", audio_path.stat().st_size))

            if duration <= 0:
                raise AudioProbeError("Thời lượng audio không hợp lệ (<= 0).")

            return AudioMetadata(
                duration_sec=duration, bitrate_bps=bitrate, size_bytes=size
            )
        except (
            subprocess.SubprocessError,
            json.JSONDecodeError,
            KeyError,
            ValueError,
        ) as e:
            raise AudioProbeError(
                f"Không thể đọc metadata của file {audio_path.name}: {str(e)}"
            ) from e

    @staticmethod
    def detect_silence(
        audio_path: Path, filter_str: str, timeout: int
    ) -> List[SilenceInterval]:
        """Tiền xử lý audio qua filter và parse stderr lấy danh sách khoảng lặng."""
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(audio_path),
            "-af",
            filter_str,
            "-f",
            "null",
            "-",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            stderr_output = result.stderr

            starts = re.findall(r"silence_start:\s*([\d\.]+)", stderr_output)
            ends = re.findall(r"silence_end:\s*([\d\.]+)", stderr_output)

            intervals: List[SilenceInterval] = []
            for s, e in zip(starts, ends):
                start_sec = float(s)
                end_sec = float(e)
                if end_sec > start_sec:
                    intervals.append(
                        SilenceInterval(start_sec=start_sec, end_sec=end_sec)
                    )

            logger.info(
                f"Phát hiện {len(intervals)} khoảng lặng trong file {audio_path.name}."
            )
            return intervals
        except subprocess.TimeoutExpired as e:
            raise AudioProcessingError(
                f"Quá thời gian (Timeout) khi detect silence file {audio_path.name}."
            ) from e
        except Exception as e:
            raise AudioProcessingError(
                f"Lỗi không xác định khi detect silence: {str(e)}"
            ) from e

    @staticmethod
    def extract_chunk(
        input_path: Path,
        output_path: Path,
        start_sec: float,
        duration_sec: float,
        timeout: int,
    ) -> None:
        """Cắt một đoạn audio từ start_sec với độ dài duration_sec sử dụng Fast Seeking."""
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-t",
            f"{duration_sec:.3f}",
            "-i",
            str(input_path),
            "-c",
            "copy",
            str(output_path),
        ]
        try:
            subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=timeout
            )
        except subprocess.CalledProcessError as e:
            fallback_cmd = [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-ss",
                f"{start_sec:.3f}",
                "-t",
                f"{duration_sec:.3f}",
                "-i",
                str(input_path),
                "-b:a",
                "192k",
                str(output_path),
            ]
            try:
                subprocess.run(
                    fallback_cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=timeout,
                )
            except Exception as fallback_err:
                raise AudioProcessingError(
                    f"Lỗi khi xuất chunk {output_path.name}: {e.stderr or str(fallback_err)}"
                ) from fallback_err


# ==============================================================================
# 5. CORE ENGINE: SMART AUDIO CHUNKER
# ==============================================================================
class SmartAudioChunker:
    """Core Module xử lý việc chia audio thông minh."""

    def __init__(
        self,
        config: Optional[ChunkerConfig] = None,
        project_id: Optional[str] = None,
    ):
        self.config = config or ChunkerConfig()
        self.project_id = project_id  # Ưu tiên Project ID nếu được cung cấp
        FFmpegHelper.check_dependencies()

    def _extract_project_id(self, audio_path: Path) -> str:
        """
        Trích xuất Project ID từ tên file audio.
        Quy tắc:
        1. Nếu self.project_id đã có -> sử dụng luôn (ưu tiên cao nhất)
        2. Nếu không, lấy từ tên file, loại bỏ hậu tố _Oaudio và extension
        """
        # Ưu tiên Project ID từ constructor
        if self.project_id:
            logger.info(f"Sử dụng Project ID từ constructor: {self.project_id}")
            return self.project_id

        # Trích xuất từ tên file
        stem = audio_path.stem  # Lấy tên file không extension
        
        # Loại bỏ hậu tố _Oaudio (không phân biệt hoa thường)
        if stem.endswith(self.config.PROJECT_ID_SUFFIX):
            project_id = stem[:-len(self.config.PROJECT_ID_SUFFIX)]
        else:
            # Nếu không có hậu tố, lấy toàn bộ tên file
            project_id = stem
        
        # Kiểm tra format PRJ-YYMMDD-XXXX
        pattern = r"^PRJ-\d{6}-[A-F0-9]{4}$"
        if not re.match(pattern, project_id):
            logger.warning(
                f"Tên file '{project_id}' không đúng format PRJ-YYMMDD-XXXX. "
                f"Vẫn sử dụng làm Project ID."
            )
        
        logger.info(f"Trích xuất Project ID từ tên file: {project_id}")
        return project_id

    def _resolve_audio_path(self, audio_input: str | Path) -> Path:
        """Tự động phân giải đường dẫn file audio trong thư mục original_audios/."""
        candidate = Path(audio_input)

        # 1. Kiểm tra nếu đường dẫn truyền vào đã tồn tại trực tiếp
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

        # 2. Kiểm tra trong thư mục original_audios/ tương đối
        input_dir = Path.cwd() / self.config.INPUT_DIR_NAME
        in_original_audios = input_dir / candidate.name
        if in_original_audios.exists() and in_original_audios.is_file():
            return in_original_audios.resolve()

        # 3. Kiểm tra nếu chỉ có tên file (không path) và tìm trong original_audios/
        if not candidate.parent.name:  # Nếu không có thư mục cha
            for ext in ['.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg']:
                test_path = input_dir / f"{candidate.stem}{ext}"
                if test_path.exists() and test_path.is_file():
                    return test_path.resolve()

        raise AudioFileNotFoundError(
            f"Không tìm thấy file audio: '{audio_input}'. "
            f"Đã tìm tại: {candidate} và {in_original_audios}"
        )

    def process(self, audio_input: str | Path) -> Path:
        """
        Nạp file audio đầu vào, kiểm tra dung lượng và tiến hành xử lý.
        Returns: Path tới thư mục chứa kết quả (chunked_audio/PRJ-YYMMDD-XXXX_Chunked/)
        """
        input_file = self._resolve_audio_path(audio_input)
        
        # Trích xuất Project ID
        project_id = self._extract_project_id(input_file)
        
        # Tạo tên thư mục output
        output_folder_name = f"{project_id}_Chunked"
        output_dir = Path.cwd() / self.config.OUTPUT_DIR_NAME / output_folder_name

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise PermissionOrIOError(
                f"Không thể tạo thư mục kết quả {output_dir}: {str(e)}"
            ) from e

        file_size = input_file.stat().st_size
        logger.info(
            f"Bắt đầu xử lý: {input_file.name} | "
            f"Dung lượng: {file_size / (1024*1024):.2f} MB | "
            f"Project ID: {project_id}"
        )

        # NHÁNH 1: Dung lượng <= 19.5 MB -> KHÔNG CHIA
        if file_size <= self.config.MAX_FILE_SIZE_BYTES:
            logger.info("File nhỏ hơn 19.5 MB. Tiến hành copy giữ nguyên...")
            dest_file = output_dir / f"{project_id}_chunk_000.mp3"
            shutil.copy2(input_file, dest_file)

            chunk_map = ChunkMap(
                original_file=input_file.name,
                project_id=project_id,
                chunked=False,
                chunk_count=1,
                chunks=[
                    ChunkInfo(
                        index=1, 
                        file_name=dest_file.name, 
                        offset_sec=0.0
                    )
                ],
            )
            self._save_chunk_map(output_dir, chunk_map)
            logger.info(f"Hoàn thành! Thư mục kết quả: {output_dir}")
            return output_dir

        # NHÁNH 2: Dung lượng > 19.5 MB -> TIẾN HÀNH CHIA THÔNG MINH
        logger.info("File vượt quá 19.5 MB. Bắt đầu quy trình Smart Split...")
        metadata = FFmpegHelper.get_metadata(
            input_file, self.config.PROCESS_TIMEOUT_SEC
        )
        silences = FFmpegHelper.detect_silence(
            input_file,
            self.config.SILENCE_PREPROCESS_FILTER,
            self.config.PROCESS_TIMEOUT_SEC,
        )

        split_points = self._calculate_smart_split_points(metadata, silences)
        chunks_info = self._execute_split(
            input_file, output_dir, split_points, project_id
        )

        chunk_map = ChunkMap(
            original_file=input_file.name,
            project_id=project_id,
            chunked=True,
            chunk_count=len(chunks_info),
            chunks=chunks_info,
        )
        self._save_chunk_map(output_dir, chunk_map)

        logger.info(
            f"Hoàn thành chia thành {len(chunks_info)} chunks! "
            f"Thư mục kết quả: {output_dir}"
        )
        return output_dir

    def _calculate_smart_split_points(
        self, metadata: AudioMetadata, silences: List[SilenceInterval]
    ) -> List[float]:
        """Thuật toán Smart Split 3 cấp độ phòng thủ tìm các mốc thời gian cắt thích hợp."""
        split_points: List[float] = [0.0]
        current_start = 0.0
        total_duration = metadata.duration_sec
        total_size = metadata.size_bytes

        while current_start < total_duration:
            remaining_duration = total_duration - current_start
            remaining_size = total_size * (remaining_duration / total_duration)

            if remaining_size <= self.config.MAX_FILE_SIZE_BYTES:
                break

            target_duration = (
                self.config.SAFETY_FILE_SIZE_BYTES / total_size
            ) * total_duration
            target_split = current_start + target_duration

            chosen_split: Optional[float] = None

            # CẤP 1: Quét cửa sổ ±15 giây
            w1_start = max(
                current_start + 1.0,
                target_split - self.config.INITIAL_SEARCH_WINDOW_SEC,
            )
            w1_end = min(
                total_duration - 1.0,
                target_split + self.config.INITIAL_SEARCH_WINDOW_SEC,
            )

            candidates_c1 = [
                s for s in silences if w1_start <= s.mid_sec <= w1_end
            ]
            if candidates_c1:
                best_silence = min(
                    candidates_c1, key=lambda s: abs(s.mid_sec - target_split)
                )
                chosen_split = best_silence.mid_sec

            # CẤP 2: Quét LÙI -30 giây
            if chosen_split is None:
                w2_start = max(
                    current_start + 1.0,
                    target_split - self.config.EXTENDED_SEARCH_WINDOW_SEC,
                )
                w2_end = target_split

                candidates_c2 = [
                    s for s in silences if w2_start <= s.mid_sec <= w2_end
                ]
                if candidates_c2:
                    best_silence = max(candidates_c2, key=lambda s: s.mid_sec)
                    chosen_split = best_silence.mid_sec

            # CẤP 3: Fallback Hard Split
            if chosen_split is None:
                chosen_split = max(current_start + 10.0, target_split - 5.0)

            split_points.append(chosen_split)
            current_start = chosen_split

        split_points.append(total_duration)
        return split_points

    def _execute_split(
        self, 
        input_file: Path, 
        output_dir: Path, 
        split_points: List[float],
        project_id: str
    ) -> List[ChunkInfo]:
        """Thực thi lệnh xuất các file mp3 dựa trên các điểm cắt đã tính."""
        chunks_info: List[ChunkInfo] = []
        total_chunks = len(split_points) - 1
        pad_width = 3  # Luôn dùng 3 chữ số (000, 001, ...)

        for i in range(total_chunks):
            index = i + 1
            start_p = split_points[i]
            end_p = split_points[i + 1]
            duration = end_p - start_p

            chunk_filename = f"chunk_{index:0{pad_width}d}.mp3"
            chunk_path = output_dir / chunk_filename

            logger.info(
                f"Đang xuất [{index}/{total_chunks}]: {chunk_filename} "
                f"({start_p:.2f}s -> {end_p:.2f}s, Độ dài: {duration:.2f}s)"
            )

            FFmpegHelper.extract_chunk(
                input_file,
                chunk_path,
                start_p,
                duration,
                self.config.PROCESS_TIMEOUT_SEC,
            )

            chunks_info.append(
                ChunkInfo(
                    index=index, 
                    file_name=chunk_filename, 
                    offset_sec=start_p
                )
            )

        return chunks_info

    def _save_chunk_map(self, output_dir: Path, chunk_map: ChunkMap) -> None:
        """Ghi kết quả ra tệp chunk_map.json."""
        map_path = output_dir / "chunk_map.json"
        try:
            with open(map_path, "w", encoding="utf-8") as f:
                json.dump(chunk_map.to_dict(), f, ensure_ascii=False, indent=4)
            logger.info(f"Đã lưu tệp sơ đồ: {map_path.name}")
        except Exception as e:
            raise PermissionOrIOError(
                f"Không thể ghi file {map_path}: {str(e)}"
            ) from e


# ==============================================================================
# 6. PUBLIC HELPER INTERFACE
# ==============================================================================
def process_audio(
    audio_input: str | Path,
    project_id: Optional[str] = None,
) -> Path:
    """
    Hàm giao diện đơn giản nhất để gọi từ module khác.
    
    Args:
        audio_input: Tên file audio hoặc đường dẫn (VD: "PRJ-260730-A7F2_Oaudio.mp3")
        project_id: Project ID (VD: "PRJ-260730-A7F2") - ưu tiên sử dụng nếu được cung cấp
    
    Returns:
        Path tới thư mục output (VD: chunked_audio/PRJ-260730-A7F2_Chunked/)
    """
    chunker = SmartAudioChunker(project_id=project_id)
    return chunker.process(audio_input)


# ==============================================================================
# 7. EXECUTION GUARD (TEST & EXAMPLE)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("      SMART AUDIO CHUNKER - MANUAL RUN TEST      ")
    print("=" * 60)

    # Tạo thư mục original_audios nếu chưa có
    original_dir = Path.cwd() / "original_audios"
    if not original_dir.exists():
        original_dir.mkdir(parents=True)
        print(f"\n[!] Đã tạo thư mục: {original_dir}")
        print("[!] Vui lòng copy file audio vào thư mục này và chạy lại.")
        sys.exit(0)

    # Tìm file audio trong original_audios/
    audio_files = list(original_dir.glob("*.mp3")) + list(original_dir.glob("*.wav"))
    
    if not audio_files:
        print(f"\n[!] Không tìm thấy file .mp3/.wav nào trong: {original_dir}")
        print("[!] Hãy copy file audio vào thư mục trên để thử nghiệm.")
        print("[!] Format tên file: PRJ-YYMMDD-XXXX_Oaudio.mp3")
    else:
        test_file = audio_files[0]
        print(f"File được chọn để test: {test_file.name}")
        
        # Trích xuất Project ID từ tên file (demo)
        stem = test_file.stem
        project_id = stem[:-7] if stem.endswith("_Oaudio") else stem
        print(f"Project ID: {project_id}")
        
        try:
            # Cách 1: Tự động trích xuất Project ID từ tên file
            print("\n--- Test 1: Tự động trích xuất Project ID ---")
            result_directory = process_audio(test_file.name)
            print(f"[✔] Hoàn thành! Kết quả: {result_directory}")
            
            # Cách 2: Truyền Project ID trực tiếp (ưu tiên)
            print("\n--- Test 2: Truyền Project ID trực tiếp ---")
            # result_directory = process_audio(test_file.name, project_id="PRJ-260730-A7F2")
            # print(f"[✔] Hoàn thành! Kết quả: {result_directory}")
            
        except SmartAudioChunkerError as err:
            print(f"\n[✘] LỖI CHUNK AUDIO: {err}")
        except Exception as err:
            print(f"\n[✘] LỖI HỆ THỐNG KHÔNG XÁC ĐỊNH: {err}")