"""
audio_extractor.py
------------------
Module trích xuất audio từ video bằng FFmpeg.
Tự động đặt tên theo format: PRJ-YYMMDD-XXXX_Oaudio.*
Lưu vào thư mục Original_audios
"""

import re
import subprocess
import logging
import time
import secrets
import string
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, List, Dict, Any
from concurrent.futures import ProcessPoolExecutor, as_completed

# ----------------------------------------------------------------------
# Cấu hình logging
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Định nghĩa đường dẫn
# ----------------------------------------------------------------------
BASE_DIR = Path.cwd()
VIDEO_DIR = BASE_DIR / "original_videos"
AUDIO_DIR = BASE_DIR / "original_audios"


# ----------------------------------------------------------------------
# Project ID Manager (Tích hợp từ downloader)
# ----------------------------------------------------------------------

class ProjectIDManager:
    """Manages project IDs for consistent file naming."""
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path.cwd() / ".project_id"
        self._project_id: Optional[str] = None
    
    def generate(self) -> str:
        """Generate a new project ID."""
        date_str = datetime.now().strftime("%y%m%d")
        chars = string.ascii_uppercase + string.digits
        random_str = ''.join(secrets.choice(chars) for _ in range(4))
        return f"PRJ-{date_str}-{random_str}"
    
    def get(self) -> str:
        """Get or create a project ID."""
        if self._project_id:
            return self._project_id
        
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    self._project_id = f.read().strip()
                    return self._project_id
            except Exception:
                pass
        
        self._project_id = self.generate()
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, 'w') as f:
                f.write(self._project_id)
        except Exception:
            pass
        
        return self._project_id


# ----------------------------------------------------------------------
# Audio Extractor
# ----------------------------------------------------------------------

class FFmpegExtractor:
    """
    Trích xuất audio từ video bằng FFmpeg.
    Tự động đặt tên theo format: PRJ-YYMMDD-XXXX_Oaudio.*
    """
    
    def __init__(self, output_dir: Union[str, Path] = AUDIO_DIR, **defaults):
        self.output_dir = Path(output_dir)
        self.project_manager = ProjectIDManager()
        self.defaults = {
            'sample_rate': 44100,
            'channels': 'stereo',
            'normalize': True,
            'trim_metadata': True,
            'bitrate': '192k',
            'overwrite': False,
            'output_format': 'mp3',
            'fast_copy': False,
        }
        self.defaults.update(defaults)
        self._check_ffmpeg()
    
    def _check_ffmpeg(self):
        """Kiểm tra FFmpeg có sẵn trong PATH không."""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            logger.info("FFmpeg da san sang")
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("FFmpeg khong duoc tim thay. Vui long cai dat FFmpeg va them vao PATH.")
    
    def _get_output_filename(self, input_path: Path) -> str:
        """
        Tạo tên file output theo format: PRJ-YYMMDD-XXXX_Oaudio.*
        """
        project_id = self.project_manager.get()
        return f"{project_id}_Oaudio.mp3"
    
    def _build_command(self, input_path: Path, output_path: Path, options: Dict[str, Any]) -> list:
        """Tạo lệnh FFmpeg tối ưu tốc độ."""
        cmd = ['ffmpeg', '-nostdin', '-i', str(input_path), '-vn']
        
        # Ghi đè file
        cmd.append('-y' if options.get('overwrite', self.defaults['overwrite']) else '-n')
        
        # Chế độ stream copy (siêu tốc)
        if options.get('fast_copy', self.defaults['fast_copy']):
            cmd += ['-c:a', 'copy', str(output_path)]
            return cmd
        
        # Chế độ mã hóa lại
        filters = []
        if options.get('normalize', self.defaults['normalize']):
            filters.append('loudnorm=I=-16:LRA=11:TP=-1.5')
        
        channels = options.get('channels', self.defaults['channels'])
        if channels == 'mono':
            filters.append('ac=1')
        elif channels != 'stereo':
            raise ValueError(f"Channels khong hop le: {channels}")
        
        if filters:
            cmd += ['-af', ','.join(filters)]
        
        sr = options.get('sample_rate', self.defaults['sample_rate'])
        if sr:
            cmd += ['-ar', str(sr)]
        
        if options.get('trim_metadata', self.defaults['trim_metadata']):
            cmd += ['-map_metadata', '-1']
        
        bitrate = options.get('bitrate', self.defaults['bitrate'])
        output_format = options.get('output_format', self.defaults['output_format'])
        
        cmd += ['-b:a', bitrate, '-f', output_format, str(output_path)]
        return cmd
    
    def extract(self, video_path: Union[str, Path], **options) -> Optional[Path]:
        """
        Trích xuất audio từ video.
        
        Args:
            video_path: Đường dẫn đến file video
            **options: Tùy chọn FFmpeg
            
        Returns:
            Path đến file audio đã trích xuất, hoặc None nếu thất bại
        """
        video_path = Path(video_path)
        if not video_path.exists():
            logger.error(f"Video khong ton tai: {video_path}")
            return None
        
        final_options = {**self.defaults, **options}
        
        # Tạo tên file output theo format PRJ-YYMMDD-XXXX_Oaudio.mp3
        output_filename = self._get_output_filename(video_path)
        output_path = self.output_dir / output_filename
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Kiểm tra file đã tồn tại
        if output_path.exists() and output_path.stat().st_size > 0 and not final_options['overwrite']:
            logger.info(f"Audio da ton tai: {output_path.name}")
            return output_path
        
        cmd = self._build_command(video_path, output_path, final_options)
        
        # Tính timeout dựa trên dung lượng file
        file_size_mb = video_path.stat().st_size / (1024 * 1024)
        dynamic_timeout = max(60, int(file_size_mb * 0.5) + 60)
        
        start_time = time.time()
        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=dynamic_timeout
            )
            elapsed = time.time() - start_time
            size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"Trich xuat thanh cong: {output_path.name} ({size_mb:.2f} MB, {elapsed:.2f}s)")
            return output_path
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg loi [{video_path.name}]: {e.stderr[-200:] if e.stderr else ''}")
            return None
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout ({dynamic_timeout}s) khi xu ly: {video_path.name}")
            return None


# Worker function cho ProcessPoolExecutor
def _worker_extract(task_data):
    video_path, output_dir, options = task_data
    extractor = FFmpegExtractor(output_dir)
    return extractor.extract(video_path, **options)


class AudioExtractor:
    """
    Audio Extractor với hỗ trợ đa tiến trình.
    """
    
    def __init__(self, output_dir: Union[str, Path] = AUDIO_DIR, **ffmpeg_kwargs):
        self.output_dir = Path(output_dir)
        self.ffmpeg_kwargs = ffmpeg_kwargs
        self.project_manager = ProjectIDManager()
    
    def extract(self, video_path: Union[str, Path], **options) -> Optional[Path]:
        """Trích xuất audio từ 1 video."""
        opts = {**self.ffmpeg_kwargs, **options}
        extractor = FFmpegExtractor(self.output_dir, **opts)
        return extractor.extract(video_path, **opts)
    
    def extract_all(
        self,
        video_dir: Optional[Union[str, Path]] = None,
        pattern: str = "*.mp4",
        max_workers: int = 2,
        **options
    ) -> List[Path]:
        """
        Trích xuất audio từ tất cả video trong thư mục.
        
        Args:
            video_dir: Thư mục chứa video (mặc định: original_videos)
            pattern: Pattern để lọc file (mặc định: *.mp4)
            max_workers: Số tiến trình song song
            **options: Tùy chọn FFmpeg
            
        Returns:
            List các file audio đã trích xuất thành công
        """
        video_dir = Path(video_dir) if video_dir else VIDEO_DIR
        if not video_dir.exists():
            logger.error(f"Thu muc video khong ton tai: {video_dir}")
            return []
        
        video_files = list(video_dir.glob(pattern))
        if not video_files:
            logger.warning(f"Khong tim thay file video nao trong {video_dir}")
            return []
        
        logger.info(f"Tim thay {len(video_files)} video. Bat dau trich xuat (Workers: {max_workers})...")
        successful = []
        combined_options = {**self.ffmpeg_kwargs, **options}
        
        if max_workers > 1:
            tasks = [(v, self.output_dir, combined_options) for v in video_files]
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_worker_extract, task): task[0] for task in tasks}
                for future in as_completed(futures):
                    res = future.result()
                    if res:
                        successful.append(res)
        else:
            for v in video_files:
                res = self.extract(v, **combined_options)
                if res:
                    successful.append(res)
        
        logger.info(f"Hoan tat! Da trich xuat {len(successful)}/{len(video_files)} file audio.")
        return successful
    
    def extract_by_project_id(self, project_id: str, video_path: Union[str, Path]) -> Optional[Path]:
        """
        Trích xuất audio với project_id cụ thể.
        File output sẽ có tên: {project_id}_Oaudio.mp3
        """
        video_path = Path(video_path)
        if not video_path.exists():
            logger.error(f"Video khong ton tai: {video_path}")
            return None
        
        output_path = self.output_dir / f"{project_id}_Oaudio.mp3"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info(f"Audio da ton tai: {output_path.name}")
            return output_path
        
        # Tạo extractor với project_id cụ thể
        extractor = FFmpegExtractor(self.output_dir)
        # Override project_id
        extractor.project_manager._project_id = project_id
        
        return extractor.extract(video_path)


# ----------------------------------------------------------------------
# Convenience Functions
# ----------------------------------------------------------------------

def extract_audio(
    video_path: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    **options
) -> Optional[Path]:
    """
    Convenience function để trích xuất audio từ video.
    
    Args:
        video_path: Đường dẫn đến video
        output_dir: Thư mục output (mặc định: original_audios)
        **options: Tùy chọn FFmpeg
    
    Returns:
        Path đến file audio, hoặc None nếu thất bại
    """
    output_dir = Path(output_dir) if output_dir else AUDIO_DIR
    extractor = AudioExtractor(output_dir)
    return extractor.extract(video_path, **options)


def extract_all_audios(
    video_dir: Optional[Union[str, Path]] = None,
    output_dir: Optional[Union[str, Path]] = None,
    pattern: str = "*.mp4",
    max_workers: int = 2,
    **options
) -> List[Path]:
    """
    Convenience function để trích xuất audio từ tất cả video.
    """
    video_dir = Path(video_dir) if video_dir else VIDEO_DIR
    output_dir = Path(output_dir) if output_dir else AUDIO_DIR
    extractor = AudioExtractor(output_dir)
    return extractor.extract_all(video_dir, pattern, max_workers, **options)


# ----------------------------------------------------------------------
# CLI Interface
# ----------------------------------------------------------------------

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Audio Extractor - Trich xuat audio tu video',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Trich xuat audio tu 1 video
  python audio_extractor.py --single "original_videos/PRJ-260729-SUMB_Ovideo.mp4"
  
  # Trich xuat tat ca video trong thu muc
  python audio_extractor.py
  
  # Trich xuat voi custom output
  python audio_extractor.py --output ./my_audios --single "video.mp4"
  
  # Su dung fast copy (khong re-encode, rat nhanh)
  python audio_extractor.py --fast-copy --single "video.mp4"
        """
    )
    
    parser.add_argument('--single', type=str, help='Trich xuat 1 video cu the')
    parser.add_argument('--output', type=str, default='original_audios', help='Thu muc output (default: original_audios)')
    parser.add_argument('--sample-rate', type=int, default=44100, help='Sample rate (default: 44100)')
    parser.add_argument('--channels', choices=['mono', 'stereo'], default='stereo', help='Channels (default: stereo)')
    parser.add_argument('--no-normalize', action='store_false', dest='normalize', help='Khong normalize audio')
    parser.add_argument('--fast-copy', action='store_true', help='Stream copy (khong re-encode, rat nhanh)')
    parser.add_argument('--bitrate', default='192k', help='Bitrate (default: 192k)')
    parser.add_argument('--overwrite', action='store_true', help='Ghi de file da ton tai')
    parser.add_argument('--max-workers', type=int, default=2, help='So tien trinh song song (default: 2)')
    parser.add_argument('--pattern', default='*.mp4', help='Pattern loc file (default: *.mp4)')
    
    args = parser.parse_args()
    
    # Tao thu muc output
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Tao extractor
    extractor = AudioExtractor(
        output_dir,
        sample_rate=args.sample_rate,
        channels=args.channels,
        normalize=args.normalize,
        bitrate=args.bitrate,
        overwrite=args.overwrite,
        fast_copy=args.fast_copy
    )
    
    if args.single:
        # Trich xuat 1 video
        video_path = Path(args.single)
        if not video_path.exists():
            video_path = VIDEO_DIR / args.single
        if not video_path.exists():
            print(f"Loi: Khong tim thay video: {args.single}")
            return
        
        result = extractor.extract(video_path)
        if result:
            print(f"\n Thanh cong! Audio: {result}")
        else:
            print("\n That bai!")
    else:
        # Trich xuat tat ca video
        results = extractor.extract_all(
            video_dir=VIDEO_DIR,
            pattern=args.pattern,
            max_workers=args.max_workers
        )
        print(f"\n Hoan tat! Da trich xuat {len(results)} file audio.")


if __name__ == '__main__':
    main()