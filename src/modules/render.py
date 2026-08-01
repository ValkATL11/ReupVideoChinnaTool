#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

# =====================================================================
# CẤU HÌNH HỆ THỐNG & ENCODING (CONFIGURATION)
# =====================================================================
VIDEO_CODEC = "libx264"
VIDEO_PRESET = "medium"
VIDEO_CRF = 18

AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"

# Style cho Subtitle (Arial, Chữ trắng, Viền đen, Shadow nhẹ, Nằm dưới giữa)
SUBTITLE_STYLE = (
    "FontName=Arial,"
    "FontSize=20,"
    "PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,"
    "BorderStyle=1,"
    "Outline=2,"
    "Shadow=1,"
    "Alignment=2"
)

# Đường dẫn thư mục mặc định
DIR_ORIGINAL = Path("original_videos")
DIR_TRANSLATED = Path("translated")
DIR_MIXED = Path("mixed_audios")
DIR_OUTPUT = Path("output")

# Setup Logging chuẩn format
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("VideoCompositor")


_fontconfig_env_cache = None


def get_ffmpeg_subtitle_env():
    """
    Build a subprocess environment safe for FFmpeg's `subtitles`/`drawtext`
    filters (libass + fontconfig).

    On many Windows FFmpeg builds, libass's directwrite font provider still
    performs a fontconfig init step. Without a real fonts.conf on the system,
    this prints "Fontconfig error: Cannot load default config file: File not
    found" and, on some builds, the process exits with a non-zero return code
    instead of just warning - which silently breaks any render step that burns
    subtitles (both the Simple Editor's custom subtitles and the main SRT).

    Fix: generate a minimal fonts.conf pointing at the real Windows Fonts
    directory (cached after first call) and point FONTCONFIG_FILE at it so
    fontconfig has something valid to load. No-op / returns None on non-Windows
    systems, where fontconfig is normally already configured correctly.
    """
    global _fontconfig_env_cache
    if os.name != "nt":
        return None

    if _fontconfig_env_cache is not None:
        return _fontconfig_env_cache

    try:
        fonts_dir = os.environ.get("WINDIR", "C:\\Windows") + "\\Fonts"
        cache_dir = Path(tempfile.gettempdir()) / "reuptool_fontconfig_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        conf_dir = Path(tempfile.gettempdir()) / "reuptool_fontconfig"
        conf_dir.mkdir(parents=True, exist_ok=True)
        fonts_conf_path = conf_dir / "fonts.conf"

        fonts_conf_xml = (
            "<?xml version=\"1.0\"?>\n"
            "<!DOCTYPE fontconfig SYSTEM \"fonts.dtd\">\n"
            "<fontconfig>\n"
            f"  <dir>{fonts_dir}</dir>\n"
            f"  <cachedir>{cache_dir}</cachedir>\n"
            "</fontconfig>\n"
        )
        fonts_conf_path.write_text(fonts_conf_xml, encoding="utf-8")

        env = os.environ.copy()
        env["FONTCONFIG_FILE"] = str(fonts_conf_path)
        env["FONTCONFIG_PATH"] = str(conf_dir)
        _fontconfig_env_cache = env
        return env
    except Exception as e:
        logger.warning("Could not prepare fontconfig environment for FFmpeg: %s", e)
        _fontconfig_env_cache = None
        return None


_system_fontfile_cache = None


def resolve_system_fontfile() -> Optional[str]:
    """
    Resolve an actual font FILE on disk (not just a font *name*).

    Using `fontfile=<path>` with FFmpeg's drawtext filter loads the font directly
    via FreeType and never touches DirectWrite/fontconfig font-provider/enumeration
    code at all - the class of code responsible for the Windows
    "Using font provider directwrite (with GDI)" crash-with-no-output seen with the
    libass `subtitles` filter. Preferring a real fontfile path over a font *name*
    (e.g. `font=Arial`) is the most reliable way to burn text on Windows.
    """
    global _system_fontfile_cache
    if _system_fontfile_cache is not None:
        return _system_fontfile_cache or None

    candidates = []
    if os.name == "nt":
        fonts_dir = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
        candidates = [fonts_dir / "arial.ttf", fonts_dir / "Arial.ttf", fonts_dir / "segoeui.ttf"]
    else:
        candidates = [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/System/Library/Fonts/Helvetica.ttc"),
        ]

    for c in candidates:
        if c.exists():
            _system_fontfile_cache = str(c)
            return _system_fontfile_cache

    logger.warning("No usable font file found for drawtext; falling back to font-name lookup.")
    _system_fontfile_cache = ""
    return None


# =====================================================================
# CÁC HÀM HỖ TRỢ (HELPER FUNCTIONS)
# =====================================================================
def check_dependencies():
    """Kiểm tra sự tồn tại của ffmpeg và ffprobe trong hệ thống."""
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    
    if not ffmpeg_path or not ffprobe_path:
        logger.error("[ERROR] FFmpeg hoặc FFprobe chưa được cài đặt hoặc chưa được thêm vào PATH hệ thống.")
        sys.exit(1)


def escape_ffmpeg_filter_path(file_path: Path) -> str:
    """
    Xử lý escape đường dẫn cho FFmpeg Filter (Đặc biệt trên Windows).
    Chuyển \ thành /, escape dấu : và ' để tránh lỗi syntax filter.
    """
    abs_path = str(file_path.resolve())
    clean_path = abs_path.replace("\\", "/")
    clean_path = clean_path.replace(":", "\\:")
    clean_path = clean_path.replace("'", "\\'")
    clean_path = clean_path.replace("[", "\\[").replace("]", "\\]")
    return clean_path


def get_video_duration(video_path: Path) -> float:
    """Lấy thời lượng (seconds) của video gốc bằng ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(res.stdout.strip())
    except Exception as e:
        logger.error(f"[ERROR] Không thể lấy duration của video {video_path.name}: {e}")
        return 0.0


def get_video_resolution(video_path: Path):
    """Lấy (width, height) pixel thực tế của video bằng ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        str(video_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        w_str, h_str = res.stdout.strip().split("x")
        return int(w_str), int(h_str)
    except Exception as e:
        logger.error(f"[ERROR] Không thể lấy resolution của video {video_path.name}: {e}")
        return 1280, 720


def validate_output(output_path: Path) -> bool:
    """Kiểm tra video đầu ra có hợp lệ hay không (Size > 0, đủ stream v/a, duration > 0)."""
    if not output_path.exists() or output_path.stat().st_size == 0:
        return False

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "stream=codec_type",
        "-show_entries", "format=duration",
        "-of", "json",
        str(output_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(res.stdout)
        
        streams = [s.get("codec_type") for s in data.get("streams", [])]
        duration = float(data.get("format", {}).get("duration", 0))

        has_video = "video" in streams
        has_audio = "audio" in streams
        valid_duration = duration > 0

        return has_video and has_audio and valid_duration
    except Exception:
        return False


def sanitize_and_copy_srt(srt_path: Path, temp_dir: Path, project_id: str) -> Path:
    """
    Đọc file SRT với UTF-8 / UTF-8-sig và ghi ra file tạm để đảm bảo 
    FFmpeg không bị lỗi encoding tiếng Việt Unicode trên Windows.
    """
    try:
        with open(srt_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(srt_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

    temp_srt_path = temp_dir / f"{project_id}_clean.srt"
    with open(temp_srt_path, "w", encoding="utf-8") as f:
        f.write(content)

    return temp_srt_path


# =====================================================================
# HÀM XỬ LÝ CHÍNH CHO MỖI PROJECT
# =====================================================================
def process_project(video_path: Path, temp_dir: Path) -> bool:
    """Xử lý từng project video: Burn Subtitle + Thay Audio + Mute Audio gốc."""
    project_id = video_path.stem.removesuffix("_Ovideo")
    
    subtitle_path = DIR_TRANSLATED / f"{project_id}_refined_vi.srt"
    audio_path = DIR_MIXED / f"{project_id}_Mixed.mp3"
    output_path = DIR_OUTPUT / f"{project_id}_Final.mp4"

    logger.info(f"\n[INFO] PROJECT_ID: {project_id}")
    logger.info(f"[INFO] Original Video: {video_path}")
    logger.info(f"[INFO] Subtitle: {subtitle_path}")
    logger.info(f"[INFO] Mixed audio: {audio_path}")

    # 1. Kiểm tra sự tồn tại của các file cần thiết
    missing_files = []
    if not subtitle_path.exists():
        missing_files.append(f"Subtitle: {subtitle_path}")
    if not audio_path.exists():
        missing_files.append(f"Mixed Audio: {audio_path}")

    if missing_files:
        for missing in missing_files:
            logger.error(f"[ERROR] Missing file for {project_id} -> {missing}")
        logger.error(f"[ERROR] Skipping project {project_id} due to missing input files.\n")
        return False

    # 2. Lấy thời lượng video gốc
    orig_duration = get_video_duration(video_path)
    if orig_duration <= 0:
        logger.error(f"[ERROR] Invalid original video duration for {project_id}.")
        return False

    # 3. Chuẩn hóa file SRT sang Temp UTF-8
    temp_srt = sanitize_and_copy_srt(subtitle_path, temp_dir, project_id)
    escaped_srt_path = escape_ffmpeg_filter_path(temp_srt)

    # 4. Chuẩn bị FFmpeg Command
    # -map 0:v:0 -> Lấy Video stream từ Video gốc
    # -map 1:a:0 -> Lấy Audio stream từ Mixed Audio (Bỏ hoàn toàn audio gốc)
    # -vf subtitles=... -> Burn phụ đề tiếng Việt
    # -t orig_duration -> Đảm bảo duration bằng đúng video gốc
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-vf", f"subtitles='{escaped_srt_path}':force_style='{SUBTITLE_STYLE}'",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", VIDEO_CODEC,
        "-preset", VIDEO_PRESET,
        "-crf", str(VIDEO_CRF),
        "-c:a", AUDIO_CODEC,
        "-b:a", AUDIO_BITRATE,
        "-t", str(orig_duration),
        str(output_path)
    ]

    logger.info("[INFO] Original audio will be removed.")
    logger.info("[INFO] Burning Vietnamese subtitles...")
    logger.info("[INFO] Adding mixed audio...")
    logger.info("[INFO] Encoding final video...")

    # 5. Thực thi FFmpeg
    try:
        result = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=get_ffmpeg_subtitle_env()
        )
        if result.returncode != 0:
            logger.error(f"[ERROR] FFmpeg processing failed for {project_id}:")
            logger.error(result.stderr[-500:] if result.stderr else "Unknown FFmpeg error")
            return False
    except Exception as e:
        logger.error(f"[ERROR] Exception occurred while running FFmpeg for {project_id}: {e}")
        return False

    # 6. Kiểm tra kết quả
    if validate_output(output_path):
        logger.info(f"[INFO] Output: {output_path}")
        logger.info(f"[INFO] Completed successfully for PROJECT_ID: {project_id}\n")
        return True
    else:
        logger.error(f"[ERROR] Final video validation failed for {output_path}.\n")
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception:
                pass
        return False


# =====================================================================
# HÀM CHẠY CHÍNH (MAIN FUNCTION)
# =====================================================================
def main():
    logger.info("==================================================")
    logger.info("       FINAL VIDEO COMPOSITOR PIPELINE            ")
    logger.info("==================================================")

    # Kiểm tra dependency FFmpeg
    check_dependencies()

    # Kiểm tra thư mục original_videos
    if not DIR_ORIGINAL.exists():
        logger.error(f"[ERROR] Thư mục '{DIR_ORIGINAL}' không tồn tại.")
        sys.exit(1)

    # Tạo thư mục output nếu chưa có
    DIR_OUTPUT.mkdir(parents=True, exist_ok=True)

    # Quét tất cả các file video có dạng *_Ovideo.mp4
    logger.info(f"[INFO] Scanning {DIR_ORIGINAL}...")
    video_files = list(DIR_ORIGINAL.glob("*_Ovideo.mp4"))

    if not video_files:
        logger.error(f"[ERROR] Không tìm thấy file dạng '*_Ovideo.mp4' trong thư mục '{DIR_ORIGINAL}'.")
        sys.exit(1)

    logger.info(f"[INFO] Found {len(video_files)} matching video file(s).\n")

    success_count = 0
    fail_count = 0

    # Sử dụng thư mục tạm để chứa các file SRT đã clean UTF-8
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)

        for video_path in video_files:
            logger.info(f"[INFO] Found: {video_path.name}")
            is_success = process_project(video_path, temp_dir)
            if is_success:
                success_count += 1
            else:
                fail_count += 1

    logger.info("==================================================")
    logger.info(f"[SUMMARY] Processing finished: {success_count} Succeeded, {fail_count} Failed.")
    logger.info("==================================================")


if __name__ == "__main__":
    main()