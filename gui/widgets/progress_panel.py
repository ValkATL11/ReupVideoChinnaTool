"""
progress_panel.py - Overall pipeline progress with per-step cards.
"""

import tkinter as tk
from tkinter import ttk
from gui.theme import COLORS, FONTS, PIPELINE_STEPS


class ProgressPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLORS["bg_dark"], **kwargs)
        self._step_cards = {}
        self._current_step = -1
        self._build()

    def _build(self):
        # ─── Overall bar ───
        top = tk.Frame(self, bg=COLORS["bg_panel"], bd=0)
        top.pack(fill="x", padx=16, pady=(16, 8))

        tk.Label(top, text="Overall Progress",
                 bg=COLORS["bg_panel"], fg=COLORS["text_secondary"],
                 font=FONTS["body"]).pack(anchor="w", padx=12, pady=(10, 2))

        bar_row = tk.Frame(top, bg=COLORS["bg_panel"])
        bar_row.pack(fill="x", padx=12, pady=(0, 4))

        self._bar_canvas = tk.Canvas(bar_row, height=8, bg=COLORS["progress_bg"],
                                     highlightthickness=0, bd=0)
        self._bar_canvas.pack(side="left", fill="x", expand=True)
        self._bar_fill = None

        self._pct_label = tk.Label(bar_row, text="0%",
                                   bg=COLORS["bg_panel"], fg=COLORS["accent"],
                                   font=FONTS["body_sm"], width=5)
        self._pct_label.pack(side="right")

        self._detail_label = tk.Label(top, text="Ready",
                                      bg=COLORS["bg_panel"], fg=COLORS["text_muted"],
                                      font=FONTS["body_sm"])
        self._detail_label.pack(anchor="w", padx=12, pady=(0, 10))

        # ─── Step cards ───
        cards_label = tk.Label(self, text="Pipeline Steps",
                               bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                               font=FONTS["body"])
        cards_label.pack(anchor="w", padx=16, pady=(8, 4))

        grid_frame = tk.Frame(self, bg=COLORS["bg_dark"])
        grid_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        grid_frame.columnconfigure((0, 1), weight=1)

        for i, (key, label) in enumerate(PIPELINE_STEPS):
            row, col = divmod(i, 2)
            card = self._make_card(grid_frame, i + 1, label)
            card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            grid_frame.rowconfigure(row, weight=1)
            self._step_cards[key] = card

    def _make_card(self, parent, step_num, label):
        frame = tk.Frame(parent, bg=COLORS["bg_card"], bd=0,
                         highlightbackground=COLORS["border"],
                         highlightthickness=1)

        # Step number badge
        badge = tk.Label(frame, text=f"  {step_num}  ",
                         bg=COLORS["bg_input"], fg=COLORS["text_muted"],
                         font=FONTS["body_sm"])
        badge.pack(anchor="w", padx=10, pady=(10, 2))

        # Label
        lbl = tk.Label(frame, text=label,
                       bg=COLORS["bg_card"], fg=COLORS["text_primary"],
                       font=FONTS["body"])
        lbl.pack(anchor="w", padx=10, pady=(2, 0))

        # Status
        status = tk.Label(frame, text="Waiting…",
                          bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                          font=FONTS["body_sm"])
        status.pack(anchor="w", padx=10, pady=(2, 0))

        # Sub-progress bar
        sub_canvas = tk.Canvas(frame, height=4, bg=COLORS["progress_bg"],
                               highlightthickness=0, bd=0)
        sub_canvas.pack(fill="x", padx=10, pady=(4, 10))

        frame._badge = badge
        frame._lbl = lbl
        frame._status = status
        frame._sub_canvas = sub_canvas
        frame._sub_fill = None
        return frame

    # ── Public API ──────────────────────────────────────────────

    def update_overall(self, step_idx: int, sub_current: int, sub_total: int, detail: str):
        """Called from pipeline thread (via after())."""
        self.after(0, self._do_overall, step_idx, sub_current, sub_total, detail)

    def _do_overall(self, step_idx, sub_current, sub_total, detail):
        total_steps = len(PIPELINE_STEPS)
        sub_frac = (sub_current / max(sub_total, 1))
        frac = min((step_idx + sub_frac) / total_steps, 1.0)
        pct = int(frac * 100)

        self._pct_label.configure(text=f"{pct}%")
        self._detail_label.configure(text=detail[:80])
        self._draw_bar(self._bar_canvas, self._bar_fill, frac,
                       COLORS["progress_fill"] if frac < 1 else COLORS["progress_done"])

    def set_step_status(self, key: str, status: str, detail: str = ""):
        self.after(0, self._do_step, key, status, detail)

    def _do_step(self, key, status, detail):
        if key not in self._step_cards:
            return
        card = self._step_cards[key]
        if status == "running":
            card.configure(highlightbackground=COLORS["accent"])
            card._badge.configure(bg=COLORS["accent_light"], fg=COLORS["text_white"])
            card._status.configure(text=detail or "Running…", fg=COLORS["accent"])
            self._draw_bar(card._sub_canvas, card._sub_fill, 0.1, COLORS["accent"])
        elif status == "done":
            card.configure(highlightbackground=COLORS["success"])
            card._badge.configure(bg="#1a3d27", fg=COLORS["success"])
            card._status.configure(text=detail or "Done ✓", fg=COLORS["success"])
            self._draw_bar(card._sub_canvas, card._sub_fill, 1.0, COLORS["success"])
        elif status == "error":
            card.configure(highlightbackground=COLORS["error"])
            card._badge.configure(bg="#3d1a1a", fg=COLORS["error"])
            card._status.configure(text=detail or "Error ✗", fg=COLORS["error"])
        else:
            card.configure(highlightbackground=COLORS["border"])
            card._badge.configure(bg=COLORS["bg_input"], fg=COLORS["text_muted"])
            card._status.configure(text="Waiting…", fg=COLORS["text_muted"])

    def update_step_sub(self, key: str, sub_current: int, sub_total: int, detail: str):
        self.after(0, self._do_sub, key, sub_current, sub_total, detail)

    def _do_sub(self, key, sub_current, sub_total, detail):
        if key not in self._step_cards:
            return
        card = self._step_cards[key]
        frac = sub_current / max(sub_total, 1)
        card._status.configure(text=detail[:50])
        self._draw_bar(card._sub_canvas, card._sub_fill, frac, COLORS["accent"])

    def _draw_bar(self, canvas, fill_ref, frac, color):
        canvas.update_idletasks()
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 2:
            return
        canvas.delete("fill")
        canvas.create_rectangle(0, 0, int(w * frac), h, fill=color, outline="", tags="fill")

    def reset(self):
        self.after(0, self._do_reset)

    def _do_reset(self):
        self._pct_label.configure(text="0%")
        self._detail_label.configure(text="Ready")
        self._draw_bar(self._bar_canvas, self._bar_fill, 0, COLORS["progress_fill"])
        for key in self._step_cards:
            self._do_step(key, "idle")
