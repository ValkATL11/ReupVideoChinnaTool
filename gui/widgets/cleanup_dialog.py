"""
cleanup_dialog.py - Post-processing resource cleanup dialog.
"""

import tkinter as tk
import shutil
from pathlib import Path
from gui.theme import COLORS, FONTS


class CleanupPanel(tk.Frame):
    """Cleanup panel shown after pipeline finishes."""

    def __init__(self, parent, project_root: Path, **kwargs):
        super().__init__(parent, bg=COLORS["bg_dark"], **kwargs)
        self._root = project_root
        self._checks = {}
        self._build()

    def _build(self):
        # Title
        hdr = tk.Frame(self, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", padx=24, pady=(24, 4))
        tk.Label(hdr, text="🗑️  Resource Cleanup",
                 bg=COLORS["bg_dark"], fg=COLORS["text_heading"],
                 font=FONTS["heading_lg"]).pack(anchor="w")
        tk.Label(hdr, text="Free disk space by removing intermediate files.",
                 bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                 font=FONTS["body"]).pack(anchor="w")

        # Quick actions
        quick = tk.Frame(self, bg=COLORS["bg_card"],
                         highlightbackground=COLORS["border"], highlightthickness=1)
        quick.pack(fill="x", padx=24, pady=(12, 0))

        tk.Label(quick, text="Quick Actions",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=FONTS["body"]).pack(anchor="w", padx=14, pady=(10, 6))

        btn_row = tk.Frame(quick, bg=COLORS["bg_card"])
        btn_row.pack(fill="x", padx=14, pady=(0, 12))

        tk.Button(
            btn_row, text="① Delete Everything",
            bg="#3d1a1a", fg=COLORS["error"],
            relief="flat", font=FONTS["button"], cursor="hand2",
            bd=0, padx=14, pady=8,
            command=self._delete_all
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_row, text="② Keep Only Output Video",
            bg="#1a2d1a", fg=COLORS["success"],
            relief="flat", font=FONTS["button"], cursor="hand2",
            bd=0, padx=14, pady=8,
            command=self._keep_output_only
        ).pack(side="left", padx=(0, 8))

        # Custom / item checkboxes
        custom = tk.Frame(self, bg=COLORS["bg_card"],
                          highlightbackground=COLORS["border"], highlightthickness=1)
        custom.pack(fill="x", padx=24, pady=12)

        tk.Label(custom, text="③ Custom — Select items to delete:",
                 bg=COLORS["bg_card"], fg=COLORS["text_secondary"],
                 font=FONTS["body"]).pack(anchor="w", padx=14, pady=(10, 4))

        items = [
            ("video",      "Original Video",        "assets/original_video"),
            ("audio",      "Extracted Audio (MP3)", "assets/original_audio"),
            ("srt",        "Original SRT",          "assets/original_srt"),
            ("trans_srt",  "Translated SRT",        "assets/translated_srt"),
            ("sub_txt",    "Subtitle Text",         "assets/subtitle_text"),
            ("dubbing",    "Dubbed Audio",          "assets/dubbing"),
            ("logs",       "Log Files",             "logs"),
            ("output",     "Output Video",          "assets/output"),
        ]

        for key, label, rel_path in items:
            row = tk.Frame(custom, bg=COLORS["bg_card"])
            row.pack(fill="x", padx=14, pady=2)

            var = tk.BooleanVar(value=False)
            self._checks[key] = (var, rel_path)

            cb = tk.Checkbutton(
                row, text="", variable=var,
                bg=COLORS["bg_card"], activebackground=COLORS["bg_card"],
                selectcolor=COLORS["bg_input"], relief="flat"
            )
            cb.pack(side="left")

            tk.Label(row, text=label, bg=COLORS["bg_card"],
                     fg=COLORS["text_primary"], font=FONTS["body"],
                     width=22, anchor="w").pack(side="left")

            # Show path + size
            full_path = self._root / rel_path
            size_txt = self._dir_size(full_path)
            tk.Label(row, text=f"  {rel_path}  ·  {size_txt}",
                     bg=COLORS["bg_card"], fg=COLORS["text_muted"],
                     font=FONTS["body_sm"]).pack(side="left")

        # Execute button
        bottom = tk.Frame(custom, bg=COLORS["bg_card"])
        bottom.pack(fill="x", padx=14, pady=(8, 12))

        tk.Button(
            bottom, text="  Execute Selected Cleanup  ",
            bg=COLORS["error"], fg="#fff",
            relief="flat", font=FONTS["button"], cursor="hand2",
            bd=0, padx=16, pady=8,
            command=self._execute_custom
        ).pack(side="left")

        self._result_label = tk.Label(
            bottom, text="",
            bg=COLORS["bg_card"], fg=COLORS["text_muted"],
            font=FONTS["body_sm"]
        )
        self._result_label.pack(side="left", padx=12)

    # ─── Helpers ────────────────────────────────────────────────────────────

    def _dir_size(self, path: Path) -> str:
        try:
            total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            if total < 1024:
                return f"{total} B"
            elif total < 1024 ** 2:
                return f"{total/1024:.0f} KB"
            else:
                return f"{total/1024**2:.1f} MB"
        except Exception:
            return "—"

    def _delete_dir(self, rel_path: str):
        path = self._root / rel_path
        if path.exists():
            try:
                shutil.rmtree(path, ignore_errors=True)
                path.mkdir(parents=True, exist_ok=True)
                # Restore .gitkeep
                (path / ".gitkeep").touch()
            except Exception:
                pass

    def _delete_all(self):
        for key, (var, rel_path) in self._checks.items():
            self._delete_dir(rel_path)
        self._result_label.configure(text="✓ All resources deleted.", fg=COLORS["error"])

    def _keep_output_only(self):
        keep = {"output"}
        for key, (var, rel_path) in self._checks.items():
            if key not in keep:
                self._delete_dir(rel_path)
        self._result_label.configure(text="✓ Kept output video only.", fg=COLORS["success"])

    def _execute_custom(self):
        count = 0
        for key, (var, rel_path) in self._checks.items():
            if var.get():
                self._delete_dir(rel_path)
                count += 1
        if count:
            self._result_label.configure(text=f"✓ Deleted {count} item(s).", fg=COLORS["success"])
        else:
            self._result_label.configure(text="Nothing selected.", fg=COLORS["text_muted"])

    def refresh_sizes(self):
        """Rebuild to refresh sizes — call after pipeline finishes."""
        for widget in self.winfo_children():
            widget.destroy()
        self._checks = {}
        self._build()
