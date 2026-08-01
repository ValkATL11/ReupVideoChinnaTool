#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Smart Dubber Pro: Module lồng tiếng AI thông minh chuyên nghiệp.
Hỗ trợ:
- Voice Cache (MD5 Hash)
- Waveform & Energy Silence Detection
- Smart Trim (Tối ưu khoảng nghỉ trước khi đổi tốc độ)
- Dynamic Speed Ramping (Tăng tốc mềm mại)
- FFmpeg Pitch-preserving Time Stretch
- Configurable User Modes (Time First, Quality First, Balanced)
- Auto Folder Management
- Tự động xóa các segment file sau khi ghép master
"""

import os
import re
import io
import math
import hashlib
import asyncio
import logging
import subprocess
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import edge_tts
from pydub import AudioSegment
from pydub.silence import detect_nonsilent, detect_silence

# ====== CẤU HÌNH HỆ THỐNG ======
VOICE_DEFAULT = "vi-VN-HoaiMyNeural"
CACHE_DIR = Path("./voice_cache")
TEMP_DIR = Path("./temp_dubber")

# Đường dẫn thư mục gốc mặc định
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SRT_DIR = BASE_DIR / "translated"
DEFAULT_DUBOUT_DIR = BASE_DIR / "dubbing"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("SmartDubber")


class UserMode(Enum):
    TIME_FIRST = "time_first"      # Ưu tiên khớp thời lượng (Chấp nhận tăng tốc tối đa)
    QUALITY_FIRST = "quality_first"# Ưu tiên giọng tự nhiên (Tối đa 1.2x - 1.25x)
    BALANCED = "balanced"          # Dung hòa giữa Smart Trim và Dynamic Speed


class VoiceCache:
    """Quản lý lưu và tái sử dụng File Audio đã TTS để tiết kiệm tài nguyên & thời gian"""
    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_hash(self, text: str, voice: str) -> str:
        key = f"{voice}_{text.strip()}"
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    def get(self, text: str, voice: str) -> Optional[AudioSegment]:
        file_hash = self._get_hash(text, voice)
        cache_file = self.cache_dir / f"{file_hash}.mp3"
        if cache_file.exists():
            logger.debug(f"⚡ [Cache Hit] Tìm thấy voice cache: {file_hash[:8]}")
            return AudioSegment.from_file(cache_file, format="mp3")
        return None

    def save(self, text: str, voice: str, audio: AudioSegment):
        file_hash = self._get_hash(text, voice)
        cache_file = self.cache_dir / f"{file_hash}.mp3"
        audio.export(cache_file, format="mp3")


class SmartDubberEngine:
    def __init__(
        self,
        voice: str = VOICE_DEFAULT,
        mode: UserMode = UserMode.BALANCED,
        max_speed_cap: float = 2.0
    ):
        self.voice = voice
        self.mode = mode
        self.max_speed_cap = max_speed_cap
        self.cache = VoiceCache()
        
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. TIMESTRETCH BẰNG FFMPEG (GIỮ NGUYÊN PITCH)
    # ------------------------------------------------------------------
    def change_speed_ffmpeg(self, audio: AudioSegment, speed: float) -> AudioSegment:
        """Thay đổi tốc độ audio dùng FFmpeg 'atempo' filter để không bị đổi Cao Độ (Pitch)"""
        if math.isclose(speed, 1.0, abs_tol=0.03):
            return audio

        # Giới hạn tốc độ theo Mode
        if self.mode == UserMode.QUALITY_FIRST:
            speed = min(speed, 1.25)
        else:
            speed = min(speed, self.max_speed_cap)

        in_file = TEMP_DIR / f"input_{os.getpid()}.wav"
        out_file = TEMP_DIR / f"output_{os.getpid()}.wav"

        audio.export(in_file, format="wav")

        # Xây dựng filter chain cho atempo
        filters = []
        curr_speed = speed
        while curr_speed > 2.0:
            filters.append("atempo=2.0")
            curr_speed /= 2.0
        while curr_speed < 0.5:
            filters.append("atempo=0.5")
            curr_speed /= 0.5
        filters.append(f"atempo={curr_speed:.4f}")

        filter_str = ",".join(filters)

        cmd = [
            "ffmpeg", "-y", "-i", str(in_file),
            "-filter:a", filter_str,
            "-vn", str(out_file)
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            result = AudioSegment.from_file(out_file, format="wav")
            return result
        except Exception as e:
            logger.error(f"Lỗi FFmpeg TimeStretch: {e}. Fallback về pydub speedup.")
            return audio.speedup(playback_speed=speed)
        finally:
            if in_file.exists(): in_file.unlink()
            if out_file.exists(): out_file.unlink()

    # ------------------------------------------------------------------
    # 2. SILENCE DETECTION & SMART TRIM
    # ------------------------------------------------------------------
    def smart_trim(self, audio: AudioSegment, target_duration_sec: float) -> AudioSegment:
        nonsilent = detect_nonsilent(audio, min_silence_len=60, silence_thresh=-40)
        if nonsilent:
            start_ms = nonsilent[0][0]
            end_ms = nonsilent[-1][1]
            audio = audio[start_ms:end_ms]

        current_dur_sec = len(audio) / 1000.0
        if current_dur_sec <= target_duration_sec:
            return audio

        silences = detect_silence(audio, min_silence_len=100, silence_thresh=-38)
        if not silences:
            return audio

        trimmed_audio = AudioSegment.empty()
        prev_end = 0

        for start_p, end_p in silences:
            trimmed_audio += audio[prev_end:start_p]
            pause_len = end_p - start_p
            reduced_pause = min(pause_len, 80)
            trimmed_audio += AudioSegment.silent(duration=reduced_pause)
            prev_end = end_p

        trimmed_audio += audio[prev_end:]
        return trimmed_audio

    # ------------------------------------------------------------------
    # 3. DYNAMIC SPEED RAMPING (Tăng tốc theo cấp độ)
    # ------------------------------------------------------------------
    def apply_dynamic_speed(self, audio: AudioSegment, target_dur_sec: float) -> AudioSegment:
        curr_dur = len(audio) / 1000.0
        required_speed = curr_dur / target_dur_sec

        if required_speed <= 1.05:
            return audio

        num_chunks = 3
        chunk_len = len(audio) // num_chunks
        processed_audio = AudioSegment.empty()

        speed_steps = []
        base_step = (required_speed - 1.0) / (num_chunks)
        for i in range(1, num_chunks + 1):
            s = 1.0 + (base_step * i * 1.3)
            speed_steps.append(s)

        for i in range(num_chunks):
            start = i * chunk_len
            end = (i + 1) * chunk_len if i < num_chunks - 1 else len(audio)
            chunk = audio[start:end]
            
            speed = speed_steps[i]
            speed_chunk = self.change_speed_ffmpeg(chunk, speed)
            processed_audio += speed_chunk

        return processed_audio

    # ------------------------------------------------------------------
    # 4. TẠO VOICE VỚI RETRY VÀ CACHE
    # ------------------------------------------------------------------
    async def fetch_tts(self, text: str) -> Optional[AudioSegment]:
        cached_audio = self.cache.get(text, self.voice)
        if cached_audio:
            return cached_audio

        for attempt in range(1, 4):
            try:
                communicate = edge_tts.Communicate(text, self.voice)
                audio_bytes = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_bytes += chunk["data"]

                if not audio_bytes:
                    raise ValueError("Không nhận được dữ liệu âm thanh")

                audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
                self.cache.save(text, self.voice, audio)
                return audio
            except Exception as e:
                logger.warning(f"Thử lại TTS ({attempt}/3) lỗi: {e}")
                await asyncio.sleep(1.0 * attempt)

        return None

    # ------------------------------------------------------------------
    # 5. XỬ LÝ CHÍNH TỪNG CÂU
    # ------------------------------------------------------------------
    async def process_sub_item(self, item: Dict) -> Optional[Dict]:
        text = item['text']
        srt_dur = item['duration']

        raw_audio = await self.fetch_tts(text)
        if not raw_audio:
            logger.error(f"❌ Bỏ qua câu #{item['index']}: Thất bại khi tạo TTS.")
            return None

        trimmed_audio = self.smart_trim(raw_audio, srt_dur)
        audio_dur = len(trimmed_audio) / 1000.0

        if audio_dur > srt_dur and srt_dur > 0:
            speed_factor = audio_dur / srt_dur

            if self.mode == UserMode.TIME_FIRST:
                final_audio = self.change_speed_ffmpeg(trimmed_audio, speed_factor)
                logger.info(f"⚡ [TIME_FIRST] #{item['index']}: Compress {speed_factor:.2f}x ({audio_dur:.1f}s -> {srt_dur:.1f}s)")
            
            elif self.mode == UserMode.BALANCED:
                if speed_factor > 1.25:
                    final_audio = self.apply_dynamic_speed(trimmed_audio, srt_dur)
                else:
                    final_audio = self.change_speed_ffmpeg(trimmed_audio, speed_factor)
                logger.info(f"⚖️ [BALANCED] #{item['index']}: Adjust {speed_factor:.2f}x")

            elif self.mode == UserMode.QUALITY_FIRST:
                cap_speed = min(speed_factor, 1.2)
                final_audio = self.change_speed_ffmpeg(trimmed_audio, cap_speed)
                logger.info(f"🎨 [QUALITY_FIRST] #{item['index']}: Soft Speed {cap_speed:.2f}x")
        else:
            final_audio = trimmed_audio
            logger.info(f"✅ #{item['index']}: Perfect Match ({audio_dur:.2f}s / {srt_dur:.2f}s)")

        return {
            'index': item['index'],
            'start': item['start'],
            'end': item['end'],
            'audio': final_audio,
            'text': text
        }


# ====== HELPER FUNCTIONS ======
def timestamp_to_seconds(ts: str) -> float:
    h, m, s_ms = ts.split(':')
    s, ms = s_ms.split(',')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt_file(srt_path: Path) -> List[Dict]:
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = re.split(r'\n\s*\n', content.strip())
    subtitles = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3 or not lines[0].isdigit():
            continue

        idx = int(lines[0])
        time_line = lines[1]
        match = re.search(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', time_line)
        if not match:
            continue

        start = timestamp_to_seconds(match.group(1))
        end = timestamp_to_seconds(match.group(2))
        text = re.sub(r'\s+', ' ', ' '.join(lines[2:])).strip()

        if text:
            subtitles.append({
                'index': idx,
                'start': start,
                'end': end,
                'duration': end - start,
                'text': text
            })
    return subtitles


def extract_project_id_from_srt(srt_path: Path) -> str:
    """
    Trích xuất Project ID từ tên file SRT.
    Format: {PROJECT_ID}_refined_vi.srt
    """
    stem = srt_path.stem  # VD: PRJ-260729-37TG_refined_vi
    
    # Loại bỏ hậu tố _refined_vi
    if stem.endswith("_refined_vi"):
        project_id = stem[:-11]  # Loại bỏ "_refined_vi"
    elif stem.endswith("_refined"):
        project_id = stem[:-8]   # Loại bỏ "_refined"
    elif stem.endswith("_vi"):
        project_id = stem[:-3]   # Loại bỏ "_vi"
    else:
        project_id = stem
    
    # Kiểm tra format PRJ-YYMMDD-XXXX
    pattern = r"^PRJ-[\dA-Z-]+$"
    if not re.match(pattern, project_id):
        logger.warning(f"⚠️ Project ID '{project_id}' không đúng format chuẩn.")
    
    return project_id


# ====== EXECUTION MAIN ======
async def run_smart_dubber(
    srt_file: Path,
    base_dubout_dir: Path,
    mode: UserMode = UserMode.BALANCED,
    output_format: str = "mp3"
):
    """
    Xử lý dubbing cho một file SRT.
    
    Input:  translated/{PROJECT_ID}_refined_vi.srt
    Output: dubbing/{PROJECT_ID}/
            ├── {PROJECT_ID}_000.{format}
            ├── {PROJECT_ID}_001.{format}
            ├── ...
            └── {PROJECT_ID}_0Full.{format}
    Sau khi hoàn thành, các segment (có số thứ tự) sẽ bị xóa, chỉ giữ lại file _0Full.
    """
    if not srt_file.exists():
        logger.error(f"❌ File SRT không tồn tại: {srt_file}")
        return

    # Trích xuất Project ID từ tên file
    project_id = extract_project_id_from_srt(srt_file)
    logger.info(f"📋 Project ID: {project_id}")

    # Tạo thư mục output cho project
    output_dir = base_dubout_dir / project_id
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"📁 Thư mục xuất: {output_dir}")

    # Khởi tạo engine
    dubber = SmartDubberEngine(voice=VOICE_DEFAULT, mode=mode)
    
    # Parse SRT
    subtitles = parse_srt_file(srt_file)
    if not subtitles:
        logger.error("❌ Không lấy được dữ liệu từ SRT")
        return

    logger.info(f"🚀 Bắt đầu Smart Dubbing [{mode.value.upper()}] cho {len(subtitles)} câu...")

    # Xử lý từng câu và lưu file segment
    results = []
    total = len(subtitles)
    pad_width = len(str(total))  # Độ rộng padding cho số index
    segment_paths = []  # Lưu danh sách các segment file để xóa sau

    for idx, item in enumerate(subtitles, 1):
        logger.info(f"🔄 Đang xử lý câu {idx}/{total} (Index {item['index']})")
        
        res = await dubber.process_sub_item(item)
        if res:
            results.append(res)
            
            # Lưu file segment với format: {PROJECT_ID}_{index:0{pad_width}d}.{format}
            segment_filename = f"{project_id}_{res['index']:0{pad_width}d}.{output_format}"
            segment_path = output_dir / segment_filename
            res['audio'].export(segment_path, format=output_format)
            segment_paths.append(segment_path)  # Ghi nhớ để xóa sau
            logger.info(f"✅ Đã lưu segment: {segment_filename}")

    # Ghép Master Track
    if results:
        results.sort(key=lambda x: x['start'])
        max_end = max(r['end'] for r in results)
        
        # Tạo canvas âm thanh im lặng
        master_track = AudioSegment.silent(duration=int((max_end + 2.0) * 1000))

        for clip in results:
            pos_ms = int(clip['start'] * 1000)
            master_track = master_track.overlay(clip['audio'], position=pos_ms)

        # Lưu file master 0Full
        master_filename = f"{project_id}_0Full.{output_format}"
        master_path = output_dir / master_filename
        master_track.export(master_path, format=output_format)
        logger.info(f"🎉 Hoàn thành ghép Master Audio: {master_filename}")

        # Xóa các segment file (chỉ giữ lại file _0Full)
        logger.info(f"🧹 Đang dọn dẹp các segment file ...")
        deleted_count = 0
        for seg_path in segment_paths:
            if seg_path.exists():
                try:
                    seg_path.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Không thể xóa {seg_path.name}: {e}")
        logger.info(f"🗑️ Đã xóa {deleted_count}/{len(segment_paths)} segment file. Chỉ giữ lại file master.")

        logger.info(f"✨ Hoàn thành! Output tại: {output_dir}")
        logger.info(f"📊 Tổng số segment: {len(results)}")
        logger.info(f"📊 Total duration: {max_end:.2f}s")
        
        return output_dir
    else:
        logger.error("❌ Không có segment nào được tạo thành công")
        return None


# ====== PUBLIC INTERFACE ======
def process_dubbing(
    srt_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    mode: str = "balanced",
    output_format: str = "mp3"
) -> Optional[Path]:
    """
    Hàm public để gọi từ bên ngoài.
    
    Args:
        srt_path: Đường dẫn đến file SRT (mặc định: translated/{PROJECT_ID}_refined_vi.srt)
        output_dir: Thư mục output (mặc định: dubbing/)
        mode: "time_first", "quality_first", "balanced"
        output_format: "mp3", "wav", "aac", ...
    
    Returns:
        Path đến thư mục output
    """
    # Xác định mode
    mode_map = {
        "time_first": UserMode.TIME_FIRST,
        "quality_first": UserMode.QUALITY_FIRST,
        "balanced": UserMode.BALANCED
    }
    user_mode = mode_map.get(mode.lower(), UserMode.BALANCED)
    
    # Xác định đường dẫn SRT
    if srt_path is None:
        # Tìm tất cả file *_refined_vi.srt trong translated/
        srt_files = list(DEFAULT_SRT_DIR.glob("*_refined_vi.srt"))
        if not srt_files:
            logger.error(f"❌ Không tìm thấy file *_refined_vi.srt trong {DEFAULT_SRT_DIR}")
            return None
        srt_path = srt_files[0]  # Lấy file đầu tiên
        logger.info(f"📄 Tự động chọn SRT: {srt_path.name}")
    
    # Xác định output dir
    if output_dir is None:
        output_dir = DEFAULT_DUBOUT_DIR
    
    # Chạy dubbing
    result = asyncio.run(run_smart_dubber(
        srt_file=srt_path,
        base_dubout_dir=output_dir,
        mode=user_mode,
        output_format=output_format
    ))
    
    return result


# ====== MAIN ======
if __name__ == "__main__":
    import sys

    # Lấy đường dẫn file SRT từ tham số dòng lệnh hoặc dùng mặc định
    srt_input = None
    if len(sys.argv) > 1:
        srt_input = Path(sys.argv[1])
        if not srt_input.exists():
            # Thử tìm trong thư mục translated
            srt_input = DEFAULT_SRT_DIR / sys.argv[1]
            if not srt_input.exists():
                print(f"❌ Không tìm thấy file: {sys.argv[1]}")
                sys.exit(1)

    # Lấy mode từ tham số dòng lệnh
    mode = "balanced"
    if len(sys.argv) > 2:
        mode = sys.argv[2]

    # Lấy output format từ tham số dòng lệnh
    output_format = "mp3"
    if len(sys.argv) > 3:
        output_format = sys.argv[3]

    print("=" * 60)
    print("🎙️ SMART DUBBER PRO")
    print("=" * 60)
    print(f"📂 Input dir: {DEFAULT_SRT_DIR}")
    print(f"📂 Output dir: {DEFAULT_DUBOUT_DIR}")
    print(f"🎚️ Mode: {mode.upper()}")
    print(f"📦 Format: {output_format.upper()}")
    print("=" * 60)

    # Chạy xử lý
    result = process_dubbing(
        srt_path=srt_input,
        output_dir=DEFAULT_DUBOUT_DIR,
        mode=mode,
        output_format=output_format
    )

    if result:
        print(f"\n✅ THÀNH CÔNG! Output tại: {result}")
        print("🧹 Các file segment đã được dọn dẹp, chỉ giữ lại file _0Full.")
    else:
        print("\n❌ THẤT BẠI! Kiểm tra log để biết thêm chi tiết.")