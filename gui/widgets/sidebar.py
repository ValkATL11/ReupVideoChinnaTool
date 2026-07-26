"""
sidebar.py - Navigation sidebar with pipeline step status indicators.
"""

import tkinter as tk
from gui.theme import COLORS, FONTS, PIPELINE_STEPS

NAV_ITEMS = [
    ("source",   "🎬  Video Source"),
    ("progress", "📊  Progress"),
    ("subtitle", "✏️  Subtitle Editor"),
    ("output",   "📁  Output"),
    ("cleanup",  "🗑️  Cleanup"),
    ("settings", "⚙️  Settings"),
]


class Sidebar(tk.Frame):
    def __init__(self, parent, on_navigate, **kwargs):
        super().__init__(parent, bg=COLORS["bg_sidebar"], width=200, **kwargs)
        self.pack_propagate(False)
        self._on_navigate = on_navigate
        self._active = "source"
        self._buttons = {}
        self._step_labels = {}
        self._build()

    def _build(self):
        # Title
        title_frame = tk.Frame(self, bg=COLORS["bg_sidebar"])
        title_frame.pack(fill="x", padx=14, pady=(20, 16))

        tk.Label(
            title_frame, text="⚡ ReupTool",
            bg=COLORS["bg_sidebar"], fg=COLORS["text_heading"],
            font=("Segoe UI", 14, "bold")
        ).pack(anchor="w")

        tk.Label(
            title_frame, text="v1.0  GUI Edition",
            bg=COLORS["bg_sidebar"], fg=COLORS["text_muted"],
            font=FONTS["body_sm"]
        ).pack(anchor="w")

        # Separator
        tk.Frame(self, bg=COLORS["border"], height=1).pack(fill="x", padx=10, pady=4)

        # Navigation
        tk.Label(
            self, text="NAVIGATION",
            bg=COLORS["bg_sidebar"], fg=COLORS["text_muted"],
            font=("Segoe UI", 7, "bold")
        ).pack(anchor="w", padx=16, pady=(8, 4))

        for key, label in NAV_ITEMS:
            self._make_nav_btn(key, label)

        # Separator
        tk.Frame(self, bg=COLORS["border"], height=1).pack(fill="x", padx=10, pady=8)

        # Pipeline steps
        tk.Label(
            self, text="PIPELINE",
            bg=COLORS["bg_sidebar"], fg=COLORS["text_muted"],
            font=("Segoe UI", 7, "bold")
        ).pack(anchor="w", padx=16, pady=(0, 4))

        for key, label in PIPELINE_STEPS:
            self._make_step_row(key, label)

    def _make_nav_btn(self, key, label):
        btn_frame = tk.Frame(self, bg=COLORS["bg_sidebar"], cursor="hand2")
        btn_frame.pack(fill="x", padx=6, pady=1)

        indicator = tk.Frame(btn_frame, bg=COLORS["bg_sidebar"], width=3)
        indicator.pack(side="left", fill="y", padx=(0, 0))

        btn = tk.Label(
            btn_frame, text=label,
            bg=COLORS["bg_sidebar"], fg=COLORS["text_secondary"],
            font=FONTS["body"], anchor="w",
            padx=12, pady=6
        )
        btn.pack(side="left", fill="x", expand=True)

        def enter(e, f=btn_frame, b=btn):
            if self._active != key:
                f.configure(bg=COLORS["bg_hover"])
                b.configure(bg=COLORS["bg_hover"])

        def leave(e, f=btn_frame, b=btn):
            if self._active != key:
                f.configure(bg=COLORS["bg_sidebar"])
                b.configure(bg=COLORS["bg_sidebar"])

        def click(e, k=key):
            self.set_active(k)
            self._on_navigate(k)

        for widget in (btn_frame, btn, indicator):
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)
            widget.bind("<Button-1>", click)

        self._buttons[key] = (btn_frame, btn, indicator)

    def _make_step_row(self, key, label):
        row = tk.Frame(self, bg=COLORS["bg_sidebar"])
        row.pack(fill="x", padx=16, pady=1)

        dot = tk.Label(row, text="○", bg=COLORS["bg_sidebar"],
                       fg=COLORS["text_muted"], font=("Segoe UI", 8), width=2)
        dot.pack(side="left")

        lbl = tk.Label(row, text=label,
                       bg=COLORS["bg_sidebar"], fg=COLORS["text_muted"],
                       font=FONTS["body_sm"], anchor="w")
        lbl.pack(side="left", fill="x", expand=True)

        self._step_labels[key] = (dot, lbl)

    def set_active(self, key: str):
        # Reset old
        if self._active in self._buttons:
            f, b, ind = self._buttons[self._active]
            f.configure(bg=COLORS["bg_sidebar"])
            b.configure(bg=COLORS["bg_sidebar"], fg=COLORS["text_secondary"])
            ind.configure(bg=COLORS["bg_sidebar"])

        self._active = key

        if key in self._buttons:
            f, b, ind = self._buttons[key]
            f.configure(bg=COLORS["sidebar_active"])
            b.configure(bg=COLORS["sidebar_active"], fg=COLORS["text_heading"])
            ind.configure(bg=COLORS["sidebar_indicator"])

    def set_step_status(self, key: str, status: str):
        """status: 'idle' | 'running' | 'done' | 'error'"""
        if key not in self._step_labels:
            return
        dot, lbl = self._step_labels[key]
        if status == "running":
            dot.configure(text="●", fg=COLORS["accent"])
            lbl.configure(fg=COLORS["text_primary"])
        elif status == "done":
            dot.configure(text="✓", fg=COLORS["success"])
            lbl.configure(fg=COLORS["success"])
        elif status == "error":
            dot.configure(text="✗", fg=COLORS["error"])
            lbl.configure(fg=COLORS["error"])
        else:
            dot.configure(text="○", fg=COLORS["text_muted"])
            lbl.configure(fg=COLORS["text_muted"])

    def reset_steps(self):
        for key in self._step_labels:
            self.set_step_status(key, "idle")
