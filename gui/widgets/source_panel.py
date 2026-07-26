"""
source_panel.py - Video source selection: URL or local MP4 file.
"""

import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path
from gui.theme import COLORS, FONTS


class SourcePanel(tk.Frame):
    def __init__(self, parent, on_start, **kwargs):
        super().__init__(parent, bg=COLORS["bg_dark"], **kwargs)
        self._on_start = on_start
        self._mode = tk.StringVar(value="url")
        self._url_var = tk.StringVar()
        self._file_var = tk.StringVar()
        self._running = False
        self._build()

    def _build(self):
        # ── Title ──
        hdr = tk.Frame(self, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", padx=24, pady=(24, 4))
        tk.Label(hdr, text="Video Source", bg=COLORS["bg_dark"],
                 fg=COLORS["text_heading"], font=FONTS["heading_lg"]).pack(anchor="w")
        tk.Label(hdr, text="Choose a Douyin/TikTok URL or a local MP4 file to process.",
                 bg=COLORS["bg_dark"], fg=COLORS["text_secondary"], font=FONTS["body"]).pack(anchor="w")

        # ── Mode selector ──
        card = tk.Frame(self, bg=COLORS["bg_card"],
                        highlightbackground=COLORS["border"], highlightthickness=1)
        card.pack(fill="x", padx=24, pady=12)

        mode_row = tk.Frame(card, bg=COLORS["bg_card"])
        mode_row.pack(fill="x", padx=16, pady=(14, 8))

        tk.Label(mode_row, text="Input Mode",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["label"]
                 ).pack(anchor="w", pady=(0, 6))

        btn_row = tk.Frame(mode_row, bg=COLORS["bg_card"])
        btn_row.pack(anchor="w")

        self._url_rb = tk.Radiobutton(
            btn_row, text="  🔗  Douyin / TikTok URL", variable=self._mode,
            value="url", command=self._on_mode_change,
            bg=COLORS["bg_card"], fg=COLORS["text_primary"],
            selectcolor=COLORS["bg_input"], activebackground=COLORS["bg_card"],
            font=FONTS["body"], indicatoron=True, relief="flat"
        )
        self._url_rb.pack(side="left", padx=(0, 24))

        self._file_rb = tk.Radiobutton(
            btn_row, text="  📂  Local MP4 File", variable=self._mode,
            value="file", command=self._on_mode_change,
            bg=COLORS["bg_card"], fg=COLORS["text_primary"],
            selectcolor=COLORS["bg_input"], activebackground=COLORS["bg_card"],
            font=FONTS["body"], indicatoron=True, relief="flat"
        )
        self._file_rb.pack(side="left")

        tk.Frame(card, bg=COLORS["border"], height=1).pack(fill="x", padx=16, pady=4)

        # ── URL input ──
        self._url_frame = tk.Frame(card, bg=COLORS["bg_card"])
        self._url_frame.pack(fill="x", padx=16, pady=8)

        tk.Label(self._url_frame, text="Video URL",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["label"]
                 ).pack(anchor="w", pady=(0, 4))

        url_row = tk.Frame(self._url_frame, bg=COLORS["bg_input"],
                           highlightbackground=COLORS["border"], highlightthickness=1)
        url_row.pack(fill="x")

        self._url_entry = tk.Entry(
            url_row, textvariable=self._url_var,
            bg=COLORS["bg_input"], fg=COLORS["text_primary"],
            insertbackground=COLORS["text_primary"],
            relief="flat", font=FONTS["body"], bd=8
        )
        self._url_entry.pack(fill="x")
        self._url_entry.insert(0, "https://www.douyin.com/...")

        def _clear_placeholder(e):
            if self._url_entry.get() == "https://www.douyin.com/...":
                self._url_entry.delete(0, "end")

        def _restore_placeholder(e):
            if not self._url_entry.get().strip():
                self._url_entry.insert(0, "https://www.douyin.com/...")

        self._url_entry.bind("<FocusIn>", _clear_placeholder)
        self._url_entry.bind("<FocusOut>", _restore_placeholder)

        # ── File input ──
        self._file_frame = tk.Frame(card, bg=COLORS["bg_card"])
        # not packed initially

        tk.Label(self._file_frame, text="MP4 File",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["label"]
                 ).pack(anchor="w", pady=(0, 4))

        file_row = tk.Frame(self._file_frame, bg=COLORS["bg_card"])
        file_row.pack(fill="x")

        file_entry_frame = tk.Frame(file_row, bg=COLORS["bg_input"],
                                    highlightbackground=COLORS["border"], highlightthickness=1)
        file_entry_frame.pack(side="left", fill="x", expand=True)

        self._file_entry = tk.Entry(
            file_entry_frame, textvariable=self._file_var,
            bg=COLORS["bg_input"], fg=COLORS["text_primary"],
            insertbackground=COLORS["text_primary"],
            relief="flat", font=FONTS["body"], bd=8, state="readonly"
        )
        self._file_entry.pack(fill="x")

        self._browse_btn = tk.Button(
            file_row, text="  Browse…  ",
            bg=COLORS["bg_hover"], fg=COLORS["text_primary"],
            relief="flat", font=FONTS["body"], cursor="hand2",
            bd=0, padx=8, pady=4,
            command=self._browse
        )
        self._browse_btn.pack(side="right", padx=(8, 0))

        # File info label
        self._file_info = tk.Label(self._file_frame, text="",
                                   bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                                   font=FONTS["body_sm"])
        self._file_info.pack(anchor="w", pady=(4, 0))

        # ── Start button ──
        bottom = tk.Frame(card, bg=COLORS["bg_card"])
        bottom.pack(fill="x", padx=16, pady=(4, 16))

        self._start_btn = tk.Button(
            bottom, text="  ▶  Start Pipeline  ",
            bg=COLORS["accent"], fg=COLORS["text_white"],
            relief="flat", font=FONTS["button"], cursor="hand2",
            bd=0, padx=20, pady=10,
            command=self._start
        )
        self._start_btn.pack(side="left")

        self._stop_btn = tk.Button(
            bottom, text="  ■  Stop  ",
            bg=COLORS["bg_hover"], fg=COLORS["error"],
            relief="flat", font=FONTS["button"], cursor="hand2",
            bd=0, padx=12, pady=10,
            command=self._stop,
            state="disabled"
        )
        self._stop_btn.pack(side="left", padx=(8, 0))

        self._status_label = tk.Label(
            bottom, text="",
            bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
            font=FONTS["body_sm"]
        )
        self._status_label.pack(side="left", padx=16)

        # ── Tips ──
        tips = tk.Frame(self, bg=COLORS["bg_dark"])
        tips.pack(fill="x", padx=24, pady=(0, 16))

        tip_items = [
            "Pipeline will pause for subtitle editing before final render.",
            "Requires GROQ_API_KEY in .env for transcription.",
            "Optional GEMINI_API_KEY for faster translation via API.",
        ]
        for tip in tip_items:
            row = tk.Frame(tips, bg=COLORS["bg_dark"])
            row.pack(anchor="w", pady=1)
            tk.Label(row, text="•", bg=COLORS["bg_dark"], fg=COLORS["accent"],
                     font=FONTS["body"]).pack(side="left")
            tk.Label(row, text=f"  {tip}", bg=COLORS["bg_dark"],
                     fg=COLORS["text_muted"], font=FONTS["body_sm"]).pack(side="left")

    def _on_mode_change(self):
        mode = self._mode.get()
        if mode == "url":
            self._file_frame.pack_forget()
            self._url_frame.pack(fill="x", padx=16, pady=8)
        else:
            self._url_frame.pack_forget()
            self._file_frame.pack(fill="x", padx=16, pady=8)

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select MP4 File",
            filetypes=[("MP4 files", "*.mp4"), ("Video files", "*.mp4 *.mov *.avi"), ("All", "*.*")]
        )
        if path:
            self._file_var.set(path)
            size = Path(path).stat().st_size / (1024 * 1024)
            self._file_info.configure(text=f"{Path(path).name}  ·  {size:.1f} MB")

    def _start(self):
        if self._running:
            return

        mode = self._mode.get()
        if mode == "url":
            url = self._url_var.get().strip()
            if not url or url == "https://www.douyin.com/...":
                self._status_label.configure(text="⚠ Please enter a URL", fg=COLORS["warning"])
                return
            self._on_start(url=url, filepath=None)
        else:
            fp = self._file_var.get().strip()
            if not fp:
                self._status_label.configure(text="⚠ Please select a file", fg=COLORS["warning"])
                return
            self._on_start(url=None, filepath=fp)

    def _stop(self):
        # Signal is handled by app.py
        self.event_generate("<<StopPipeline>>")

    def set_running(self, running: bool):
        self._running = running
        if running:
            self._start_btn.configure(state="disabled", bg=COLORS["bg_hover"],
                                      fg=COLORS["text_muted"])
            self._stop_btn.configure(state="normal")
            self._status_label.configure(text="Pipeline running…", fg=COLORS["accent"])
        else:
            self._start_btn.configure(state="normal", bg=COLORS["accent"],
                                      fg=COLORS["text_white"])
            self._stop_btn.configure(state="disabled")
            self._status_label.configure(text="")

    def set_done(self, success: bool):
        self.set_running(False)
        if success:
            self._status_label.configure(text="✓ Pipeline complete!", fg=COLORS["success"])
        else:
            self._status_label.configure(text="✗ Pipeline failed. Check log.", fg=COLORS["error"])
