# src/reup_tool/video_merger.py
import os
import re
import subprocess
import tempfile
import shutil
import logging
from pathlib import Path
from typing import Optional, Callable
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
import pysrt

from reup_tool.config import config
from reup_tool.utils import read_text_file

logger = logging.getLogger(__name__)


class VideoAudioMerger:
    def __init__(self):
        self.video_dir = config.paths.video_dir
        self.srt_dir = config.paths.translated_dir
        self.audio_dir = config.paths.dubbing_dir
        self.output_dir = config.paths.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cfg = config.video_merger

    def find_video(self, video_name: Optional[str] = None) -> Optional[Path]:
        video_ext = self.cfg.suffix.video_ext
        video_files = list(self.video_dir.glob(f"*{video_ext}"))
        if not video_files:
            return None
        if video_name:
            for video in video_files:
                if video.stem == video_name:
                    return video
            return None
        return video_files[0]

    def find_srt(self, video_name: str) -> Optional[Path]:
        srt_suffix = self.cfg.suffix.srt_suffix
        srt_ext = self.cfg.suffix.srt_ext
        patterns = [
            f"{video_name}{srt_suffix}{srt_ext}",
            f"{video_name}{srt_ext}",
            f"*{srt_suffix}{srt_ext}",
        ]
        for pattern in patterns:
            srt_files = list(self.srt_dir.glob(pattern))
            if srt_files:
                return srt_files[0]
        all_srt = list(self.srt_dir.glob(f"*{srt_ext}"))
        return all_srt[0] if all_srt else None

    def find_audio_folder(self, video_name: str) -> Optional[Path]:
        audio_folder = self.audio_dir / video_name
        return audio_folder if audio_folder.exists() else None

    def parse_srt_with_pysrt(self, srt_path: Path):
        tmp_path = None
        try:
            content = read_text_file(srt_path).replace('\r\n', '\n').replace('\r', '\n')
            # Write a normalized UTF-8 temp copy so pysrt can re-read it safely
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.srt', encoding='utf-8', delete=False
            ) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            if '\n\n' in content:
                subs = pysrt.open(tmp_path, encoding='utf-8')
                segments = []
                for sub in subs:
                    segments.append({
                        'index': sub.index,
                        'start': sub.start.ordinal / 1000,
                        'end': sub.end.ordinal / 1000,
                        'duration': (sub.end.ordinal - sub.start.ordinal) / 1000,
                        'text': sub.text.replace('\n', ' ').strip()
                    })
                return segments
            else:
                return self.parse_srt_no_empty_lines(content)
        except Exception:
            return self.parse_srt_manual(srt_path)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def parse_srt_no_empty_lines(self, content: str):
        lines = content.split('\n')
        segments = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.isdigit():
                idx = int(line)
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                if i < len(lines):
                    timestamp_line = lines[i].strip()
                    i += 1
                    if '-->' in timestamp_line:
                        parts = timestamp_line.split('-->')
                        if len(parts) == 2:
                            start_str = parts[0].strip()
                            end_str = parts[1].strip()
                            while i < len(lines) and not lines[i].strip():
                                i += 1
                            text_lines = []
                            while i < len(lines):
                                next_line = lines[i].strip()
                                if not next_line or next_line.isdigit() or '-->' in next_line:
                                    break
                                text_lines.append(next_line)
                                i += 1
                            segments.append({
                                'index': idx,
                                'start': self.srt_to_seconds(start_str),
                                'end': self.srt_to_seconds(end_str),
                                'duration': self.srt_to_seconds(end_str) - self.srt_to_seconds(start_str),
                                'text': ' '.join(text_lines)
                            })
                            continue
            else:
                i += 1
        return segments

    def parse_srt_manual(self, srt_path: Path):
        content = read_text_file(srt_path).replace('\r\n', '\n').replace('\r', '\n')
        pattern = r'(\d+)\n([\d:,]+)\s*-->\s*([\d:,]+)\n(.+?)(?=\n\d+\n|\Z)'
        matches = re.findall(pattern, content, re.DOTALL)
        segments = []
        for match in matches:
            segments.append({
                'index': int(match[0]),
                'start': self.srt_to_seconds(match[1]),
                'end': self.srt_to_seconds(match[2]),
                'duration': self.srt_to_seconds(match[2]) - self.srt_to_seconds(match[1]),
                'text': match[3].strip().replace('\n', ' ')
            })
        return segments

    def srt_to_seconds(self, timestamp: str) -> float:
        timestamp = timestamp.replace(',', '.')
        parts = timestamp.split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return 0.0

    def find_audio_file(self, audio_folder: Path, index: int) -> Optional[Path]:
        audio_ext = self.cfg.suffix.audio_ext
        patterns = [
            f"dong_{index:03d}{audio_ext}",
            f"dong_{index}{audio_ext}",
            f"*_{index:03d}{audio_ext}",
            f"*_{index}{audio_ext}",
        ]
        for pattern in patterns:
            audio_files = list(audio_folder.glob(pattern))
            if audio_files:
                return audio_files[0]
        return None

    def load_audio_safe(self, audio_path: Path) -> AudioSegment:
        try:
            return AudioSegment.from_file(audio_path)
        except Exception:
            return AudioSegment.silent(duration=500)

    def adjust_audio_to_duration(self, audio: AudioSegment, target_duration_ms: int) -> AudioSegment:
        current_duration = len(audio)
        if current_duration > target_duration_ms:
            return audio[:target_duration_ms]
        elif current_duration < target_duration_ms:
            return audio + AudioSegment.silent(duration=target_duration_ms - current_duration)
        return audio

    def extract_audio(self, video_path: Path, output_path: Path):
        cmd = [
            'ffmpeg', '-y', '-i', str(video_path),
            '-vn', '-acodec', 'pcm_s16le',
            '-ar', '44100', '-ac', '2',
            str(output_path)
        ]
        subprocess.run(cmd, check=True, capture_output=True, encoding='utf-8', errors='ignore')

    def get_media_duration_ms(self, media_path: Path) -> int:
        """Lấy tổng thời lượng (ms) của video/audio bằng ffprobe."""
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(media_path)
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding='utf-8', errors='ignore', check=True
            )
            return int(float(result.stdout.strip()) * 1000)
        except Exception:
            return 0

    # ── Helper: video dimensions via ffprobe ─────────────────────────────────

    def get_video_dimensions(self, video_path: Path):
        """Return (width, height) of a video file, falling back to 1920×1080."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "default=noprint_wrappers=1",
                str(video_path)
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="ignore", timeout=15
            )
            w, h = 1920, 1080
            for line in result.stdout.splitlines():
                if line.startswith("width="):
                    w = int(line.split("=")[1])
                elif line.startswith("height="):
                    h = int(line.split("=")[1])
            return w, h
        except Exception:
            return 1920, 1080

    # ── Helper: seconds → ASS timestamp ─────────────────────────────────────

    @staticmethod
    def _sec_to_ass_ts(seconds: float) -> str:
        """Convert float seconds → ASS timestamp H:MM:SS.cc (centiseconds)."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int(round((seconds % 1) * 100))
        if cs >= 100:
            cs = 99
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    # ── SRT → ASS converter with precise \\pos() positioning ────────────────

    def srt_to_ass(self, srt_path: Path, ass_path: Path, video_w: int, video_h: int) -> bool:
        """
        Convert an SRT file to ASS and embed \\an5\\pos(x,y) on every dialogue
        line so that the user's dragged position is honoured exactly.

        The ASS PlayResX/Y is set to the actual video dimensions, so the pixel
        coordinates map 1-to-1 without any scaling.
        """
        try:
            sub_cfg = self.cfg.subtitle

            # Pixel position from percentage
            x_px = int(video_w * sub_cfg.pos_x_pct / 100.0)
            y_px = int(video_h * sub_cfg.pos_y_pct / 100.0)
            # \an5 = anchor at text centre; \pos() sets that centre in pixels
            pos_override = f"{{\\an5\\pos({x_px},{y_px})}}"

            segments = self.parse_srt_with_pysrt(srt_path)
            if not segments:
                return False

            # ASS header
            ass_header = (
                "[Script Info]\n"
                "ScriptType: v4.00+\n"
                f"PlayResX: {video_w}\n"
                f"PlayResY: {video_h}\n"
                "Timer: 100.0000\n"
                "\n"
                "[V4+ Styles]\n"
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding\n"
                f"Style: Default,"
                f"{sub_cfg.font_name},"
                f"{sub_cfg.font_size},"
                f"{sub_cfg.primary_color},"
                f"{sub_cfg.secondary_color},"
                f"{sub_cfg.outline_color},"
                f"{sub_cfg.back_color},"
                f"{sub_cfg.bold},"
                f"{sub_cfg.italic},"
                f"{sub_cfg.underline},"
                f"0,"           # StrikeOut
                f"100,100,"     # ScaleX, ScaleY
                f"0,"           # Spacing
                f"0,"           # Angle
                f"{sub_cfg.border_style},"
                f"{sub_cfg.outline_width},"
                f"{sub_cfg.shadow},"
                f"{sub_cfg.alignment},"
                f"{sub_cfg.margin_l},"
                f"{sub_cfg.margin_r},"
                f"{sub_cfg.margin_v},"
                f"1\n"          # Encoding
                "\n"
                "[Events]\n"
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            )

            lines = []
            for seg in segments:
                start = self._sec_to_ass_ts(seg["start"])
                end   = self._sec_to_ass_ts(seg["end"])
                text  = seg.get("text", "").replace("\n", "\\N")
                lines.append(
                    f"Dialogue: 0,{start},{end},Default,,0,0,0,,{pos_override}{text}"
                )

            ass_path.write_text(
                ass_header + "\n".join(lines) + "\n",
                encoding="utf-8-sig"     # BOM helps some FFmpeg builds on Windows
            )
            return True
        except Exception as e:
            logger.error(f"❌ SRT→ASS conversion failed: {e}")
            return False

    # ── Main merge function ──────────────────────────────────────────────────

    def merge_video_audio_subtitle(self, video_path: Path, audio_path: Path, srt_path: Path, output_path: Path) -> bool:
        try:
            video_w, video_h = self.get_video_dimensions(video_path)

            temp_dir = Path(tempfile.mkdtemp())
            temp_video  = temp_dir / "video.mp4"
            temp_audio  = temp_dir / "audio.mp3"
            temp_ass    = temp_dir / "sub.ass"
            temp_srt    = temp_dir / "sub.srt"   # fallback only
            temp_output = temp_dir / "output.mp4"

            shutil.copy2(video_path, temp_video)
            shutil.copy2(audio_path, temp_audio)

            # Try to produce a styled ASS file with exact \pos() coordinates.
            # Fall back to a plain SRT copy when conversion fails.
            use_ass = self.srt_to_ass(srt_path, temp_ass, video_w, video_h)
            if use_ass:
                subtitle_filter = "subtitles=sub.ass"
            else:
                shutil.copy2(srt_path, temp_srt)
                subtitle_filter = "subtitles=sub.srt"

            v_cfg = self.cfg.video
            a_cfg = self.cfg.audio

            cmd = [
                'ffmpeg', '-y',
                '-i', str(temp_video),
                '-i', str(temp_audio),
                '-filter_complex',
                f"{subtitle_filter},setsar=1",
                '-map', '1:a:0',
                '-vcodec', v_cfg.codec,
                '-pix_fmt', v_cfg.pix_fmt,
                '-r', str(v_cfg.frame_rate),
                '-g', str(v_cfg.gop_size),
                '-b:v', v_cfg.bitrate,
                '-profile:v', v_cfg.profile,
                '-level', v_cfg.level,
                '-acodec', a_cfg.codec,
                '-b:a', a_cfg.bitrate,
                '-ar', str(a_cfg.sample_rate),
                '-preset', v_cfg.preset,
                str(temp_output)
            ]

            result = subprocess.run(
                cmd,
                cwd=str(temp_dir),
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=300
            )

            if result.returncode == 0 and temp_output.exists():
                shutil.copy2(temp_output, output_path)
                success = True
            else:
                logger.error(f"FFmpeg stderr:\n{result.stderr[-2000:]}")
                success = False

            shutil.rmtree(temp_dir, ignore_errors=True)
            return success
        except Exception as e:
            logger.error(f"❌ merge_video_audio_subtitle error: {e}")
            return False

    def process_video(
        self,
        video_name: Optional[str] = None,
        known_video_path: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        try:
            # Use direct path when available (e.g., file outside video_dir)
            if known_video_path and known_video_path.exists():
                video_path = known_video_path
                video_name = video_path.stem
            else:
                video_path = self.find_video(video_name)
            if not video_path:
                return False

            video_name = video_path.stem
            srt_path = self.find_srt(video_name)
            if not srt_path:
                return False

            audio_folder = self.find_audio_folder(video_name)
            if not audio_folder:
                return False

            segments = self.parse_srt_with_pysrt(srt_path)
            if not segments:
                return False

            temp_dir = Path(tempfile.mkdtemp())

            if progress_callback:
                progress_callback(1, 4, "Trích xuất audio gốc...")

            original_audio = temp_dir / "original_audio.wav"
            self.extract_audio(video_path, original_audio)

            full_audio = AudioSegment.from_file(original_audio)
            full_audio = full_audio - (20 - 20 * self.cfg.original_volume)

            # Video's audio track có thể ngắn hơn video thực tế (lệch audio/video
            # khi tải về). Nếu không đệm cho khớp, các câu phụ đề có mốc thời gian
            # vượt quá độ dài audio gốc sẽ bị dồn cục lại thay vì chèn đúng vị trí,
            # khiến phần lồng tiếng phía sau bị mất hoàn toàn khi ghép với ffmpeg.
            video_duration_ms = self.get_media_duration_ms(video_path)
            if video_duration_ms > len(full_audio):
                full_audio = full_audio + AudioSegment.silent(
                    duration=video_duration_ms - len(full_audio)
                )

            segments_sorted = sorted(segments, key=lambda x: x['start'], reverse=True)
            total_segs = len(segments_sorted)

            for idx, seg in enumerate(segments_sorted, 1):
                if progress_callback:
                    progress_callback(1 + int((idx / max(total_segs, 1)) * 2), 4, f"Mix audio {idx}/{total_segs}")

                audio_file = self.find_audio_file(audio_folder, seg['index'])
                if not audio_file:
                    continue

                new_audio = self.load_audio_safe(audio_file)
                new_audio = new_audio - (20 - 20 * self.cfg.new_volume)
                target_duration_ms = int(seg['duration'] * 1000)
                new_audio = self.adjust_audio_to_duration(new_audio, target_duration_ms)

                if len(new_audio) > 100:
                    new_audio = new_audio.fade_in(self.cfg.fade_in_ms).fade_out(self.cfg.fade_out_ms)

                start_ms = int(seg['start'] * 1000)

                # Bảo vệ: nếu vị trí chèn vượt quá độ dài audio hiện có (ví dụ SRT
                # có mốc thời gian trễ hơn cả audio gốc + đệm), đệm thêm khoảng
                # lặng trước khi chèn thay vì để bị dồn cục vào cuối track.
                if start_ms > len(full_audio):
                    full_audio = full_audio + AudioSegment.silent(
                        duration=start_ms - len(full_audio)
                    )

                full_audio = full_audio[:start_ms] + new_audio + full_audio[start_ms + len(new_audio):]

            # Đảm bảo track cuối cùng khớp đúng thời lượng video: cắt nếu dư,
            # đệm lặng nếu thiếu (đề phòng đoạn thoại cuối kéo dài quá video).
            if video_duration_ms > 0:
                if len(full_audio) > video_duration_ms:
                    full_audio = full_audio[:video_duration_ms]
                elif len(full_audio) < video_duration_ms:
                    full_audio = full_audio + AudioSegment.silent(
                        duration=video_duration_ms - len(full_audio)
                    )

            mixed_audio_path = temp_dir / "mixed_audio.mp3"
            full_audio.export(mixed_audio_path, format="mp3")

            if progress_callback:
                progress_callback(3, 4, "FFmpeg merge video, audio & sub...")

            final_output = self.output_dir / f"{video_name}_final{self.cfg.suffix.video_ext}"
            success = self.merge_video_audio_subtitle(video_path, mixed_audio_path, srt_path, final_output)

            shutil.rmtree(temp_dir, ignore_errors=True)

            if progress_callback and success:
                progress_callback(4, 4, f"Đã xuất video: {final_output.name[:20]}")

            return success
        except Exception as e:
            logger.error(f"❌ Lỗi xử lý merge: {e}")
            return False

    def process_all_videos(
        self,
        single_file: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        if single_file:
            video_files = [Path(single_file)]
        else:
            video_files = list(self.video_dir.glob(f"*{self.cfg.suffix.video_ext}"))

        if not video_files:
            if progress_callback:
                progress_callback(1, 1, "Không tìm thấy video")
            return False

        success = 0
        for video in video_files:
            # Truyền known_video_path để process_video dùng đường dẫn trực tiếp
            # thay vì phụ thuộc find_video() — xử lý file ngoài video_dir
            if self.process_video(
                video_name=video.stem,
                known_video_path=video,
                progress_callback=progress_callback
            ):
                success += 1

        return (success > 0)


def process_all(
    single_file: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> bool:
    merger = VideoAudioMerger()
    return merger.process_all_videos(single_file=single_file, progress_callback=progress_callback)
