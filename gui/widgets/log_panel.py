"""
log_panel.py - Real-time log display widget with color-coded levels.
"""

import tkinter as tk
from tkinter import ttk
import queue
from gui.theme import COLORS, FONTS


class LogPanel(tk.Frame):
    """Scrollable log panel that receives messages via queue or direct call."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLORS["bg_panel"], **kwargs)
        self._build()

    def _build(self):
        header = tk.Frame(self, bg=COLORS["bg_panel"])
        header.pack(fill="x", padx=8, pady=(6, 0))

        tk.Label(
            header, text="📋  LOG  (realtime)",
            bg=COLORS["bg_panel"], fg=COLORS["text_secondary"],
            font=FONTS["body_sm"]
        ).pack(side="left")

        self._clear_btn = tk.Button(
            header, text="Clear", bg=COLORS["bg_input"],
            fg=COLORS["text_secondary"], relief="flat",
            font=FONTS["body_sm"], cursor="hand2",
            command=self.clear, bd=0, padx=6, pady=1
        )
        self._clear_btn.pack(side="right")

        # Text area
        text_frame = tk.Frame(self, bg=COLORS["border"])
        text_frame.pack(fill="both", expand=True, padx=8, pady=6)

        self._text = tk.Text(
            text_frame,
            bg=COLORS["bg_dark"], fg=COLORS["log_text"],
            font=FONTS["mono"], wrap="word",
            state="disabled", relief="flat",
            selectbackground=COLORS["accent_light"],
            bd=0, padx=6, pady=4,
            spacing1=1, spacing3=1
        )

        scrollbar = ttk.Scrollbar(text_frame, command=self._text.yview)
        self._text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self._text.pack(side="left", fill="both", expand=True)

        # Color tags
        self._text.tag_configure("INFO",    foreground=COLORS["log_info"])
        self._text.tag_configure("WARNING", foreground=COLORS["log_warning"])
        self._text.tag_configure("ERROR",   foreground=COLORS["log_error"])
        self._text.tag_configure("SUCCESS", foreground=COLORS["log_success"])
        self._text.tag_configure("DEFAULT", foreground=COLORS["log_text"])
        self._text.tag_configure("TIME",    foreground=COLORS["text_muted"])
        self._text.tag_configure("STEP",    foreground=COLORS["accent"])

        self._max_lines = 2000

    def log(self, message: str, level: str = "DEFAULT"):
        """Thread-safe log append. Call from any thread."""
        self.after(0, self._append, message, level)

    def _append(self, message: str, level: str):
        """Must run on the main thread."""
        self._text.configure(state="normal")

        # Trim old lines
        line_count = int(self._text.index("end-1c").split(".")[0])
        if line_count > self._max_lines:
            self._text.delete("1.0", f"{line_count - self._max_lines}.0")

        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")

        self._text.insert("end", f"[{ts}] ", "TIME")
        level_tag = level if level in ("INFO", "WARNING", "ERROR", "SUCCESS") else "DEFAULT"
        self._text.insert("end", f"[{level}] " if level != "DEFAULT" else "", level_tag)
        self._text.insert("end", message + "\n", level_tag)

        self._text.see("end")
        self._text.configure(state="disabled")

    def log_step(self, step_name: str):
        self.after(0, self._append_step, step_name)

    def _append_step(self, step_name: str):
        self._text.configure(state="normal")
        self._text.insert("end", f"\n▶  {step_name}\n", "STEP")
        self._text.see("end")
        self._text.configure(state="disabled")

    def clear(self):
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
