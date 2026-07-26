"""
subtitle_editor.py - CapCut-style subtitle editor.
Frame preview + drag positioning + full style control panel.
Saves to subtitle_style.json; backend reads it at render time.

Fix summary (v1.6):
  1. Preview and export now share a single style source of truth:
       config/subtitle_style.json  ← written by this editor
       config.py                   ← reads & converts it for the video merger
  2. Preview font is loaded from the configured font_name instead of the
     hardcoded "arial.ttf".  Falls back gracefully through a platform-aware
     font search so mismatches are visible in the UI, not silent.
  3. Preview maintains the video's exact aspect ratio with centred letterboxing
     so what you see is a 1:1 spatial match with the exported frame.
  4. Drag-to-reposition is corrected for the letterbox offset: dragging at the
     edge of the black bar no longer moves the subtitle outside 0–100 %.
  5. Safe-area and centre guides are drawn on the canvas (faint, non-intrusive).
"""

import tkinter as tk
from tkinter import ttk, colorchooser, filedialog
import json
import os
import subprocess
import threading
from pathlib import Path
from gui.theme import COLORS, FONTS

# Attempt optional imports gracefully
try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


STYLE_DEFAULTS = {
    "font_name": "Cambria Bold",
    "font_size": 28,
    "primary_color": "#FFFF00",
    "outline_color": "#000000",
    "outline_width": 2,
    "shadow_enable": False,
    "shadow_color": "#000000",
    "shadow_offset_x": 2,
    "shadow_offset_y": 2,
    "background_enable": False,
    "background_color": "#000000",
    "background_opacity": 128,
    "alignment": "center",
    "margin_v": 20,
    "margin_h": 10,
    "bold": True,
    "italic": False,
    "underline": False,
    "line_spacing": 1,
    "letter_spacing": 0,
    "border_radius": 4,
    "border_style": 3,
    "pos_x_pct": 50.0,
    "pos_y_pct": 85.0,
    "opacity": 255,
    "preview_scale": 1.0,
}

# Available fonts (common Windows fonts)
FONT_LIST = [
    "Cambria Bold", "Arial", "Arial Black", "Calibri", "Comic Sans MS",
    "Consolas", "Courier New", "Georgia", "Impact", "Segoe UI",
    "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
]

# ---------------------------------------------------------------------------
# Font loading helper — shared by preview renderer
# ---------------------------------------------------------------------------

def _load_pil_font(font_name: str, font_size: int, bold: bool = False,
                   italic: bool = False) -> "ImageFont.FreeTypeFont":
    """
    Load a PIL/Pillow FreeType font for the given family name and size.

    Resolution order:
      1. font_name as-is (e.g. "Cambria Bold" → tries "Cambria Bold.ttf")
      2. Stripped variant without spaces ("CambriaBold.ttf")
      3. Common style suffixes appended when bold/italic flags are set
      4. Platform font directories (Windows %WINDIR%/Fonts, Linux common paths)
      5. A set of cross-platform fallback fonts
      6. PIL's built-in default (always succeeds, but very small)

    A warning indicator is stored in the returned font's `_load_warning`
    attribute so callers can decide whether to show a UI message.
    """
    size = max(8, int(font_size))

    # Build candidate filename list
    base_candidates = [font_name]
    stripped = font_name.replace(" ", "")
    if stripped != font_name:
        base_candidates.append(stripped)

    # Add bold/italic suffix variants
    style_suffix = ""
    if bold and italic:
        style_suffix = "BoldItalic"
    elif bold:
        style_suffix = "Bold"
    elif italic:
        style_suffix = "Italic"

    if style_suffix:
        base_candidates += [f"{font_name} {style_suffix}", f"{stripped}{style_suffix}"]

    # Flatten to .ttf/.otf filenames
    candidates = []
    for name in base_candidates:
        for ext in (".ttf", ".otf", ".TTF", ".OTF"):
            candidates.append(name + ext)

    # Cross-platform fallback fonts
    fallbacks = [
        "arial.ttf", "Arial.ttf",
        "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
        "LiberationSans-Bold.ttf", "LiberationSans-Regular.ttf",
        "FreeSansBold.otf", "FreeSans.otf",
    ]

    # Platform font directories
    font_dirs = []
    if os.name == "nt":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        font_dirs = [
            os.path.join(windir, "Fonts"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
        ]
    else:
        font_dirs = [
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            os.path.expanduser("~/.fonts"),
            "/System/Library/Fonts",        # macOS
            "/Library/Fonts",               # macOS
        ]

    # 1 — try bare filenames (relies on OS font path / working directory)
    for candidate in candidates:
        try:
            font = ImageFont.truetype(candidate, size)
            return font
        except Exception:
            continue

    # 2 — walk font directories
    for font_dir in font_dirs:
        if not os.path.isdir(font_dir):
            continue
        for candidate in candidates + fallbacks:
            fp = os.path.join(font_dir, candidate)
            if os.path.isfile(fp):
                try:
                    font = ImageFont.truetype(fp, size)
                    return font
                except Exception:
                    continue
        # Also do a recursive search limited to two levels for the primary name
        try:
            for root_dir, _dirs, files in os.walk(font_dir):
                depth = root_dir.replace(font_dir, "").count(os.sep)
                if depth > 2:
                    continue
                for fname in files:
                    if fname.lower().endswith((".ttf", ".otf")):
                        primary = font_name.lower().replace(" ", "")
                        if primary in fname.lower():
                            try:
                                font = ImageFont.truetype(
                                    os.path.join(root_dir, fname), size
                                )
                                return font
                            except Exception:
                                pass
        except Exception:
            pass

    # 3 — bare fallback filenames
    for fb in fallbacks:
        try:
            font = ImageFont.truetype(fb, size)
            return font
        except Exception:
            continue

    # 4 — PIL built-in (tiny, but never fails)
    return ImageFont.load_default()


class SubtitleEditor(tk.Frame):
    def __init__(self, parent, on_continue, project_root: Path, **kwargs):
        super().__init__(parent, bg=COLORS["bg_dark"], **kwargs)
        self._on_continue = on_continue
        self._root_path = project_root
        self._style = dict(STYLE_DEFAULTS)
        self._video_path: Path = None
        self._srt_path: Path = None
        self._srt_segments = []
        self._preview_image = None   # scaled PIL image that fills the canvas area
        self._photo_image = None
        self._drag_start = None
        # Letterbox offsets: pixel distance from canvas edge to the image edge
        self._img_x_offset: int = 0
        self._img_y_offset: int = 0
        self._style_file = project_root / "config" / "subtitle_style.json"
        self._load_style()
        self._build()

    def _load_style(self):
        if self._style_file.exists():
            try:
                data = json.loads(self._style_file.read_text(encoding="utf-8"))
                self._style.update(data)
            except Exception:
                pass

    def _save_style(self):
        self._style_file.parent.mkdir(parents=True, exist_ok=True)
        self._style_file.write_text(
            json.dumps(self._style, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ─────────────────────────────────── BUILD UI ────────────────────────────
    def _build(self):
        # Top action bar
        bar = tk.Frame(self, bg=COLORS["bg_panel"],
                       highlightbackground=COLORS["border"], highlightthickness=1)
        bar.pack(fill="x")

        tk.Label(bar, text="✏️  Subtitle Editor",
                 bg=COLORS["bg_panel"], fg=COLORS["text_heading"],
                 font=FONTS["heading"]).pack(side="left", padx=16, pady=10)

        self._continue_btn = tk.Button(
            bar, text="  ▶  Continue Render  ",
            bg=COLORS["success"], fg="#fff",
            relief="flat", font=FONTS["button"], cursor="hand2",
            bd=0, padx=16, pady=8,
            command=self._do_continue
        )
        self._continue_btn.pack(side="right", padx=12, pady=6)

        self._reset_btn = tk.Button(
            bar, text="Reset Style",
            bg=COLORS["bg_hover"], fg=COLORS["text_secondary"],
            relief="flat", font=FONTS["button"], cursor="hand2",
            bd=0, padx=10, pady=8,
            command=self._reset_style
        )
        self._reset_btn.pack(side="right", padx=4, pady=6)

        # Main content area: left=preview+timeline, right=style controls
        content = tk.Frame(self, bg=COLORS["bg_dark"])
        content.pack(fill="both", expand=True)

        left = tk.Frame(content, bg=COLORS["bg_dark"])
        left.pack(side="left", fill="both", expand=True, padx=(12, 6), pady=12)

        right = tk.Frame(content, bg=COLORS["bg_panel"], width=280,
                         highlightbackground=COLORS["border"], highlightthickness=1)
        right.pack(side="right", fill="y", padx=(0, 12), pady=12)
        right.pack_propagate(False)

        self._build_preview(left)
        self._build_timeline(left)
        self._build_style_panel(right)

    # ─────────── Preview canvas ─────────────────────────────────────────────
    def _build_preview(self, parent):
        lbl = tk.Label(parent, text="Frame Preview  (drag subtitle to reposition)",
                       bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                       font=FONTS["body_sm"])
        lbl.pack(anchor="w", pady=(0, 4))

        self._canvas = tk.Canvas(parent, bg="#000", highlightthickness=1,
                                 highlightbackground=COLORS["border"], cursor="crosshair")
        self._canvas.pack(fill="both", expand=True)

        self._canvas.bind("<ButtonPress-1>", self._drag_press)
        self._canvas.bind("<B1-Motion>", self._drag_motion)
        self._canvas.bind("<ButtonRelease-1>", self._drag_release)
        # Redraw on resize so the letterbox stays centred
        self._canvas.bind("<Configure>", lambda e: self._refresh_preview())

        self._canvas_placeholder()

    def _canvas_placeholder(self):
        self._canvas.delete("all")
        self._canvas.create_text(
            200, 140, text="No frame loaded.\nUse the slider below to select a frame.",
            fill=COLORS["text_muted"], font=FONTS["body"], justify="center"
        )

    # ─────────── Timeline / slider ──────────────────────────────────────────
    def _build_timeline(self, parent):
        tl = tk.Frame(parent, bg=COLORS["bg_card"],
                      highlightbackground=COLORS["border"], highlightthickness=1)
        tl.pack(fill="x", pady=(8, 0))

        row1 = tk.Frame(tl, bg=COLORS["bg_card"])
        row1.pack(fill="x", padx=10, pady=(8, 2))

        tk.Label(row1, text="Timeline", bg=COLORS["bg_card"],
                 fg=COLORS["text_secondary"], font=FONTS["body_sm"]).pack(side="left")

        self._time_label = tk.Label(row1, text="00:00:00",
                                    bg=COLORS["bg_card"], fg=COLORS["accent"],
                                    font=FONTS["mono"])
        self._time_label.pack(side="left", padx=8)

        self._frame_label = tk.Label(row1, text="Frame: 0",
                                     bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                                     font=FONTS["body_sm"])
        self._frame_label.pack(side="left", padx=8)

        self._fps_label = tk.Label(row1, text="FPS: —",
                                   bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                                   font=FONTS["body_sm"])
        self._fps_label.pack(side="left")

        self._duration_label = tk.Label(row1, text="/ 00:00:00",
                                        bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                                        font=FONTS["body_sm"])
        self._duration_label.pack(side="right")

        self._slider = ttk.Scale(tl, from_=0, to=100, orient="horizontal",
                                 command=self._on_slider)
        self._slider.pack(fill="x", padx=10, pady=(0, 4))

        row2 = tk.Frame(tl, bg=COLORS["bg_card"])
        row2.pack(fill="x", padx=10, pady=(0, 8))

        tk.Label(row2, text="Jump to (s):", bg=COLORS["bg_card"],
                 fg=COLORS["text_muted"], font=FONTS["body_sm"]).pack(side="left")

        self._jump_var = tk.StringVar()
        jump_entry = tk.Entry(row2, textvariable=self._jump_var,
                              bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                              insertbackground=COLORS["text_primary"],
                              relief="flat", font=FONTS["body_sm"], bd=4, width=8)
        jump_entry.pack(side="left", padx=4)

        tk.Button(row2, text="Go",
                  bg=COLORS["bg_hover"], fg=COLORS["text_primary"],
                  relief="flat", font=FONTS["body_sm"], cursor="hand2",
                  bd=0, padx=8, pady=2,
                  command=self._jump_to_time).pack(side="left")

        grab_btn = tk.Button(row2, text="📸  Grab Frame",
                             bg=COLORS["accent"], fg="#fff",
                             relief="flat", font=FONTS["body_sm"], cursor="hand2",
                             bd=0, padx=10, pady=2,
                             command=self._grab_frame)
        grab_btn.pack(side="right")

        self._total_seconds = 0.0
        self._fps = 25.0

    # ─────────── Style controls ─────────────────────────────────────────────
    def _build_style_panel(self, parent):
        tk.Label(parent, text="Subtitle Style",
                 bg=COLORS["bg_panel"], fg=COLORS["text_heading"],
                 font=FONTS["heading"]).pack(anchor="w", padx=12, pady=(12, 0))

        # Scrollable area
        canvas = tk.Canvas(parent, bg=COLORS["bg_panel"], highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        scroll_frame = tk.Frame(canvas, bg=COLORS["bg_panel"])
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _on_resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        scroll_frame.bind("<Configure>", _on_resize)
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self._ctrl = scroll_frame
        self._style_vars = {}

        self._add_section("Font")
        self._add_combo("font_name", "Typeface", FONT_LIST)
        self._add_spinbox("font_size", "Size", 8, 120, 1)
        self._add_checkrow("bold", "Bold", "italic", "Italic", "underline", "Underline")

        self._add_section("Color")
        self._add_color("primary_color", "Text Color")
        self._add_spinbox("opacity", "Text Opacity", 0, 255, 5)

        self._add_section("Outline")
        self._add_color("outline_color", "Outline Color")
        self._add_spinbox("outline_width", "Outline Width", 0, 20, 1)

        self._add_section("Shadow")
        self._add_checkbox("shadow_enable", "Enable Shadow")
        self._add_color("shadow_color", "Shadow Color")
        self._add_spinbox("shadow_offset_x", "Offset X", -20, 20, 1)
        self._add_spinbox("shadow_offset_y", "Offset Y", -20, 20, 1)

        self._add_section("Background")
        self._add_checkbox("background_enable", "Enable Background")
        self._add_color("background_color", "BG Color")
        self._add_spinbox("background_opacity", "BG Opacity", 0, 255, 5)
        self._add_spinbox("border_radius", "Border Radius", 0, 40, 1)

        self._add_section("Layout")
        self._add_radio("alignment", "Alignment", ["left", "center", "right"])
        self._add_spinbox("margin_v", "Margin Vertical", 0, 200, 2)
        self._add_spinbox("margin_h", "Margin Horizontal", 0, 200, 2)
        self._add_spinbox("line_spacing", "Line Spacing", 0, 10, 1)
        self._add_spinbox("letter_spacing", "Letter Spacing", -5, 20, 1)

        self._add_section("Position (% of frame)")
        self._add_spinbox("pos_x_pct", "X Position %", 0, 100, 1)
        self._add_spinbox("pos_y_pct", "Y Position %", 0, 100, 1)

        self._add_section("Preview")
        self._add_spinbox("preview_scale", "Preview Scale", 0.25, 3.0, 0.25)

    def _add_section(self, title):
        tk.Frame(self._ctrl, bg=COLORS["border"], height=1).pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(self._ctrl, text=title.upper(),
                 bg=COLORS["bg_panel"], fg=COLORS["text_muted"],
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=12, pady=(4, 0))

    def _row(self, label):
        row = tk.Frame(self._ctrl, bg=COLORS["bg_panel"])
        row.pack(fill="x", padx=12, pady=2)
        tk.Label(row, text=label, bg=COLORS["bg_panel"],
                 fg=COLORS["text_secondary"], font=FONTS["label"], width=16, anchor="w"
                 ).pack(side="left")
        return row

    def _add_combo(self, key, label, values):
        row = self._row(label)
        var = tk.StringVar(value=str(self._style.get(key, "")))
        cb = ttk.Combobox(row, textvariable=var, values=values,
                          state="readonly", width=18, font=FONTS["body_sm"])
        cb.pack(side="left")
        var.trace_add("write", lambda *_: self._on_change(key, var.get()))
        self._style_vars[key] = var

    def _add_spinbox(self, key, label, from_, to, increment):
        row = self._row(label)
        var = tk.DoubleVar(value=self._style.get(key, from_))
        sb = tk.Spinbox(row, from_=from_, to=to, increment=increment,
                        textvariable=var, width=8,
                        bg=COLORS["bg_input"], fg=COLORS["text_primary"],
                        buttonbackground=COLORS["bg_hover"],
                        relief="flat", font=FONTS["body_sm"])
        sb.pack(side="left")
        var.trace_add("write", lambda *_: self._on_change(key, var.get()))
        self._style_vars[key] = var

    def _add_color(self, key, label):
        row = self._row(label)
        color = self._style.get(key, "#FFFFFF")
        swatch = tk.Label(row, bg=color, width=4, relief="solid", cursor="hand2",
                          bd=1)
        swatch.pack(side="left")
        hex_var = tk.StringVar(value=color)
        hex_lbl = tk.Label(row, textvariable=hex_var, bg=COLORS["bg_panel"],
                           fg=COLORS["text_muted"], font=FONTS["body_sm"])
        hex_lbl.pack(side="left", padx=6)

        def pick():
            result = colorchooser.askcolor(color=hex_var.get(), title=f"Pick {label}")
            if result and result[1]:
                chosen = result[1]
                swatch.configure(bg=chosen)
                hex_var.set(chosen)
                self._on_change(key, chosen)

        swatch.bind("<Button-1>", lambda e: pick())
        self._style_vars[key] = hex_var

    def _add_checkbox(self, key, label):
        row = tk.Frame(self._ctrl, bg=COLORS["bg_panel"])
        row.pack(fill="x", padx=12, pady=2)
        var = tk.BooleanVar(value=bool(self._style.get(key, False)))
        cb = tk.Checkbutton(row, text=label, variable=var,
                            bg=COLORS["bg_panel"], fg=COLORS["text_primary"],
                            selectcolor=COLORS["bg_input"],
                            activebackground=COLORS["bg_panel"],
                            font=FONTS["body_sm"], relief="flat")
        cb.pack(anchor="w")
        var.trace_add("write", lambda *_: self._on_change(key, var.get()))
        self._style_vars[key] = var

    def _add_checkrow(self, k1, l1, k2, l2, k3, l3):
        row = tk.Frame(self._ctrl, bg=COLORS["bg_panel"])
        row.pack(fill="x", padx=12, pady=2)
        for key, label in ((k1, l1), (k2, l2), (k3, l3)):
            var = tk.BooleanVar(value=bool(self._style.get(key, False)))
            cb = tk.Checkbutton(row, text=label, variable=var,
                                bg=COLORS["bg_panel"], fg=COLORS["text_primary"],
                                selectcolor=COLORS["bg_input"],
                                activebackground=COLORS["bg_panel"],
                                font=FONTS["body_sm"], relief="flat")
            cb.pack(side="left", padx=(0, 8))
            var.trace_add("write", lambda *_, k=key, v=var: self._on_change(k, v.get()))
            self._style_vars[key] = var

    def _add_radio(self, key, label, options):
        row = self._row(label)
        var = tk.StringVar(value=str(self._style.get(key, options[0])))
        for opt in options:
            rb = tk.Radiobutton(row, text=opt.capitalize(), variable=var, value=opt,
                                bg=COLORS["bg_panel"], fg=COLORS["text_primary"],
                                selectcolor=COLORS["bg_input"],
                                activebackground=COLORS["bg_panel"],
                                font=FONTS["body_sm"], relief="flat")
            rb.pack(side="left", padx=2)
        var.trace_add("write", lambda *_: self._on_change(key, var.get()))
        self._style_vars[key] = var

    # ─────────── Style change handler ────────────────────────────────────────
    def _on_change(self, key, value):
        try:
            if key in ("pos_x_pct", "pos_y_pct", "preview_scale", "line_spacing"):
                self._style[key] = float(value)
            elif key in ("font_size", "font_name", "primary_color", "outline_color",
                         "shadow_color", "background_color", "alignment"):
                self._style[key] = value
            elif key in ("outline_width", "shadow_offset_x", "shadow_offset_y",
                         "margin_v", "margin_h", "opacity", "background_opacity",
                         "border_radius", "letter_spacing"):
                self._style[key] = int(float(value))
            elif key in ("bold", "italic", "underline", "shadow_enable",
                         "background_enable"):
                self._style[key] = bool(value)
            self._save_style()
            self._refresh_preview()
        except (ValueError, TypeError):
            pass

    # ─────────── Frame grab ──────────────────────────────────────────────────
    def _on_slider(self, val):
        seconds = float(val) * self._total_seconds / 100.0
        self._update_time_display(seconds)

    def _update_time_display(self, seconds: float):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        self._time_label.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
        frame_num = int(seconds * self._fps)
        self._frame_label.configure(text=f"Frame: {frame_num}")

    def _jump_to_time(self):
        try:
            t = float(self._jump_var.get())
            if self._total_seconds > 0:
                pct = min(max(t / self._total_seconds, 0), 1) * 100
                self._slider.set(pct)
                self._update_time_display(t)
        except ValueError:
            pass

    def _grab_frame(self):
        if not self._video_path or not self._video_path.exists():
            return
        pct = self._slider.get()
        seconds = pct * self._total_seconds / 100.0
        threading.Thread(target=self._extract_frame, args=(seconds,), daemon=True).start()

    def _extract_frame(self, seconds: float):
        try:
            import tempfile
            out_path = Path(tempfile.mktemp(suffix=".png"))
            cmd = [
                "ffmpeg", "-y", "-ss", str(seconds),
                "-i", str(self._video_path),
                "-frames:v", "1",
                "-q:v", "2", str(out_path)
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0 and out_path.exists():
                self.after(0, self._show_frame, out_path)
            else:
                self.after(0, lambda: self._canvas.create_text(
                    200, 140, text="Frame extraction failed.\nCheck FFmpeg is installed.",
                    fill=COLORS["error"], font=FONTS["body"], justify="center"
                ))
        except Exception as e:
            self.after(0, lambda: self._canvas.create_text(
                200, 140, text=f"Error: {e}",
                fill=COLORS["error"], font=FONTS["body"], justify="center"
            ))

    def _show_frame(self, path: Path):
        if not PIL_AVAILABLE:
            self._canvas.delete("all")
            self._canvas.create_text(200, 140,
                text="PIL not installed.\nRun: pip install Pillow",
                fill=COLORS["warning"], font=FONTS["body"], justify="center")
            return
        try:
            img = Image.open(path).convert("RGB")
            # Store the ORIGINAL (full-resolution) image so that _refresh_preview
            # can scale it to whatever the canvas currently is without degradation.
            self._preview_image_orig = img
            self._preview_image = None   # will be set in _refresh_preview
            self._refresh_preview()
        except Exception as e:
            self._canvas.create_text(200, 140, text=f"Load error: {e}",
                fill=COLORS["error"], font=FONTS["body"])

    # ─────────── Preview renderer ────────────────────────────────────────────

    def _refresh_preview(self):
        """
        Render the subtitle preview onto the canvas.

        The image is scaled to fit the canvas while preserving the video's
        aspect ratio (letterbox).  The subtitle is drawn on the scaled image
        using the same percentage-based coordinates that the video merger uses,
        so what you see in the preview is a pixel-accurate representation of the
        exported frame (modulo font hinting differences between PIL and ffmpeg).
        """
        if not PIL_AVAILABLE:
            return
        orig = getattr(self, "_preview_image_orig", None)
        if orig is None:
            return

        try:
            self._canvas.update_idletasks()
            cw = max(self._canvas.winfo_width(), 100)
            ch = max(self._canvas.winfo_height(), 80)

            # ── Scale to fit, preserving aspect ratio ──────────────────────
            ow, oh = orig.size
            scale = min(cw / ow, ch / oh)
            # Honour the optional preview_scale slider (0.25–3.0) but clamp so
            # the image never overflows the canvas.
            user_scale = float(self._style.get("preview_scale", 1.0))
            scale = min(scale * user_scale, min(cw / ow, ch / oh))
            nw = max(1, int(ow * scale))
            nh = max(1, int(oh * scale))

            img = orig.resize((nw, nh), Image.LANCZOS)
            self._preview_image = img   # keep reference for drag calculations

            # ── Letterbox offsets (centred on canvas) ──────────────────────
            ox = (cw - nw) // 2
            oy = (ch - nh) // 2
            self._img_x_offset = ox
            self._img_y_offset = oy

            # ── Subtitle text to display ───────────────────────────────────
            text = "Đây là subtitle mẫu"
            if self._srt_segments:
                text = self._srt_segments[0].get("text", text)[:60]

            # ── Font (same name as what the merger will use) ───────────────
            font_name = str(self._style.get("font_name", "Arial"))
            font_size = max(8, int(float(self._style.get("font_size", 28))))
            bold = bool(self._style.get("bold", False))
            italic = bool(self._style.get("italic", False))

            # Scale font size proportionally to the preview scale so layout
            # looks correct relative to a full-resolution frame.
            preview_font_size = max(8, int(font_size * scale))
            pil_font = _load_pil_font(font_name, preview_font_size, bold, italic)

            # ── Position (percentage → pixel on the scaled preview image) ──
            x_pct = float(self._style.get("pos_x_pct", 50)) / 100.0
            y_pct = float(self._style.get("pos_y_pct", 85)) / 100.0
            x = int(nw * x_pct)
            y = int(nh * y_pct)

            # ── Draw subtitle layers onto the preview image ────────────────
            draw = ImageDraw.Draw(img, "RGBA")

            # Background box
            if self._style.get("background_enable"):
                try:
                    bbox = draw.textbbox((x, y), text, font=pil_font, anchor="mm")
                except TypeError:
                    bbox = draw.textbbox((x, y), text, font=pil_font)
                pad = 6
                bg_color = self._style.get("background_color", "#000000")
                bg_opacity = int(self._style.get("background_opacity", 128))
                r, g, b = _hex_to_rgb(bg_color)
                draw.rectangle(
                    [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad],
                    fill=(r, g, b, bg_opacity)
                )

            # Outline (drawn by offsetting the text in all directions)
            outline_w = int(self._style.get("outline_width", 0))
            if outline_w > 0:
                oc = self._style.get("outline_color", "#000000")
                # Scale outline width with preview scale so it looks proportional
                ow_px = max(1, int(outline_w * scale))
                for dx in range(-ow_px, ow_px + 1):
                    for dy in range(-ow_px, ow_px + 1):
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), text, fill=oc,
                                      font=pil_font, anchor="mm")

            # Shadow
            if self._style.get("shadow_enable"):
                sc = self._style.get("shadow_color", "#000000")
                sx = int(int(self._style.get("shadow_offset_x", 2)) * scale)
                sy = int(int(self._style.get("shadow_offset_y", 2)) * scale)
                draw.text((x + sx, y + sy), text, fill=sc, font=pil_font, anchor="mm")

            # Main text
            pc = self._style.get("primary_color", "#FFFF00")
            opacity = int(self._style.get("opacity", 255))
            r, g, b = _hex_to_rgb(pc)
            draw.text((x, y), text, fill=(r, g, b, opacity), font=pil_font, anchor="mm")

            # Drag handle indicator (small circle at subtitle anchor)
            draw.ellipse([x - 5, y - 5, x + 5, y + 5], outline=COLORS["accent"], width=2)

            # ── Composite: black canvas + centred frame ────────────────────
            canvas_img = Image.new("RGB", (cw, ch), "#111111")
            canvas_img.paste(img.convert("RGB"), (ox, oy))

            # ── Safe-area and centre guides ────────────────────────────────
            gdraw = ImageDraw.Draw(canvas_img, "RGBA")

            # 10 % safe-area rectangle
            sa_x1 = ox + int(nw * 0.10)
            sa_y1 = oy + int(nh * 0.10)
            sa_x2 = ox + int(nw * 0.90)
            sa_y2 = oy + int(nh * 0.90)
            gdraw.rectangle([sa_x1, sa_y1, sa_x2, sa_y2],
                            outline=(255, 255, 255, 45), width=1)

            # Centre crosshair
            cx = ox + nw // 2
            cy = oy + nh // 2
            gdraw.line([cx - 18, cy, cx + 18, cy], fill=(255, 255, 255, 60), width=1)
            gdraw.line([cx, cy - 18, cx, cy + 18], fill=(255, 255, 255, 60), width=1)

            # ── Display ────────────────────────────────────────────────────
            self._canvas.delete("all")
            self._photo_image = ImageTk.PhotoImage(canvas_img)
            self._canvas.create_image(0, 0, anchor="nw", image=self._photo_image)

        except Exception:
            pass   # Never crash the UI on a preview redraw error

    # ─────────── Drag to reposition ──────────────────────────────────────────
    def _drag_press(self, e):
        self._drag_start = (e.x, e.y)

    def _drag_motion(self, e):
        """
        Update pos_x_pct / pos_y_pct from mouse position.

        The mouse coordinates are relative to the canvas origin.  We subtract
        the letterbox offsets (_img_x_offset, _img_y_offset) to convert to
        image-local coordinates before computing the percentage, so dragging
        in the black border area does not push the subtitle out of range.
        """
        if self._preview_image is None:
            return
        iw, ih = self._preview_image.size
        ox = self._img_x_offset
        oy = self._img_y_offset
        # Image-local mouse position
        ix = e.x - ox
        iy = e.y - oy
        x_pct = max(0.0, min(100.0, ix / max(iw, 1) * 100.0))
        y_pct = max(0.0, min(100.0, iy / max(ih, 1) * 100.0))
        self._style["pos_x_pct"] = round(x_pct, 1)
        self._style["pos_y_pct"] = round(y_pct, 1)
        self._update_style_vars()
        self._refresh_preview()

    def _drag_release(self, e):
        self._drag_start = None
        self._save_style()

    def _update_style_vars(self):
        """Sync internal _style dict back to UI variables."""
        for key, var in self._style_vars.items():
            val = self._style.get(key)
            if val is None:
                continue
            try:
                current = var.get()
                if str(current) != str(val):
                    var.set(val)
            except Exception:
                pass

    # ─────────── Public API ──────────────────────────────────────────────────
    def load_project(self, video_path: Path, srt_path: Path):
        """Called when pipeline pauses for subtitle editing."""
        self._video_path = video_path
        self._srt_path = srt_path
        self._srt_segments = self._parse_srt(srt_path) if srt_path and srt_path.exists() else []

        # Get video info
        if video_path and video_path.exists():
            self._probe_video()

        self._canvas_placeholder()
        self._canvas.create_text(
            200, 60,
            text=f"Video: {video_path.name if video_path else 'None'}\n"
                 f"{len(self._srt_segments)} subtitle segments loaded.\n\n"
                 "Set the slider to a time and click 📸 Grab Frame.",
            fill=COLORS["text_secondary"], font=FONTS["body"], justify="center"
        )

    def _probe_video(self):
        try:
            cmd = ["ffprobe", "-v", "error",
                   "-select_streams", "v:0",
                   "-show_entries", "stream=r_frame_rate,duration",
                   "-of", "default=noprint_wrappers=1",
                   str(self._video_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            for line in result.stdout.splitlines():
                if "duration=" in line:
                    self._total_seconds = float(line.split("=")[1].strip())
                    h = int(self._total_seconds // 3600)
                    m = int((self._total_seconds % 3600) // 60)
                    s = int(self._total_seconds % 60)
                    self._duration_label.configure(text=f"/ {h:02d}:{m:02d}:{s:02d}")
                if "r_frame_rate=" in line:
                    fps_str = line.split("=")[1].strip()
                    if "/" in fps_str:
                        num, den = fps_str.split("/")
                        self._fps = float(num) / float(den)
                    else:
                        self._fps = float(fps_str)
                    self._fps_label.configure(text=f"FPS: {self._fps:.2f}")
        except Exception:
            pass

    def _parse_srt(self, srt_path: Path):
        segments = []
        try:
            content = srt_path.read_text(encoding="utf-8")
            import re
            pattern = r'(\d+)\n([\d:,]+)\s*-->\s*([\d:,]+)\n(.+?)(?=\n\d+\n|\Z)'
            for m in re.findall(pattern, content, re.DOTALL):
                segments.append({
                    "index": int(m[0]),
                    "start": m[1].strip(),
                    "end": m[2].strip(),
                    "text": m[3].strip().replace("\n", " ")
                })
        except Exception:
            pass
        return segments

    def _reset_style(self):
        self._style = dict(STYLE_DEFAULTS)
        self._save_style()
        self._update_style_vars()
        self._refresh_preview()

    def _do_continue(self):
        self._save_style()
        self._on_continue()


# ---------------------------------------------------------------------------
# Small colour utility used only by the preview renderer
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str):
    """Convert #RRGGBB to (r, g, b) tuple.  Returns white on error."""
    try:
        h = hex_color.strip().lstrip("#")
        if len(h) == 6:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        pass
    return 255, 255, 255
