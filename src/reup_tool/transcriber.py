# src/reup_tool/transcriber.py
import os
import time
import logging
import json
from pathlib import Path
from typing import Optional, Callable
from groq import Groq

from reup_tool.config import config

logger = logging.getLogger(__name__)


class AudioToTextConverter:
    def __init__(self, api_key: str, model: str = "whisper-large-v3-turbo"):
        self.api_key = api_key
        self.client = Groq(api_key=api_key)
        self.model = model

    def transcribe_audio(self, audio_path, language="auto", response_format="verbose_json"):
        try:
            logger.info(f"Đang chuyển đổi: {os.path.basename(audio_path)}")
            with open(audio_path, "rb") as file:
                if language == "auto":
                    transcription = self.client.audio.transcriptions.create(
                        file=(os.path.basename(audio_path), file.read()),
                        model=self.model,
                        response_format=response_format,
                        timestamp_granularities=["segment"]
                    )
                else:
                    transcription = self.client.audio.transcriptions.create(
                        file=(os.path.basename(audio_path), file.read()),
                        model=self.model,
                        language=language,
                        response_format=response_format,
                        timestamp_granularities=["segment"]
                    )

            if response_format == "verbose_json":
                if hasattr(transcription, 'model_dump'):
                    data = transcription.model_dump()
                elif hasattr(transcription, '__dict__'):
                    data = transcription.__dict__
                else:
                    data = transcription

                if isinstance(data, dict):
                    result = {
                        "text": data.get("text", ""),
                        "language": data.get("language", language),
                        "duration": data.get("duration", 0),
                        "segments": []
                    }
                    segments = data.get("segments", [])
                    for segment in segments:
                        result["segments"].append({
                            "start": segment.get("start", 0) if isinstance(segment, dict) else segment.start,
                            "end": segment.get("end", 0) if isinstance(segment, dict) else segment.end,
                            "text": segment.get("text", "") if isinstance(segment, dict) else segment.text,
                            "tokens": segment.get("tokens", []) if isinstance(segment, dict) else getattr(segment, 'tokens', [])
                        })
                else:
                    result = {
                        "text": getattr(transcription, 'text', ''),
                        "language": getattr(transcription, 'language', language),
                        "duration": getattr(transcription, 'duration', 0),
                        "segments": []
                    }
                    segments = getattr(transcription, 'segments', [])
                    for segment in segments:
                        result["segments"].append({
                            "start": getattr(segment, 'start', 0),
                            "end": getattr(segment, 'end', 0),
                            "text": getattr(segment, 'text', ''),
                            "tokens": getattr(segment, 'tokens', [])
                        })

                logger.info(f"✓ Chuyển đổi thành công! Ngôn ngữ: {result['language']}, Độ dài: {len(result['text'])} ký tự")
                return result
            else:
                return {"text": str(transcription), "segments": []}
        except Exception as e:
            logger.error(f"Lỗi khi chuyển đổi: {e}")
            return None

    def save_transcription(self, result, output_path, format_type="txt"):
        if not result:
            return False
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if format_type == "txt":
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(result["text"])
            elif format_type == "json":
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
            elif format_type == "srt":
                with open(output_path, 'w', encoding='utf-8') as f:
                    segments = result.get("segments", [])
                    if not segments:
                        f.write("1\n00:00:00,000 --> 00:00:00,000\n" + f"{result['text'].strip()}\n\n")
                    else:
                        for i, segment in enumerate(segments, 1):
                            start = self._format_timestamp(segment["start"])
                            end = self._format_timestamp(segment["end"])
                            f.write(f"{i}\n{start} --> {end}\n{segment['text'].strip()}\n\n")
            logger.info(f"✓ Đã lưu: {output_path.name}")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi lưu file: {e}")
            return False

    def _format_timestamp(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def process_all(
    single_file: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> bool:
    audio_dir = config.paths.audio_dir
    srt_dir = config.paths.srt_dir

    if single_file:
        stem = Path(single_file).stem
        audio_files = list(audio_dir.glob(f"{stem}.*"))
    else:
        audio_files = list(audio_dir.glob("*.mp3")) or list(audio_dir.glob("*.wav")) or list(audio_dir.glob("*.m4a")) or list(audio_dir.glob("*.flac"))

    if not audio_files:
        logger.warning(f"Không tìm thấy file audio nào trong: {audio_dir}")
        if progress_callback:
            progress_callback(1, 1, "Không có file audio nào")
        return False

    total_files = len(audio_files)
    converter = AudioToTextConverter(config.groq_api_key, model=config.transcriber.model)

    success = 0
    for i, audio_file in enumerate(audio_files, 1):
        if progress_callback:
            progress_callback(i - 1, total_files, f"Groq Whisper {i}/{total_files}: {audio_file.name[:20]}")

        base_name = audio_file.stem
        srt_path = srt_dir / f"{base_name}.srt"

        if srt_path.exists() and srt_path.stat().st_size > 0:
            logger.info(f"⏭ File {srt_path.name} đã tồn tại, bỏ qua")
            success += 1
            if progress_callback:
                progress_callback(i, total_files, f"Đã có sẵn: {srt_path.name[:20]}")
            continue

        result = converter.transcribe_audio(str(audio_file), language=config.transcriber.language)
        if result:
            converter.save_transcription(result, srt_dir / f"{base_name}.txt", "txt")
            converter.save_transcription(result, srt_dir / f"{base_name}.json", "json")
            converter.save_transcription(result, srt_path, "srt")
            success += 1
            if progress_callback:
                progress_callback(i, total_files, f"Xong SRT: {base_name[:20]}")
        else:
            if progress_callback:
                progress_callback(i, total_files, f"Thất bại: {audio_file.name[:20]}")

    return (success > 0)
