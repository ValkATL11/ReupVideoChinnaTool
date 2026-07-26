"""
app.py - Main application window orchestrator.

Architecture:
  - Sidebar   → navigation
  - Content   → swappable panels (source, progress, subtitle editor, output, cleanup, settings)
  - Log panel → always visible at bottom
  - Pipeline  → runs in background thread; GUI stays fully responsive
  - Event queue → thread-safe communication
"""

import sys
import threading
import queue
import time
import logging
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

# Insert src into path so modules can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gui.theme import COLORS, FONTS, PIPELINE_STEPS
from gui.widgets.sidebar import Sidebar
from gui.widgets.log_panel import LogPanel
from gui.widgets.source_panel import SourcePanel
from gui.widgets.progress_panel import ProgressPanel
from gui.widgets.subtitle_editor import SubtitleEditor
from gui.widgets.output_panel import OutputPanel
from gui.widgets.cleanup_dialog import CleanupPanel
from gui.widgets.settings_panel import SettingsPanel

# ── Logging bridge: redirect Python logging to the GUI log panel ─────────────

class GUILogHandler(logging.Handler):
    def __init__(self, log_fn):
        super().__init__()
        self._log_fn = log_fn
        self.setFormatter(logging.Formatter("%(name)s — %(message)s"))

    def emit(self, record):
        msg = self.format(record)
        level_map = {
            logging.DEBUG: "DEFAULT",
            logging.INFO: "INFO",
            logging.WARNING: "WARNING",
            logging.ERROR: "ERROR",
            logging.CRITICAL: "ERROR",
        }
        self._log_fn(msg, level_map.get(record.levelno, "DEFAULT"))


# ── Pipeline step keys matching PIPELINE_STEPS order ────────────────────────

STEP_KEYS = [k for k, _ in PIPELINE_STEPS]

# Pause event: pipeline waits here during subtitle editing
_SUBTITLE_PAUSE = threading.Event()
_SUBTITLE_PAUSE.set()  # Initially not paused


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ReupTool  —  Video Re-dubbing Pipeline")
        self.geometry("1280x800")
        self.minsize(1000, 700)
        self.configure(bg=COLORS["bg_dark"])

        self._project_root = PROJECT_ROOT
        self._pipeline_thread: threading.Thread = None
        self._stop_event = threading.Event()
        self._event_queue: queue.Queue = queue.Queue()
        self._running = False
        self._last_video_path: Path = None
        self._last_srt_path: Path = None
        self._render_start: float = 0.0

        self._build_layout()
        self._setup_logging()
        self._poll_queue()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_layout(self):
        # Root: sidebar | main
        root_frame = tk.Frame(self, bg=COLORS["bg_dark"])
        root_frame.pack(fill="both", expand=True)

        self._sidebar = Sidebar(root_frame, self._navigate)
        self._sidebar.pack(side="left", fill="y")

        # Thin divider
        tk.Frame(root_frame, bg=COLORS["border"], width=1).pack(side="left", fill="y")

        # Right area: content | log
        right = tk.Frame(root_frame, bg=COLORS["bg_dark"])
        right.pack(side="left", fill="both", expand=True)

        # Content area (swappable panels)
        self._content_frame = tk.Frame(right, bg=COLORS["bg_dark"])
        self._content_frame.pack(fill="both", expand=True)

        # Log panel at bottom
        tk.Frame(right, bg=COLORS["border"], height=1).pack(fill="x")
        self._log_panel = LogPanel(right, height=180)
        self._log_panel.pack(fill="x", side="bottom")
        tk.Frame(right, bg=COLORS["border"], height=1).pack(fill="x", side="bottom")

        # Build all panels (hidden initially)
        self._panels: dict[str, tk.Frame] = {}

        self._source_panel = SourcePanel(self._content_frame, self._start_pipeline)
        self._panels["source"] = self._source_panel

        self._progress_panel = ProgressPanel(self._content_frame)
        self._panels["progress"] = self._progress_panel

        self._subtitle_editor = SubtitleEditor(
            self._content_frame, self._on_subtitle_continue, PROJECT_ROOT
        )
        self._panels["subtitle"] = self._subtitle_editor

        self._output_panel = OutputPanel(self._content_frame, PROJECT_ROOT)
        self._panels["output"] = self._output_panel

        self._cleanup_panel = CleanupPanel(self._content_frame, PROJECT_ROOT)
        self._panels["cleanup"] = self._cleanup_panel

        self._settings_panel = SettingsPanel(self._content_frame, PROJECT_ROOT)
        self._panels["settings"] = self._settings_panel

        # Show source panel first
        self._current_panel = "source"
        self._show_panel("source")
        self._sidebar.set_active("source")

        # Stop event from source panel
        self._source_panel.bind("<<StopPipeline>>", self._stop_pipeline)

    def _show_panel(self, key: str):
        for k, p in self._panels.items():
            p.pack_forget()
        if key in self._panels:
            self._panels[key].pack(fill="both", expand=True)
            self._current_panel = key

    def _navigate(self, key: str):
        self._show_panel(key)
        self._sidebar.set_active(key)

    # ── Logging bridge ───────────────────────────────────────────────────────

    def _setup_logging(self):
        handler = GUILogHandler(self._log_panel.log)
        handler.setLevel(logging.INFO)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

    # ── Queue polling (thread-safe GUI updates) ───────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg = self._event_queue.get_nowait()
                self._handle_event(msg)
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    def _handle_event(self, msg: dict):
        kind = msg.get("kind")

        if kind == "step_start":
            key = msg["key"]
            self._log_panel.log_step(msg["label"])
            self._sidebar.set_step_status(key, "running")
            self._progress_panel.set_step_status(key, "running", "Running…")

        elif kind == "step_done":
            key = msg["key"]
            self._sidebar.set_step_status(key, "done")
            self._progress_panel.set_step_status(key, "done", "Done ✓")

        elif kind == "step_fail":
            key = msg["key"]
            detail = msg.get("detail", "")
            self._sidebar.set_step_status(key, "error")
            self._progress_panel.set_step_status(key, "error", detail)
            self._log_panel.log(f"Step failed: {key} — {detail}", "ERROR")

        elif kind == "progress":
            step_idx = msg["step_idx"]
            sub_cur = msg["sub_cur"]
            sub_tot = msg["sub_tot"]
            detail = msg.get("detail", "")
            key = STEP_KEYS[step_idx] if step_idx < len(STEP_KEYS) else ""
            self._progress_panel.update_overall(step_idx, sub_cur, sub_tot, detail)
            if key:
                self._progress_panel.update_step_sub(key, sub_cur, sub_tot, detail)

        elif kind == "subtitle_pause":
            # Navigate to subtitle editor and pause pipeline
            self._log_panel.log("⏸  Pipeline paused for subtitle editing.", "SUCCESS")
            self._navigate("subtitle")
            self._sidebar.set_active("subtitle")
            video_path = msg.get("video_path")
            srt_path = msg.get("srt_path")
            if video_path:
                self._subtitle_editor.load_project(
                    Path(video_path) if video_path else None,
                    Path(srt_path) if srt_path else None
                )

        elif kind == "pipeline_done":
            output_path = msg.get("output_path")
            render_time = msg.get("render_time", 0)
            srt_path = msg.get("srt_path")
            self._running = False
            self._source_panel.set_done(True)
            if output_path:
                self._output_panel.set_complete(
                    Path(output_path), render_time,
                    Path(srt_path) if srt_path else None
                )
            self._cleanup_panel.refresh_sizes()
            self._navigate("output")
            self._log_panel.log("🎉 Pipeline complete!", "SUCCESS")

        elif kind == "pipeline_fail":
            reason = msg.get("reason", "Unknown error")
            self._running = False
            self._source_panel.set_done(False)
            self._output_panel.set_failed(reason)
            self._navigate("output")
            messagebox.showerror("Pipeline Failed", f"Pipeline failed:\n\n{reason}")

        elif kind == "log":
            self._log_panel.log(msg["text"], msg.get("level", "DEFAULT"))

    def _post(self, **kwargs):
        """Post event from any thread."""
        self._event_queue.put(kwargs)

    # ── Pipeline execution ───────────────────────────────────────────────────

    def _start_pipeline(self, url: str = None, filepath: str = None):
        if self._running:
            return

        self._stop_event.clear()
        _SUBTITLE_PAUSE.set()  # Make sure pause is cleared
        self._running = True
        self._source_panel.set_running(True)
        self._progress_panel.reset()
        self._sidebar.reset_steps()
        self._output_panel.reset()
        self._navigate("progress")
        self._log_panel.clear()
        self._log_panel.log("Pipeline starting…", "INFO")

        self._pipeline_thread = threading.Thread(
            target=self._run_pipeline,
            args=(url, filepath),
            daemon=True
        )
        self._pipeline_thread.start()

    def _stop_pipeline(self, event=None):
        if not self._running:
            return
        if messagebox.askyesno("Stop Pipeline", "Stop the running pipeline?"):
            self._stop_event.set()
            self._running = False
            self._source_panel.set_running(False)
            self._log_panel.log("Pipeline stopped by user.", "WARNING")

    def _run_pipeline(self, url: str, filepath: str):
        """Runs in a background thread."""
        try:
            from reup_tool.config import config
            import reup_tool.downloader as downloader
            import reup_tool.audio_converter as audio_converter
            import reup_tool.transcriber as transcriber
            import reup_tool.translator as translator
            import reup_tool.subtitle_formatter as subtitle_formatter
            import reup_tool.dubber as dubber
            import reup_tool.video_merger as video_merger

            single_file = Path(filepath) if filepath else None

            steps = [
                ("download",   "📥 Download",         lambda cb: downloader.process_all(url=url, progress_callback=cb) if url else downloader.process_all(url=None, progress_callback=cb)),
                ("convert",    "🔊 Extract Audio",    lambda cb: audio_converter.process_all(single_file=single_file, progress_callback=cb)),
                ("transcribe", "📝 Transcribe",       lambda cb: transcriber.process_all(single_file=single_file, progress_callback=cb)),
                ("translate",  "🌐 Translate",        lambda cb: translator.process_all(single_file=single_file, progress_callback=cb)),
                ("format",     "📄 Format Subtitle",  lambda cb: subtitle_formatter.process_all(single_file=single_file, progress_callback=cb)),
                ("dub",        "🎙️ Dub (TTS)",       lambda cb: dubber.process_all(single_file=single_file, progress_callback=cb)),
            ]

            self._render_start = time.time()

            for step_idx, (key, label, fn) in enumerate(steps):
                if self._stop_event.is_set():
                    self._post(kind="pipeline_fail", reason="Stopped by user")
                    return

                self._post(kind="step_start", key=key, label=label)

                def make_cb(s_idx=step_idx, s_key=key):
                    def cb(cur, tot, detail=""):
                        self._post(kind="progress", step_idx=s_idx,
                                   sub_cur=cur, sub_tot=max(tot, 1), detail=detail)
                    return cb

                try:
                    result = fn(make_cb())
                except Exception as exc:
                    self._post(kind="step_fail", key=key, detail=str(exc))
                    self._post(kind="pipeline_fail", reason=f"Exception in {label}: {exc}")
                    return

                if result is False:
                    self._post(kind="step_fail", key=key, detail="Returned False")
                    self._post(kind="pipeline_fail", reason=f"Step '{label}' failed. Check the log.")
                    return

                self._post(kind="step_done", key=key)

            # ── PAUSE for subtitle editing ───────────────────────────────────
            video_path = self._find_video(single_file, config)
            srt_path = self._find_srt(video_path, config)

            self._last_video_path = video_path
            self._last_srt_path = srt_path

            _SUBTITLE_PAUSE.clear()  # Block pipeline here

            self._post(
                kind="subtitle_pause",
                video_path=str(video_path) if video_path else None,
                srt_path=str(srt_path) if srt_path else None
            )

            # Wait for user to click "Continue"
            while not _SUBTITLE_PAUSE.wait(timeout=0.5):
                if self._stop_event.is_set():
                    self._post(kind="pipeline_fail", reason="Stopped by user")
                    return

            # ── Final render ─────────────────────────────────────────────────
            if self._stop_event.is_set():
                self._post(kind="pipeline_fail", reason="Stopped by user")
                return

            self._post(kind="step_start", key="merge", label="🎬 Render Video")
            merge_cb = lambda cur, tot, detail="": self._post(
                kind="progress", step_idx=6, sub_cur=cur, sub_tot=max(tot, 1), detail=detail
            )

            try:
                # Reload subtitle style into config before merging
                self._apply_subtitle_style(config)
                result = video_merger.process_all(single_file=single_file, progress_callback=merge_cb)
            except Exception as exc:
                self._post(kind="step_fail", key="merge", detail=str(exc))
                self._post(kind="pipeline_fail", reason=f"Merge error: {exc}")
                return

            if result is False:
                self._post(kind="step_fail", key="merge", detail="Merge returned False")
                self._post(kind="pipeline_fail", reason="Video merge failed. Check log.")
                return

            self._post(kind="step_done", key="merge")

            # Find output
            output_path = self._find_output(video_path, config)
            render_time = time.time() - self._render_start

            self._post(
                kind="pipeline_done",
                output_path=str(output_path) if output_path else None,
                render_time=render_time,
                srt_path=str(srt_path) if srt_path else None
            )

        except Exception as exc:
            self._post(kind="pipeline_fail", reason=f"Unexpected error: {exc}")

    def _apply_subtitle_style(self, config):
        """Load subtitle_style.json and apply ALL fields to config.video_merger.subtitle."""
        style_file = PROJECT_ROOT / "config" / "subtitle_style.json"
        if not style_file.exists():
            return
        try:
            import json

            def hex_to_ass(hex_color: str, alpha: int = 0) -> str:
                """Convert #RRGGBB → ASS &HAABBGGRR& (AA=0 = opaque)."""
                h = str(hex_color).lstrip("#")
                if len(h) == 6:
                    r, g, b = h[0:2], h[2:4], h[4:6]
                    return f"&H{alpha:02X}{b}{g}{r}&"
                return str(hex_color)   # already in ASS format — pass through

            data = json.loads(style_file.read_text(encoding="utf-8"))
            sub = config.video_merger.subtitle

            # ── Font ──────────────────────────────────────────────────────────
            if "font_name" in data:
                sub.font_name = str(data["font_name"])
            if "font_size" in data:
                sub.font_size = int(data["font_size"])

            # ── Text style ────────────────────────────────────────────────────
            if "bold" in data:
                sub.bold = -1 if data["bold"] else 0    # ASS: -1=bold, 0=normal
            if "italic" in data:
                sub.italic = -1 if data["italic"] else 0
            if "underline" in data:
                sub.underline = -1 if data["underline"] else 0

            # ── Colors (convert from #RRGGBB editor format → ASS &HAABBGGRR&) ─
            if "primary_color" in data:
                opacity = int(data.get("opacity", 255))
                alpha = max(0, 255 - opacity)           # ASS: 0=opaque, 255=transparent
                sub.primary_color = hex_to_ass(data["primary_color"], alpha)
            if "outline_color" in data:
                sub.outline_color = hex_to_ass(data["outline_color"])
            if "background_enable" in data:
                if data["background_enable"] and "background_color" in data:
                    bg_opacity = int(data.get("background_opacity", 128))
                    bg_alpha = max(0, 255 - bg_opacity)
                    sub.back_color = hex_to_ass(data["background_color"], bg_alpha)
                else:
                    sub.back_color = "&HFF000000&"      # fully transparent

            # ── Outline / shadow ──────────────────────────────────────────────
            if "outline_width" in data:
                sub.outline_width = int(data["outline_width"])
            if "border_style" in data:
                sub.border_style = int(data["border_style"])
            if "shadow_enable" in data:
                sub.shadow = 1 if data["shadow_enable"] else 0

            # ── Layout / alignment ────────────────────────────────────────────
            if "alignment" in data:
                # Editor stores "left"/"center"/"right" (horizontal only).
                # Map to ASS numpad alignment for the bottom row (most common).
                align_map = {"left": 1, "center": 2, "right": 3}
                val = data["alignment"]
                sub.alignment = align_map.get(str(val), 2) if isinstance(val, str) else int(val)
            if "margin_v" in data:
                sub.margin_v = int(data["margin_v"])
            if "margin_h" in data:
                sub.margin_l = int(data["margin_h"])
                sub.margin_r = int(data["margin_h"])

            # ── Position (percentage of frame) — KEY for correct render ───────
            if "pos_x_pct" in data:
                sub.pos_x_pct = float(data["pos_x_pct"])
            if "pos_y_pct" in data:
                sub.pos_y_pct = float(data["pos_y_pct"])

        except Exception:
            pass

    def _find_video(self, single_file, config) -> Path:
        if single_file and single_file.exists():
            return single_file
        videos = list(config.paths.video_dir.glob("*.mp4"))
        return videos[0] if videos else None

    def _find_srt(self, video_path, config) -> Path:
        if not video_path:
            return None
        stem = video_path.stem
        translated_dir = config.paths.translated_dir
        # Try <stem>_vi.srt
        candidates = [
            translated_dir / f"{stem}_vi.srt",
            translated_dir / f"{stem}.srt",
        ]
        for c in candidates:
            if c.exists():
                return c
        all_srt = list(translated_dir.glob("*.srt"))
        return all_srt[0] if all_srt else None

    def _find_output(self, video_path, config) -> Path:
        if not video_path:
            output_files = sorted(
                config.paths.output_dir.glob("*.mp4"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            return output_files[0] if output_files else None
        final = config.paths.output_dir / f"{video_path.stem}_final.mp4"
        if final.exists():
            return final
        output_files = sorted(
            config.paths.output_dir.glob("*.mp4"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        return output_files[0] if output_files else None

    # ── Subtitle continue callback ────────────────────────────────────────────

    def _on_subtitle_continue(self):
        """Called when user clicks 'Continue' in subtitle editor."""
        _SUBTITLE_PAUSE.set()  # Unblock the pipeline thread
        self._log_panel.log("▶  Subtitle editing complete. Resuming pipeline…", "SUCCESS")
        self._navigate("progress")
        self._sidebar.set_active("progress")
