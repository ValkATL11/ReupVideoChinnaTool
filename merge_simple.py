# merge_simple.py
import os
import re
import subprocess
import tempfile
import shutil
from pathlib import Path
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

# ==================== CẤU HÌNH ====================
BASE_DIR = r"D:\Data_meno\Work\Develop_Project\My_apps\ReupToolV1"

# Cấu hình âm lượng
ORIGINAL_VOLUME = 0.3  # 30%
NEW_VOLUME = 0.9  # 90%

# Cấu hình chèn
FADE_IN = 30
FADE_OUT = 30

VIDEO_EXT = ".mp4"
SRT_EXT = ".srt"
AUDIO_EXT = ".mp3"

SRT_SUFFIX = "_vi"
# =================================================

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class VideoAudioMerger:
    def __init__(self, base_dir=BASE_DIR):
        self.base_dir = Path(base_dir)
        self.video_dir = self.base_dir / "mp4"
        self.srt_dir = self.base_dir / "translated"
        self.audio_dir = self.base_dir / "dubbing"
        self.output_dir = self.base_dir / "OUTPUT"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def find_video(self, video_name=None):
        video_files = list(self.video_dir.glob(f"*{VIDEO_EXT}"))
        if not video_files:
            logger.error(f"❌ Không tìm thấy video nào trong: {self.video_dir}")
            return None
        
        if video_name:
            for video in video_files:
                if video.stem == video_name:
                    return video
            logger.warning(f"⚠️ Không tìm thấy video: {video_name}")
            return None
        
        return video_files[0]
    
    def find_srt(self, video_name):
        patterns = [
            f"{video_name}{SRT_SUFFIX}{SRT_EXT}",
            f"{video_name}{SRT_EXT}",
            f"*{SRT_SUFFIX}{SRT_EXT}",
        ]
        
        for pattern in patterns:
            srt_files = list(self.srt_dir.glob(pattern))
            if srt_files:
                logger.info(f"📄 Tìm thấy SRT: {srt_files[0].name}")
                return srt_files[0]
        
        all_srt = list(self.srt_dir.glob(f"*{SRT_EXT}"))
        if all_srt:
            logger.warning(f"⚠️ Không tìm thấy SRT khớp với {video_name}")
            logger.info(f"📄 Sử dụng: {all_srt[0].name}")
            return all_srt[0]
        
        logger.error(f"❌ Không tìm thấy file SRT nào trong: {self.srt_dir}")
        return None
    
    def find_audio_folder(self, video_name):
        audio_folder = self.audio_dir / video_name
        if not audio_folder.exists():
            logger.error(f"❌ Không tìm thấy thư mục audio: {audio_folder}")
            return None
        return audio_folder
    
    def srt_to_seconds(self, timestamp):
        timestamp = timestamp.replace(',', '.')
        parts = timestamp.split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return 0
    
    def parse_srt(self, srt_path):
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        segments = []
        lines = content.split('\n')
        
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
                            start = self.srt_to_seconds(parts[0].strip())
                            end = self.srt_to_seconds(parts[1].strip())
                            
                            while i < len(lines) and not lines[i].strip():
                                i += 1
                            
                            text_lines = []
                            while i < len(lines):
                                next_line = lines[i].strip()
                                if not next_line:
                                    i += 1
                                    continue
                                if next_line.isdigit() or '-->' in next_line:
                                    break
                                text_lines.append(next_line)
                                i += 1
                            
                            text = ' '.join(text_lines)
                            text = re.sub(r'^Dòng\s*\d+:\s*', '', text)
                            
                            segments.append({
                                'index': idx,
                                'start': start,
                                'end': end,
                                'duration': end - start,
                                'text': text
                            })
                            continue
            else:
                i += 1
        
        logger.info(f"📊 Tìm thấy {len(segments)} segment trong SRT")
        return segments
    
    def find_audio_file(self, audio_folder, index):
        patterns = [
            f"dong_{index:03d}{AUDIO_EXT}",
            f"dong_{index}{AUDIO_EXT}",
            f"*_{index:03d}{AUDIO_EXT}",
            f"*_{index}{AUDIO_EXT}",
        ]
        
        for pattern in patterns:
            audio_files = list(audio_folder.glob(pattern))
            if audio_files:
                return audio_files[0]
        
        return None
    
    def load_audio_safe(self, audio_path):
        """Load audio an toàn, nếu lỗi thì tạo silence thay thế"""
        try:
            return AudioSegment.from_file(audio_path)
        except CouldntDecodeError as e:
            logger.warning(f"⚠️ File audio lỗi: {audio_path}")
            logger.warning(f"   Tạo silence thay thế (0.5s)")
            # Tạo silence 0.5s thay thế
            return AudioSegment.silent(duration=500)
        except Exception as e:
            logger.warning(f"⚠️ Không thể load {audio_path}: {e}")
            return AudioSegment.silent(duration=500)
    
    def adjust_audio_to_duration(self, audio, target_duration_ms):
        """Điều chỉnh audio để có độ dài chính xác"""
        current_duration = len(audio)
        
        if current_duration > target_duration_ms:
            return audio[:target_duration_ms]
        elif current_duration < target_duration_ms:
            silence_needed = target_duration_ms - current_duration
            silence = AudioSegment.silent(duration=silence_needed)
            return audio + silence
        return audio
    
    def extract_audio(self, video_path, output_path):
        cmd = [
            'ffmpeg', '-i', str(video_path),
            '-vn', '-acodec', 'pcm_s16le',
            '-ar', '44100', '-ac', '2',
            str(output_path)
        ]
        subprocess.run(cmd, check=True, capture_output=True)
    
    def process_video(self, video_name=None):
        try:
            video_path = self.find_video(video_name)
            if not video_path:
                return False
            
            video_name = video_path.stem
            logger.info("=" * 60)
            logger.info(f"📹 Video: {video_path.name}")
            
            srt_path = self.find_srt(video_name)
            if not srt_path:
                return False
            
            audio_folder = self.find_audio_folder(video_name)
            if not audio_folder:
                return False
            logger.info(f"🎵 Audio: {audio_folder}")
            
            segments = self.parse_srt(srt_path)
            
            if not segments:
                logger.error("❌ KHÔNG TÌM THẤY SEGMENT NÀO!")
                return False
            
            audio_files = list(audio_folder.glob(f"*{AUDIO_EXT}"))
            logger.info(f"📁 Tìm thấy {len(audio_files)} file audio")
            
            temp_dir = Path(tempfile.mkdtemp())
            
            original_audio = temp_dir / "original_audio.wav"
            logger.info("🎵 Đang trích xuất audio gốc...")
            self.extract_audio(video_path, original_audio)
            
            full_audio = AudioSegment.from_file(original_audio)
            full_audio = full_audio - (20 - 20 * ORIGINAL_VOLUME)
            logger.info(f"⏱️ Audio gốc: {len(full_audio)/1000:.2f}s")
            
            # Chèn từ CUỐI lên ĐẦU
            segments_sorted = sorted(segments, key=lambda x: x['start'], reverse=True)
            
            inserted_count = 0
            for seg in segments_sorted:
                audio_file = self.find_audio_file(audio_folder, seg['index'])
                
                if not audio_file:
                    logger.warning(f"⚠️ Không tìm thấy audio cho dòng {seg['index']}")
                    continue
                
                # Load audio an toàn (có xử lý lỗi)
                new_audio = self.load_audio_safe(audio_file)
                logger.info(f"📝 {audio_file.name}:")
                logger.info(f"    Độ dài gốc: {len(new_audio)/1000:.3f}s")
                
                # Điều chỉnh âm lượng
                new_audio = new_audio - (20 - 20 * NEW_VOLUME)
                
                # Điều chỉnh đúng duration
                target_duration_ms = int(seg['duration'] * 1000)
                logger.info(f"    Target duration: {seg['duration']:.3f}s")
                new_audio = self.adjust_audio_to_duration(new_audio, target_duration_ms)
                
                # Thêm fade
                if len(new_audio) > 100:
                    new_audio = new_audio.fade_in(FADE_IN).fade_out(FADE_OUT)
                
                # Chèn vào video
                start_ms = int(seg['start'] * 1000)
                logger.info(f"    Chèn vào: {seg['start']:.3f}s")
                
                before = full_audio[:start_ms]
                after = full_audio[start_ms + len(new_audio):]
                full_audio = before + new_audio + after
                inserted_count += 1
            
            logger.info(f"✅ Đã chèn {inserted_count}/{len(segments)} audio")
            
            mixed_audio_path = temp_dir / "mixed_audio.mp3"
            logger.info("💾 Đang lưu audio đã mix...")
            full_audio.export(mixed_audio_path, format="mp3")
            
            output_path = self.output_dir / f"{video_name}_final{VIDEO_EXT}"
            logger.info("🔗 Đang ghép audio vào video...")
            
            cmd = [
                'ffmpeg', '-i', str(video_path),
                '-i', str(mixed_audio_path),
                '-c:v', 'copy',
                '-map', '0:v:0',
                '-map', '1:a:0',
                '-shortest',
                str(output_path)
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            logger.info(f"✅ HOÀN THÀNH! Video đã lưu tại: {output_path}")
            logger.info("=" * 60)
            return True
            
        except Exception as e:
            logger.error(f"❌ Lỗi xử lý: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def process_all_videos(self):
        video_files = list(self.video_dir.glob(f"*{VIDEO_EXT}"))
        
        if not video_files:
            logger.warning(f"⚠️ Không tìm thấy video nào trong {self.video_dir}")
            return
        
        logger.info("=" * 60)
        logger.info(f"📁 Tìm thấy {len(video_files)} video")
        logger.info("=" * 60)
        
        success = 0
        for video in video_files:
            if self.process_video(video.stem):
                success += 1
        
        logger.info("=" * 60)
        logger.info(f"📊 KẾT QUẢ: ✅ {success}/{len(video_files)} video thành công")
        logger.info(f"📁 Output: {self.output_dir}")
        logger.info("=" * 60)

def main():
    merger = VideoAudioMerger()
    merger.process_all_videos()

if __name__ == "__main__":
    main()