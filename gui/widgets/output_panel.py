"""
output_panel.py - Output results display after pipeline completes.
"""

import tkinter as tk
import subprocess
import os
import platform
from pathlib import Path
from gui.theme import COLORS, FONTS


class OutputPanel(tk.Frame):
    def __init__(self, parent, project_root: Path, **kwargs):
        super().__init__(parent, bg=COLORS["bg_dark"], **kwargs)
        self._root = project_root
        self._output_path: Path = None
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", padx=24, pady=(24, 4))
        tk.Label(hdr, text="📁  Output",
                 bg=COLORS["bg_dark"], fg=COLORS["text_heading"],
                 font=FONTS["heading_lg"]).pack(anchor="w")
        tk.Label(hdr, text="Final rendered video and export options.",
                 bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                 font=FONTS["body"]).pack(anchor="w")

        # Result card
        card = tk.Frame(self, bg=COLORS["bg_card"],
                        highlightbackground=COLORS["border"], highlightthickness=1)
        card.pack(fill="x", padx=24, pady=12)

        self._status_icon = tk.Label(card, text="⏳",
                                     bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                                     font=("Segoe UI", 40))
        self._status_icon.pack(pady=(20, 4))

        self._status_label = tk.Label(card, text="Pipeline not started yet.",
                                      bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                                      font=FONTS["heading"])
        self._status_label.pack()

        tk.Frame(card, bg=COLORS["border"], height=1).pack(fill="x", padx=16, pady=12)

        # Info grid
        info_grid = tk.Frame(card, bg=COLORS["bg_card"])
        info_grid.pack(fill="x", padx=24, pady=(0, 8))
        info_grid.columnconfigure(1, weight=1)

        self._info_rows = {}
        fields = [
            ("path", "Output Path"),
            ("size", "File Size"),
            ("time", "Render Time"),
            ("srt",  "Subtitle File"),
        ]
        for i, (key, label) in enumerate(fields):
            tk.Label(info_grid, text=label + ":",
                     bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                     font=FONTS["body_sm"], anchor="w"
                     ).grid(row=i, column=0, sticky="w", pady=3)
            val_lbl = tk.Label(info_grid, text="—",
                               bg=COLORS["bg_card"], fg=COLORS["text_primary"],
                               font=FONTS["body"], anchor="w")
            val_lbl.grid(row=i, column=1, sticky="w", padx=12, pady=3)
            self._info_rows[key] = val_lbl

        tk.Frame(card, bg=COLORS["border"], height=1).pack(fill="x", padx=16, pady=8)

        # Action buttons
        btn_row = tk.Frame(card, bg=COLORS["bg_card"])
        btn_row.pack(fill="x", padx=16, pady=(0, 16))

        self._open_folder_btn = tk.Button(
            btn_row, text="📂  Open Folder",
            bg=COLORS["bg_hover"], fg=COLORS["text_primary"],
            relief="flat", font=FONTS["button"], cursor="hand2",
            bd=0, padx=14, pady=8, state="disabled",
            command=self._open_folder
        )
        self._open_folder_btn.pack(side="left", padx=(0, 8))

        self._play_btn = tk.Button(
            btn_row, text="▶  Play Video",
            bg=COLORS["accent"], fg="#fff",
            relief="flat", font=FONTS["button"], cursor="hand2",
            bd=0, padx=14, pady=8, state="disabled",
            command=self._play_video
        )
        self._play_btn.pack(side="left", padx=(0, 8))

        self._copy_btn = tk.Button(
            btn_row, text="📋  Copy Path",
            bg=COLORS["bg_hover"], fg=COLORS["text_primary"],
            relief="flat", font=FONTS["button"], cursor="hand2",
            bd=0, padx=14, pady=8, state="disabled",
            command=self._copy_path
        )
        self._copy_btn.pack(side="left")

        self._copy_confirm = tk.Label(btn_row, text="",
                                      bg=COLORS["bg_card"], fg=COLORS["success"],
                                      font=FONTS["body_sm"])
        self._copy_confirm.pack(side="left", padx=8)

        # Recent outputs list
        recent = tk.Frame(self, bg=COLORS["bg_dark"])
        recent.pack(fill="both", expand=True, padx=24, pady=(8, 16))

        tk.Label(recent, text="Recent Outputs",
                 bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                 font=FONTS["body"]).pack(anchor="w", pady=(0, 6))

        self._recent_frame = tk.Frame(recent, bg=COLORS["bg_dark"])
        self._recent_frame.pack(fill="both", expand=True)
        self._refresh_recent()

    # ── Public API ──────────────────────────────────────────────────────────

    def set_complete(self, output_path: Path, render_seconds: float, srt_path: Path = None):
        self._output_path = output_path
        self._status_icon.configure(text="🎉", fg=COLORS["success"])
        self._status_label.configure(text="Render Complete!", fg=COLORS["success"])

        if output_path and output_path.exists():
            size = output_path.stat().st_size / (1024 * 1024)
            self._info_rows["path"].configure(text=str(output_path))
            self._info_rows["size"].configure(text=f"{size:.1f} MB")
            self._info_rows["time"].configure(text=f"{render_seconds:.0f} s")
            if srt_path:
                self._info_rows["srt"].configure(text=str(srt_path))

            self._open_folder_btn.configure(state="normal")
            self._play_btn.configure(state="normal")
            self._copy_btn.configure(state="normal")

        self._refresh_recent()

    def set_failed(self, reason: str = ""):
        self._status_icon.configure(text="❌", fg=COLORS["error"])
        self._status_label.configure(text="Pipeline Failed", fg=COLORS["error"])
        for row in self._info_rows.values():
            row.configure(text=reason[:80] if reason else "—")

    def reset(self):
        self._output_path = None
        self._status_icon.configure(text="⏳", fg=COLORS["text_muted"])
        self._status_label.configure(text="Pipeline not started yet.", fg=COLORS["text_muted"])
        for row in self._info_rows.values():
            row.configure(text="—")
        for btn in (self._open_folder_btn, self._play_btn, self._copy_btn):
            btn.configure(state="disabled")

    # ── Actions ─────────────────────────────────────────────────────────────

    def _open_folder(self):
        folder = self._output_path.parent if self._output_path else (self._root / "assets" / "output")
        if platform.system() == "Windows":
            os.startfile(folder)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _play_video(self):
        if self._output_path and self._output_path.exists():
            if platform.system() == "Windows":
                os.startfile(self._output_path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(self._output_path)])
            else:
                subprocess.Popen(["xdg-open", str(self._output_path)])

    def _copy_path(self):
        if self._output_path:
            self.clipboard_clear()
            self.clipboard_append(str(self._output_path))
            self._copy_confirm.configure(text="Copied!")
            self.after(2000, lambda: self._copy_confirm.configure(text=""))

    def _refresh_recent(self):
        for w in self._recent_frame.winfo_children():
            w.destroy()

        output_dir = self._root / "assets" / "output"
        videos = []
        if output_dir.exists():
            videos = sorted(
                [f for f in output_dir.glob("*.mp4") if f.name != ".gitkeep"],
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )[:8]

        if not videos:
            tk.Label(self._recent_frame, text="No output files yet.",
                     bg=COLORS["bg_dark"], fg=COLORS["text_muted"],
                     font=FONTS["body_sm"]).pack(anchor="w")
            return

        for vf in videos:
            row = tk.Frame(self._recent_frame, bg=COLORS["bg_card"],
                           highlightbackground=COLORS["border"], highlightthickness=1)
            row.pack(fill="x", pady=2)

            tk.Label(row, text="🎬", bg=COLORS["bg_card"],
                     font=FONTS["body"]).pack(side="left", padx=8, pady=6)

            info = tk.Frame(row, bg=COLORS["bg_card"])
            info.pack(side="left", fill="x", expand=True)

            tk.Label(info, text=vf.name, bg=COLORS["bg_card"],
                     fg=COLORS["text_primary"], font=FONTS["body"],
                     anchor="w").pack(anchor="w")

            size = vf.stat().st_size / (1024 * 1024)
            tk.Label(info, text=f"{size:.1f} MB",
                     bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                     font=FONTS["body_sm"], anchor="w").pack(anchor="w")

            open_btn = tk.Button(
                row, text="Open",
                bg=COLORS["bg_hover"], fg=COLORS["text_primary"],
                relief="flat", font=FONTS["body_sm"], cursor="hand2",
                bd=0, padx=8, pady=4,
                command=lambda f=vf: self._open_file(f)
            )
            open_btn.pack(side="right", padx=8, pady=6)

    def _open_file(self, path: Path):
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass
