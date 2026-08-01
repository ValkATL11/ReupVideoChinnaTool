import json
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from groq import Groq

# Cấu hình Logging hiển thị tiến trình
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("TranscriberAPI")


class TranscriberAPI:
    """Mô-đun 2-Pass: 
    - Lần 1: Lấy Segment-level (File SRT gốc)
    - Lần 2: Lấy Word-level (File dữ liệu mốc thời gian từ đơn)
    - Ghép Word-level cho các câu siêu dài để tách câu chuẩn nhịp audio gốc.
    """

    def __init__(self, api_key: str, model: str = "whisper-large-v3-turbo"):
        self.client = Groq(api_key=api_key)
        self.model = model
        self.temp_dir = None  # Sẽ được khởi tạo khi process

    def _setup_temp_dir(self):
        """Tạo thư mục tạm cho các file trung gian."""
        if self.temp_dir is None:
            self.temp_dir = Path(tempfile.mkdtemp(prefix="transcriber_temp_"))
            logger.info(f"📁 Tạo thư mục tạm: {self.temp_dir}")

    def _cleanup_temp_dir(self):
        """Dọn dẹp thư mục tạm sau khi hoàn tất."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            logger.info(f"🧹 Đã dọn dẹp thư mục tạm: {self.temp_dir}")
            self.temp_dir = None

    def _format_timestamp(self, seconds: float) -> str:
        """Định dạng giây thành timestamp chuẩn SRT (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int(round((seconds % 1) * 1000))
        if millis >= 1000:
            secs += 1
            millis = 0
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _transcribe_chunk(self, audio_path: Path, granularity: str, language: str = "auto") -> Optional[Dict[str, Any]]:
        """Hàm dùng chung gọi Groq Whisper API theo granularity ('segment' hoặc 'word')."""
        try:
            with open(audio_path, "rb") as f:
                kwargs = {
                    "file": (audio_path.name, f.read()),
                    "model": self.model,
                    "response_format": "verbose_json",
                    "timestamp_granularities": [granularity],
                }
                if language and language != "auto":
                    kwargs["language"] = language

                transcription = self.client.audio.transcriptions.create(**kwargs)

            data = transcription.model_dump() if hasattr(transcription, "model_dump") else transcription.__dict__
            return data
        except Exception as e:
            logger.error(f"❌ Lỗi Groq API ({granularity}) tại {audio_path.name}: {e}")
            return None

    def _split_long_segment_by_words(
        self, 
        seg: Dict[str, Any], 
        all_words: List[Dict[str, Any]], 
        max_chars: int = 35
    ) -> List[Dict[str, Any]]:
        """
        Tìm các từ trong Word-level rơi vào khoảng thời gian của câu bất thường [seg.start -> seg.end].
        Sau đó ghép các từ lại thành các câu ngắn dựa trên timestamp thực tế của word.
        """
        seg_start = seg["start"]
        seg_end = seg["end"]

        # 1. Lọc các từ thuộc khoảng thời gian câu bất thường này (cho phép sai số 0.3s)
        matched_words = [
            w for w in all_words 
            if (w["start"] >= seg_start - 0.3) and (w["end"] <= seg_end + 0.3)
        ]

        # Nếu không khớp được từ nào từ File 2, giữ nguyên câu gốc
        if not matched_words:
            return [seg]

        # 2. Gom từ thành các câu nhỏ dựa trên timestamp chính xác của từng từ
        new_segments = []
        curr_words = []
        sub_start = None

        for idx, w in enumerate(matched_words):
            word_text = w["word"].strip()
            if not word_text:
                continue

            if sub_start is None:
                sub_start = w["start"]

            curr_words.append(word_text)
            curr_text = " ".join(curr_words)
            sub_end = w["end"]

            # Kiểm tra ngắt câu: 
            # - Có dấu ngắt câu (. , ! ?)
            # - Hoặc độ dài chữ >= max_chars
            # - Hoặc là từ cuối cùng trong tập từ match được
            has_punct = any(word_text.endswith(p) for p in [".", ",", "!", "?", "...", "。", "，"])
            is_too_long = len(curr_text) >= max_chars
            is_last = (idx == len(matched_words) - 1)

            if has_punct or is_too_long or is_last:
                new_segments.append({
                    "start": sub_start,
                    "end": sub_end,
                    "text": curr_text
                })
                curr_words = []
                sub_start = None

        return new_segments if new_segments else [seg]

    def _extract_project_id(self, folder_name: str) -> str:
        """
        Trích xuất Project ID từ tên thư mục chunked.
        Format: PRJ-YYMMDD-XXXX_Chunked
        """
        # Loại bỏ hậu tố _Chunked
        if folder_name.endswith("_Chunked"):
            project_id = folder_name[:-8]
        else:
            project_id = folder_name
        
        # Kiểm tra format PRJ-YYMMDD-XXXX
        pattern = r"^PRJ-\d{6}-[A-F0-9]{4}$"
        if not re.match(pattern, project_id):
            logger.warning(
                f"⚠️ Project ID '{project_id}' không đúng format PRJ-YYMMDD-XXXX. "
                f"Vẫn sử dụng làm Project ID."
            )
        
        return project_id

    def process_folder(self, chunked_folder: Path, language: str = "auto") -> Optional[Dict[str, Any]]:
        """Xử lý transcription cho một folder chunked audio."""
        # Tạo thư mục tạm
        self._setup_temp_dir()
        
        # Đọc chunk_map.json
        map_file = chunked_folder / "chunk_map.json"
        if not map_file.exists():
            logger.error(f"❌ Không tìm thấy chunk_map.json tại: {map_file}")
            return None

        with open(map_file, "r", encoding="utf-8") as f:
            chunk_map = json.load(f)

        chunks = chunk_map.get("chunks", [])
        if not chunks:
            logger.error(f"❌ Không có chunk nào trong chunk_map.json")
            return None

        # Trích xuất Project ID từ tên folder
        project_id = self._extract_project_id(chunked_folder.name)
        logger.info(f"📋 Project ID: {project_id}")

        original_segments: List[Dict[str, Any]] = []
        all_words_file2: List[Dict[str, Any]] = []
        detected_lang = None

        logger.info(f"▶ Bắt đầu xử lý folder: {chunked_folder.name} ({len(chunks)} chunks)")

        # ==============================================================================
        # BƯỚC 1: BẮT ĐẦU GỌI API VÀ THU THỦY DỮ LIỆU FILE 1 & FILE 2
        # ==============================================================================
        for chunk in chunks:
            chunk_filename = chunk["file"]
            offset = float(chunk["offset"])
            chunk_path = chunked_folder / chunk_filename

            if not chunk_path.exists():
                logger.error(f"❌ File chunk không tồn tại: {chunk_path}")
                return None

            # --- Gọi Lần 1: Lấy Segment-level (Tạo File 1) ---
            logger.info(f"  └─ [Lần 1] Gọi Segment API: {chunk_filename}")
            seg_data = self._transcribe_chunk(chunk_path, granularity="segment", language=language)
            if not seg_data:
                return None

            if not detected_lang and seg_data.get("language"):
                detected_lang = seg_data["language"]

            for seg in seg_data.get("segments", []):
                s = seg if isinstance(seg, dict) else seg.__dict__
                original_segments.append({
                    "start": round(float(s.get("start", 0.0)) + offset, 2),
                    "end": round(float(s.get("end", 0.0)) + offset, 2),
                    "text": str(s.get("text", "")).strip()
                })

            # --- Gọi Lần 2: Lấy Word-level (Tạo File 2 dữ liệu từ) ---
            logger.info(f"  └─ [Lần 2] Gọi Word-level API: {chunk_filename}")
            word_data = self._transcribe_chunk(chunk_path, granularity="word", language=language)
            if word_data:
                for w in word_data.get("words", []):
                    w_dict = w if isinstance(w, dict) else w.__dict__
                    all_words_file2.append({
                        "word": str(w_dict.get("word", "")).strip(),
                        "start": round(float(w_dict.get("start", 0.0)) + offset, 2),
                        "end": round(float(w_dict.get("end", 0.0)) + offset, 2),
                    })

        # ==============================================================================
        # BƯỚC 2: QUÉT CÂU BẤT THƯỜNG TRONG FILE 1 & ĐỐI CHIẾU SANG FILE 2 TÁCH LẠI
        # ==============================================================================
        logger.info(f"🔍 Tổng số câu gốc (File 1): {len(original_segments)} câu.")
        logger.info("🔍 Đang tiến hành tìm câu dài bất thường và khớp timestamp từng từ từ File 2...")

        refined_segments: List[Dict[str, Any]] = []

        for seg in original_segments:
            char_len = len(seg["text"])
            duration = seg["end"] - seg["start"]

            # Ngưỡng phát hiện câu bất thường: Dài > 70 ký tự HOẶC thời lượng > 8 giây
            is_abnormal = (char_len > 70) or (duration > 8.0)

            if is_abnormal:
                logger.warning(
                    f"  ⚠️ Phát hiện câu bất thường ({char_len} chars, {duration:.1f}s): \"{seg['text'][:30]}...\""
                )
                # Lấy các từ từ File 2 ứng với câu này để tách chuẩn nhịp
                split_res = self._split_long_segment_by_words(seg, all_words_file2, max_chars=35)
                refined_segments.extend(split_res)
            else:
                # Nếu câu bình thường, GIỮ NGUYÊN HOÀN TOÀN
                refined_segments.append(seg)

        # Dọn dẹp thư mục tạm
        self._cleanup_temp_dir()

        return {
            "project_id": project_id,
            "language": detected_lang,
            "original_segments": original_segments,  # File 1 gốc (SRT)
            "refined_segments": refined_segments,    # File 2 đã ghép Word-Level (SRT)
            "words_data": all_words_file2             # Danh sách từng từ chi tiết (JSON)
        }

    def export_outputs(
        self, 
        result: Dict[str, Any], 
        output_dir: Path
    ) -> Dict[str, Path]:
        """
        Xuất 3 file output bắt buộc vào thư mục output.
        
        Returns:
            Dict chứa đường dẫn các file đã xuất
        """
        project_id = result["project_id"]
        # Đổi hậu tố từ _Chunked thành _transcribed
        folder_name = f"{project_id}_transcribed"
        output_folder = output_dir / folder_name
        
        # Tạo thư mục output
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Đường dẫn các file output
        output_files = {
            "original": output_folder / f"{project_id}_original.srt",
            "refined": output_folder / f"{project_id}_refined.srt",
            "words": output_folder / f"{project_id}_words.json"
        }
        
        # 1. Xuất file SRT gốc (original)
        with open(output_files["original"], "w", encoding="utf-8") as f:
            for i, seg in enumerate(result["original_segments"], 1):
                start = self._format_timestamp(seg["start"])
                end = self._format_timestamp(seg["end"])
                f.write(f"{i}\n{start} --> {end}\n{seg['text'].strip()}\n\n")
        logger.info(f"✓ Đã xuất file SRT gốc: {output_files['original']}")
        
        # 2. Xuất file SRT đã refine
        with open(output_files["refined"], "w", encoding="utf-8") as f:
            for i, seg in enumerate(result["refined_segments"], 1):
                start = self._format_timestamp(seg["start"])
                end = self._format_timestamp(seg["end"])
                f.write(f"{i}\n{start} --> {end}\n{seg['text'].strip()}\n\n")
        logger.info(f"✓ Đã xuất file SRT refined: {output_files['refined']}")
        
        # 3. Xuất file JSON word-level
        with open(output_files["words"], "w", encoding="utf-8") as f:
            json.dump(result["words_data"], f, ensure_ascii=False, indent=2)
        logger.info(f"✓ Đã xuất file Word-Level JSON: {output_files['words']}")
        
        return output_files


# ==============================================================================
# HÀM THỰC THI CHÍNH
# ==============================================================================
def process_all_transcriptions(
    groq_api_key: str,
    target_project_id: Optional[str] = None,
    language: str = "auto"
) -> List[Path]:
    """
    Xử lý transcription cho tất cả project trong thư mục chunked_audio.
    
    Args:
        groq_api_key: API key của Groq
        target_project_id: Project ID cụ thể cần xử lý (VD: PRJ-260729-37TG)
                           Nếu None, xử lý tất cả project
        language: Ngôn ngữ (mặc định: auto)
    
    Returns:
        List các đường dẫn file output đã tạo
    """
    base_project_dir = Path(__file__).resolve().parent
    chunked_base_dir = base_project_dir / "chunked_audio"
    output_dir = base_project_dir / "transcriber_output"

    if not chunked_base_dir.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục chunked_audio tại: {chunked_base_dir}")

    runner = TranscriberAPI(api_key=groq_api_key)
    created_files: List[Path] = []

    # Xác định các folder cần xử lý
    if target_project_id:
        folder_name = f"{target_project_id}_Chunked"
        folders_to_process = [chunked_base_dir / folder_name]
        if not folders_to_process[0].exists():
            raise FileNotFoundError(f"Không tìm thấy folder: {folder_name}")
    else:
        # Lấy tất cả folder có format PRJ-*_Chunked
        folders_to_process = [
            f for f in chunked_base_dir.iterdir() 
            if f.is_dir() and f.name.endswith("_Chunked")
        ]

    if not folders_to_process:
        logger.warning("⚠️ Không tìm thấy folder nào để xử lý.")
        return []

    # Xử lý từng folder
    for folder in folders_to_process:
        logger.info(f"\n{'='*60}")
        logger.info(f"📂 Xử lý folder: {folder.name}")
        logger.info(f"{'='*60}")
        
        try:
            result = runner.process_folder(folder, language=language)
            if not result:
                logger.error(f"❌ Không thể xử lý folder: {folder.name}")
                continue
            
            # Xuất output
            output_files = runner.export_outputs(result, output_dir)
            created_files.extend(output_files.values())
            
            logger.info(f"✅ Hoàn thành xử lý: {folder.name}")
            
        except Exception as e:
            logger.error(f"❌ Lỗi khi xử lý {folder.name}: {e}")
            # Đảm bảo dọn dẹp thư mục tạm ngay cả khi có lỗi
            if hasattr(runner, '_cleanup_temp_dir'):
                runner._cleanup_temp_dir()
            continue

    return created_files


# ==============================================================================
# CHẠY THỬ
# ==============================================================================
if __name__ == "__main__":
    MY_GROQ_API_KEY = ""

    try:
        # Test 1: Xử lý tất cả project
        print("\n" + "="*60)
        print("🚀 BẮT ĐẦU XỬ LÝ TẤT CẢ PROJECT")
        print("="*60)
        
        output_files = process_all_transcriptions(
            groq_api_key=MY_GROQ_API_KEY,
            target_project_id=None,  # Xử lý tất cả
            language="auto"
        )
        
        print(f"\n✅ HOÀN THÀNH! TẤT CẢ FILE ĐÃ ĐƯỢC LƯU TRONG 'transcriber_output':")
        for file in output_files:
            print(f" ──> {file}")
            
        # Test 2: Xử lý một project cụ thể (ví dụ)
        # output_files = process_all_transcriptions(
        #     groq_api_key=MY_GROQ_API_KEY,
        #     target_project_id="PRJ-260729-37TG",
        #     language="auto"
        # )
        
    except Exception as err:
        print(f"\n❌ Có lỗi: {err}")