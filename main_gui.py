"""
main_gui.py - Entry point for ReupTool Desktop GUI.

Usage:
    python main_gui.py
"""

import sys
import os
from pathlib import Path

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Check .env exists, create default if not
env_path = PROJECT_ROOT / ".env"
if not env_path.exists():
    env_path.write_text("GROQ_API_KEY=\nGEMINI_API_KEY=\n", encoding="utf-8")

# Patch config to not crash on missing GROQ_API_KEY at GUI startup
# The GUI will prompt user to fill in Settings if key is missing.
import importlib
import types

def _safe_config_import():
    """Import config but don't crash if API key missing — show error in GUI instead."""
    try:
        import reup_tool.config as cfg_module
        return True, None
    except EnvironmentError as e:
        return False, str(e)
    except FileNotFoundError as e:
        return False, str(e)

ok, err = _safe_config_import()
if not ok:
    # Still launch GUI; user will see the error in settings
    import tkinter as tk
    from tkinter import messagebox
    root_check = tk.Tk()
    root_check.withdraw()
    messagebox.showwarning(
        "Configuration Required",
        f"Configuration issue detected:\n\n{err}\n\n"
        "Please open Settings and fill in your API keys, then restart."
    )
    root_check.destroy()

# Launch main GUI
from gui.app import App


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
