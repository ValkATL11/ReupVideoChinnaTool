# src/reup_tool/subtitle_formatter.py
import os
import re
import logging
from pathlib import Path
from typing import Optional, Callable

from reup_tool.config import config
from reup_tool.utils import read_text_file

logger = logging.getLogger(__name__)


def extract_subtitle_text(srt_content: str) -> str:
    lines = srt_content.strip().split('\n')
    subtitle_lines = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.isdigit() or '-->' in line or line == '':
            i += 1
            continue
        if line:
            line = re.sub(r'^Dòng\s*\d+:\s*', '', line)
            line = re.sub(r'^\d+\s+', '', line)
            subtitle_lines.append(line)
        i += 1
    return '\n'.join(subtitle_lines)


def process_all(
    single_file: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> bool:
    srt_dir = config.paths.translated_dir
    output_dir = config.paths.subtitle_text_dir

    if single_file:
        stem = Path(single_file).stem.replace('_vi', '')
        srt_files = list(srt_dir.glob(f"{stem}*.srt"))
    else:
        srt_files = list(srt_dir.glob("*.srt"))

    if not srt_files:
        logger.warning(f"⚠️ Không tìm thấy file SRT nào trong: {srt_dir}")
        if progress_callback:
            progress_callback(1, 1, "Không có file SRT")
        return False

    total_files = len(srt_files)
    success = 0

    for i, srt_file in enumerate(srt_files, 1):
        if progress_callback:
            progress_callback(i - 1, total_files, f"Extract text {i}/{total_files}: {srt_file.name[:20]}")

        try:
            content = read_text_file(srt_file)

            text_content = extract_subtitle_text(content)
            output_name = srt_file.stem.replace('_vi', '') + '_subtitle.txt'
            output_path = output_dir / output_name

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(text_content)

            success += 1
            if progress_callback:
                progress_callback(i, total_files, f"Tạo text: {output_name[:20]}")

        except Exception as e:
            logger.error(f"❌ Lỗi xử lý {srt_file.name}: {e}")
            if progress_callback:
                progress_callback(i, total_files, f"Thất bại: {srt_file.name[:20]}")

    return (success > 0)
