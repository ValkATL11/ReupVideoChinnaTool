"""
ReupTool V3 — Automated Video Dubbing & Processing Workstation
===============================================================
Entry point for Desktop Application GUI (PySide6) and CLI Automation mode.

Usage:
  python main.py                     # Launch PySide6 Desktop GUI (Default)
  python main.py --cli --url "URL"   # Download & process URL in Headless CLI mode
  python main.py --cli -p "PROJ_ID"  # Process existing project in Headless CLI mode
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure src/ is in path when running as script
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Setup root logging
log_format = "%(asctime)s - [%(levelname)s] - [%(name)s]: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_PROJECT_ROOT / "app.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("ReupToolV3")


def run_cli_mode(project_id: str = None, url: str = None, local_file: str = None):
    """Run pipeline execution in headless CLI mode."""
    from app.core.project import ProjectManager, generate_project_id
    from app.core.pipeline import PipelineEngine

    logger.info("=" * 60)
    logger.info("        REUPTOOL V3 — HEADLESS CLI MODE")
    logger.info("=" * 60)

    pm = ProjectManager()

    if project_id:
        proj = pm.create_project(custom_id=project_id)
        source = url or local_file or ""
    elif url or local_file:
        proj = pm.create_project()
        source = url or local_file
    else:
        logger.error("Error: Please provide --url, --input, or --project ID for CLI mode.")
        sys.exit(1)

    logger.info("Active Project ID: %s", proj.project_id)

    def print_progress(step_key, cur, total, msg):
        pct = int((cur / total) * 100) if total > 0 else 0
        print(f"[{step_key}] ({pct}%) {msg}")

    def print_step_start(step_key, step_name):
        print(f"\n▶ STARTING STEP: {step_name} [{step_key}]")

    def print_step_finish(step_key, msg):
        print(f"✓ {msg}")

    def print_step_fail(step_key, err):
        print(f"❌ FAILED STEP [{step_key}]: {err}")

    engine = PipelineEngine(
        project=proj,
        source_input=source,
        on_step_start=print_step_start,
        on_progress=print_progress,
        on_step_finish=print_step_finish,
        on_step_fail=print_step_fail
    )

    success = engine.run()
    if success:
        print("\n" + "=" * 60)
        print("✅ PIPELINE COMPLETED SUCCESSFULLY!")
        print(f"📁 Output Video: {proj.final_output_path}")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("❌ PIPELINE FAILED! Check logs for details.")
        print("=" * 60)
        sys.exit(1)


def run_gui_mode():
    """Launch PySide6 Desktop GUI."""
    try:
        from PySide6.QtWidgets import QApplication
        from app.gui.main_window import MainWindow
        from app.gui.styles.theme import apply_theme
    except ImportError:
        logger.error("PySide6 is not installed! Please run: pip install PySide6")
        sys.exit(1)

    app = QApplication(sys.argv)
    apply_theme(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


def main():
    parser = argparse.ArgumentParser(
        description="ReupTool V3 — Automated Video Dubbing & Processing Workstation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Launch PySide6 GUI (Default)
  python main.py

  # Process video URL via Headless CLI
  python main.py --cli --url "https://www.douyin.com/video/123"

  # Process local file via Headless CLI
  python main.py --cli --input "D:/my_video.mp4" --project PRJ-260730-0001
        """
    )

    parser.add_argument("--cli", action="store_true", help="Run in Headless CLI mode instead of GUI")
    parser.add_argument("-p", "--project", type=str, help="Project ID (e.g. PRJ-260730-37TG)")
    parser.add_argument("-u", "--url", type=str, help="Video URL to download & process")
    parser.add_argument("-i", "--input", type=str, help="Local video file path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.cli or args.url or args.input or args.project:
        run_cli_mode(project_id=args.project, url=args.url, local_file=args.input)
    else:
        run_gui_mode()


if __name__ == "__main__":
    main()
