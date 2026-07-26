"""
settings_panel.py - Settings panel for API keys and pipeline configuration.
"""

import tkinter as tk
from tkinter import ttk
import json
from pathlib import Path
from gui.theme import COLORS, FONTS


class SettingsPanel(tk.Frame):
    def __init__(self, parent, project_root: Path, **kwargs):
        super().__init__(parent, bg=COLORS["bg_dark"], **kwargs)
        self._root = project_root
        self._settings_path = project_root / "config" / "settings.json"
        self._env_path = project_root / ".env"
        self._settings = {}
        self._env_vars = {}
        self._vars = {}
        self._load()
        self._build()

    def _load(self):
        try:
            self._settings = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except Exception:
            self._settings = {}
        self._env_vars = {}
        try:
            for line in self._env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    self._env_vars[k.strip()] = v.strip()
        except Exception:
            pass

    def _save(self):
        # Save settings.json
        try:
            self._settings_path.write_text(
                json.dumps(self._settings, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass
        # Save .env
        lines = []
        for k, v in self._env_vars.items():
            lines.append(f"{k}={v}")
        try:
            self._env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass

    def _build(self):
        hdr = tk.Frame(self, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", padx=24, pady=(24, 4))
        tk.Label(hdr, text="⚙️  Settings",
                 bg=COLORS["bg_dark"], fg=COLORS["text_heading"],
                 font=FONTS["heading_lg"]).pack(anchor="w")
        tk.Label(hdr, text="Configure API keys, pipeline options, and output settings.",
                 bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                 font=FONTS["body"]).pack(anchor="w")

        # Scroll canvas
        outer = tk.Frame(self, bg=COLORS["bg_dark"])
        outer.pack(fill="both", expand=True, padx=24, pady=12)

        canvas = tk.Canvas(outer, bg=COLORS["bg_dark"], highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        frame = tk.Frame(canvas, bg=COLORS["bg_dark"])
        canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._ctrl = frame

        # ── API Keys ──
        self._section("API Keys (stored in .env)")
        self._env_field("GROQ_API_KEY", "Groq API Key", "Required for Whisper transcription", secret=True)
        self._env_field("GEMINI_API_KEY", "Gemini API Key", "Optional — faster translation via API (comma-separated for rotation)", secret=True)

        # ── Downloader ──
        self._section("Downloader")
        self._settings_bool("downloader.headless", "Run browser headless", True)

        # ── Audio Converter ──
        self._section("Audio Converter")
        self._settings_bool("audio_converter.headless", "Run browser headless", True)
        self._settings_int("audio_converter.vbr_quality", "VBR Quality (0-9)", 5, 0, 9)

        # ── Transcription ──
        self._section("Transcription (Groq Whisper)")
        self._settings_combo("transcriber.language", "Language",
                             ["auto", "zh", "en", "vi", "ja", "ko", "th"],
                             "auto")
        self._settings_combo("transcriber.model", "Model",
                             ["whisper-large-v3-turbo", "whisper-large-v3", "distil-whisper-large-v3-en"],
                             "whisper-large-v3-turbo")

        # ── Translator ──
        self._section("Translator")
        self._settings_combo("translator.engine", "Engine",
                             ["gemini_api", "gemini_selenium"],
                             "gemini_selenium")
        self._settings_bool("translator.headless", "Run browser headless", True)

        # ── Dubber ──
        self._section("Dubber (Edge TTS)")
        self._settings_combo("dubber.voice", "Voice Gender", ["female", "male"], "female")
        self._settings_str("dubber.voice_female", "Female Voice", "vi-VN-HoaiMyNeural")
        self._settings_str("dubber.voice_male", "Male Voice", "vi-VN-NamMinhNeural")
        self._settings_float("dubber.speed", "Speed", 1.3, 0.5, 3.0)

        # ── Video Merger ──
        self._section("Video Merger")
        self._settings_float("video_merger.original_volume", "Original Volume", 0.3, 0.0, 1.0)
        self._settings_float("video_merger.new_volume", "Dubbed Volume", 0.9, 0.0, 1.0)
        self._settings_combo("video_merger.video.codec", "Video Codec",
                             ["libx264", "libx265", "h264_nvenc"], "libx264")
        self._settings_combo("video_merger.video.preset", "Encoding Preset",
                             ["ultrafast", "superfast", "veryfast", "fast", "medium", "slow"],
                             "superfast")
        self._settings_str("video_merger.video.bitrate", "Video Bitrate", "4000k")
        self._settings_str("video_merger.audio.bitrate", "Audio Bitrate", "128k")

        # ── Save button ──
        btn_row = tk.Frame(frame, bg=COLORS["bg_dark"])
        btn_row.pack(fill="x", pady=(12, 20))

        tk.Button(btn_row, text="  💾  Save Settings  ",
                  bg=COLORS["accent"], fg="#fff",
                  relief="flat", font=FONTS["button"], cursor="hand2",
                  bd=0, padx=16, pady=10,
                  command=self._do_save).pack(side="left")

        self._save_label = tk.Label(btn_row, text="",
                                    bg=COLORS["bg_dark"], fg=COLORS["success"],
                                    font=FONTS["body_sm"])
        self._save_label.pack(side="left", padx=12)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _section(self, title):
        tk.Frame(self._ctrl, bg=COLORS["border"], height=1).pack(fill="x", pady=(10, 0))
        tk.Label(self._ctrl, text=title.upper(),
                 bg=COLORS["bg_dark"], fg=COLORS["text_muted"],
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", pady=(4, 0))

    def _row(self, label, hint=""):
        row = tk.Frame(self._ctrl, bg=COLORS["bg_dark"])
        row.pack(fill="x", pady=3)
        left = tk.Frame(row, bg=COLORS["bg_dark"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=label, bg=COLORS["bg_dark"],
                 fg=COLORS["text_primary"], font=FONTS["body"],
                 anchor="w").pack(anchor="w")
        if hint:
            tk.Label(left, text=hint, bg=COLORS["bg_dark"],
                     fg=COLORS["text_muted"], font=FONTS["body_sm"],
                     anchor="w").pack(anchor="w")
        return row

    def _env_field(self, key, label, hint="", secret=False):
        row = self._row(label, hint)
        var = tk.StringVar(value=self._env_vars.get(key, ""))
        entry = tk.Entry(row, textvariable=var,
                         bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                         insertbackground=COLORS["text_primary"],
                         relief="flat", font=FONTS["body_sm"], bd=6, width=36,
                         show="•" if secret else "")
        entry.pack(side="right")
        self._vars[("env", key)] = var

    def _settings_bool(self, path, label, default=True):
        row = self._row(label)
        val = self._get_setting(path, default)
        var = tk.BooleanVar(value=bool(val))
        tk.Checkbutton(row, variable=var,
                       bg=COLORS["bg_dark"], activebackground=COLORS["bg_dark"],
                       selectcolor=COLORS["bg_input"], relief="flat"
                       ).pack(side="right")
        self._vars[("settings", path)] = var

    def _settings_combo(self, path, label, options, default):
        row = self._row(label)
        val = self._get_setting(path, default)
        var = tk.StringVar(value=str(val))
        cb = ttk.Combobox(row, textvariable=var, values=options,
                          state="readonly", width=24, font=FONTS["body_sm"])
        cb.pack(side="right")
        self._vars[("settings", path)] = var

    def _settings_str(self, path, label, default):
        row = self._row(label)
        val = self._get_setting(path, default)
        var = tk.StringVar(value=str(val))
        tk.Entry(row, textvariable=var,
                 bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                 insertbackground=COLORS["text_primary"],
                 relief="flat", font=FONTS["body_sm"], bd=6, width=20
                 ).pack(side="right")
        self._vars[("settings", path)] = var

    def _settings_int(self, path, label, default, from_, to):
        row = self._row(label)
        val = self._get_setting(path, default)
        var = tk.IntVar(value=int(val))
        tk.Spinbox(row, from_=from_, to=to, textvariable=var, width=8,
                   bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                   buttonbackground=COLORS["bg_hover"],
                   relief="flat", font=FONTS["body_sm"]
                   ).pack(side="right")
        self._vars[("settings", path)] = var

    def _settings_float(self, path, label, default, from_, to):
        row = self._row(label)
        val = self._get_setting(path, default)
        var = tk.DoubleVar(value=float(val))
        tk.Spinbox(row, from_=from_, to=to, increment=0.05,
                   textvariable=var, width=8,
                   bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                   buttonbackground=COLORS["bg_hover"],
                   relief="flat", font=FONTS["body_sm"]
                   ).pack(side="right")
        self._vars[("settings", path)] = var

    def _get_setting(self, path, default):
        keys = path.split(".")
        obj = self._settings
        for k in keys:
            if isinstance(obj, dict) and k in obj:
                obj = obj[k]
            else:
                return default
        return obj

    def _set_setting(self, path, value):
        keys = path.split(".")
        obj = self._settings
        for k in keys[:-1]:
            if k not in obj or not isinstance(obj[k], dict):
                obj[k] = {}
            obj = obj[k]
        obj[keys[-1]] = value

    def _do_save(self):
        for (kind, key), var in self._vars.items():
            try:
                val = var.get()
                if kind == "env":
                    self._env_vars[key] = str(val)
                else:
                    self._set_setting(key, val)
            except Exception:
                pass
        self._save()
        self._save_label.configure(text="✓ Saved!")
        self.after(2500, lambda: self._save_label.configure(text=""))
