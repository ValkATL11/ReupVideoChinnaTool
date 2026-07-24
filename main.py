"""
main.py - Orchestrator chính của ReupVideoChinnaTool
Hiển thị tiến trình thời gian thực (Real-time progress bar) trên Terminal
Lưu log hệ thống tổng quan vào logs/main.log
Lưu log chi tiết nội bộ từng bước vào logs/modules/<ten_module>.log
"""

import sys
import argparse
import logging
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Thêm thư mục src vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from reup_tool.config import config
import reup_tool.downloader as downloader
import reup_tool.audio_converter as audio_converter
import reup_tool.transcriber as transcriber
import reup_tool.translator as translator
import reup_tool.subtitle_formatter as subtitle_formatter
import reup_tool.dubber as dubber
import reup_tool.video_merger as video_merger


def setup_logging():
    log_dir = PROJECT_ROOT / "logs"
    module_log_dir = log_dir / "modules"
    log_dir.mkdir(parents=True, exist_ok=True)
    module_log_dir.mkdir(parents=True, exist_ok=True)

    log_level_str = getattr(config, "log_level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Main Logger - chỉ ghi vào logs/main.log (không in chi tiết ra terminal)
    main_logger = logging.getLogger()
    main_logger.setLevel(log_level)
    main_logger.handlers.clear()

    main_fh = logging.FileHandler(log_dir / "main.log", encoding="utf-8")
    main_fh.setLevel(log_level)
    main_fh.setFormatter(formatter)
    main_logger.addHandler(main_fh)

    return log_dir, module_log_dir, formatter


def attach_module_file_logger(module_name: str, module_log_dir: Path, formatter: logging.Formatter):
    """Ghi log riêng cho từng module vào logs/modules/<module_name>.log"""
    handler = logging.FileHandler(module_log_dir / f"{module_name}.log", encoding="utf-8")
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)

    mod_logger = logging.getLogger(f"reup_tool.{module_name}")
    mod_logger.addHandler(handler)
    return mod_logger, handler


def detach_module_file_logger(mod_logger: logging.Logger, handler: logging.Handler):
    mod_logger.removeHandler(handler)
    handler.close()


class RealtimeProgressTracker:
    """Quản lý thanh tiến trình ASCII thời gian thực trên Terminal"""
    def __init__(self, total_steps: int = 7, bar_width: int = 25):
        self.total_steps = total_steps
        self.bar_width = bar_width
        self.current_step_idx = 0
        self.step_desc = ""

    def start_step(self, step_idx: int, step_desc: str):
        self.current_step_idx = step_idx
        self.step_desc = step_desc
        self.update_sub_progress(0, 1, "Bắt đầu...")

    def update_sub_progress(self, current: int, total: int, detail: str = ""):
        total = max(total, 1)
        sub_frac = min(max(current / total, 0.0), 1.0)
        overall_frac = (self.current_step_idx + sub_frac) / self.total_steps
        overall_percent = int(overall_frac * 100)

        filled_len = int(self.bar_width * overall_frac)
        bar = '█' * filled_len + '░' * (self.bar_width - filled_len)

        detail_clean = detail[:28] if detail else ""
        step_num = self.current_step_idx + 1

        line = f"\r📌 [{step_num}/{self.total_steps}] {self.step_desc:<25} [{bar}] {overall_percent:3d}% | {detail_clean:<28}"
        sys.stdout.write(line)
        sys.stdout.flush()

    def complete_step(self, step_desc: str):
        overall_frac = (self.current_step_idx + 1) / self.total_steps
        overall_percent = int(overall_frac * 100)
        filled_len = int(self.bar_width * overall_frac)
        bar = '█' * filled_len + '░' * (self.bar_width - filled_len)

        step_num = self.current_step_idx + 1
        line = f"\r✅ [{step_num}/{self.total_steps}] {step_desc:<25} [{bar}] {overall_percent:3d}% | Hoàn tất!                                  \n"
        sys.stdout.write(line)
        sys.stdout.flush()


def run_pipeline(input_video: str = None, download_url: str = None):
    log_dir, module_log_dir, formatter = setup_logging()
    main_logger = logging.getLogger("main")

    # 1. HỎI LINK TẢI NẾU CHƯA CÓ VÀ KHÔNG CHỈ ĐỊNH INPUT FILE
    if not download_url and not input_video:
        print("\n" + "=" * 65)
        print("📥 TẢI VIDEO DOUYIN/TIKTOK (THỜI GIAN THỰC)")
        print("=" * 65)
        user_url = input("📌 Nhập link video cần tải (ấn Enter để dùng video có sẵn): ").strip()
        if user_url:
            download_url = user_url

    print("\n" + "=" * 70)
    print("🚀 REUP VIDEO PIPELINE ")
    print("=" * 70)
    main_logger.info("==================================================")
    main_logger.info("🚀 BẮT ĐẦU REUP VIDEO PIPELINE")
    main_logger.info("==================================================")

    single_file = Path(input_video) if input_video else None
    tracker = RealtimeProgressTracker(total_steps=7, bar_width=25)

    pipeline_steps = [
        ("downloader", "Downloader (Tải video)", lambda cb: downloader.process_all(url=download_url, progress_callback=cb) if download_url else downloader.process_all(url=None, progress_callback=cb)),
        ("audio_converter", "Audio Converter", lambda cb: audio_converter.process_all(single_file=single_file, progress_callback=cb)),
        ("transcriber", "Transcriber (Audio->SRT)", lambda cb: transcriber.process_all(single_file=single_file, progress_callback=cb)),
        ("translator", "Translator (Dịch SRT)", lambda cb: translator.process_all(single_file=single_file, progress_callback=cb)),
        ("subtitle_formatter", "Subtitle Formatter", lambda cb: subtitle_formatter.process_all(single_file=single_file, progress_callback=cb)),
        ("dubber", "Dubber (Lồng tiếng AI)", lambda cb: dubber.process_all(single_file=single_file, progress_callback=cb)),
        ("video_merger", "Video Merger (Ghép lại)", lambda cb: video_merger.process_all(single_file=single_file, progress_callback=cb)),
    ]

    total_steps = len(pipeline_steps)

    for step_idx, (mod_name, step_desc, step_func) in enumerate(pipeline_steps):
        tracker.start_step(step_idx, step_desc)
        main_logger.info(f"▶️ [BƯỚC {step_idx + 1}/{total_steps}] {step_desc} - Bắt đầu")

        mod_logger, handler = attach_module_file_logger(mod_name, module_log_dir, formatter)

        def make_callback(s_idx=step_idx):
            def cb(current, total, detail=""):
                tracker.update_sub_progress(current, total, detail)
            return cb

        try:
            res = step_func(make_callback(step_idx))
            detach_module_file_logger(mod_logger, handler)

            if res is False:
                sys.stdout.write("\n")
                print(f"❌ [BƯỚC {step_idx + 1}/{total_steps}] {step_desc} thất bại! Kiểm tra log: logs/modules/{mod_name}.log")
                main_logger.error(f"❌ [BƯỚC {step_idx + 1}/{total_steps}] {step_desc} thất bại!")
                sys.exit(1)

            tracker.complete_step(step_desc)
            main_logger.info(f"✅ [BƯỚC {step_idx + 1}/{total_steps}] {step_desc} hoàn tất!")

        except Exception as e:
            detach_module_file_logger(mod_logger, handler)
            sys.stdout.write("\n")
            print(f"❌ [BƯỚC {step_idx + 1}/{total_steps}] Ngoại lệ tại {step_desc}: {e}")
            main_logger.exception(f"❌ Ngoại lệ tại module {mod_name}: {e}")
            sys.exit(1)

    print("\n" + "=" * 70)
    print("🎉 TOÀN BỘ PIPELINE HOÀN THÀNH THÀNH CÔNG! [█████████████████████████] 100%")
    print("📁 Kết quả lưu tại: assets/output/")
    print("📄 Chi tiết log hệ thống: logs/main.log & logs/modules/")
    print("=" * 70 + "\n")
    main_logger.info("🎉 TOÀN BỘ PIPELINE HOÀN THÀNH THÀNH CÔNG!")


def main():
    parser = argparse.ArgumentParser(description="ReupVideoChinnaTool - Video Processing Pipeline")
    parser.add_argument("--input", type=str, help="Tên hoặc đường dẫn file MP4 đơn lẻ trong assets/original_video/")
    parser.add_argument("--url", type=str, help="URL Douyin/TikTok để tải video mới trước khi xử lý")

    args = parser.parse_args()
    run_pipeline(input_video=args.input, download_url=args.url)


if __name__ == "__main__":
    main()
