"""
theme.py - Dark mode color palette and font definitions for ReupTool GUI.
"""

COLORS = {
    # Backgrounds
    "bg_dark": "#0d1117",
    "bg_panel": "#161b22",
    "bg_card": "#1c2128",
    "bg_input": "#21262d",
    "bg_hover": "#282e36",
    "bg_sidebar": "#010409",

    # Borders
    "border": "#30363d",
    "border_focus": "#388bfd",

    # Accent / brand
    "accent": "#1f6feb",
    "accent_hover": "#388bfd",
    "accent_light": "#0d419d",

    # Status colors
    "success": "#3fb950",
    "warning": "#d29922",
    "error": "#f85149",
    "info": "#58a6ff",

    # Text
    "text_primary": "#c9d1d9",
    "text_secondary": "#8b949e",
    "text_muted": "#484f58",
    "text_heading": "#e6edf3",
    "text_white": "#f0f6fc",

    # Progress bar
    "progress_bg": "#21262d",
    "progress_fill": "#1f6feb",
    "progress_done": "#3fb950",

    # Log colors
    "log_info": "#58a6ff",
    "log_warning": "#d29922",
    "log_error": "#f85149",
    "log_success": "#3fb950",
    "log_text": "#c9d1d9",

    # Sidebar
    "sidebar_active": "#1c2128",
    "sidebar_indicator": "#1f6feb",
}

FONTS = {
    "heading": ("Segoe UI", 13, "bold"),
    "heading_lg": ("Segoe UI", 16, "bold"),
    "body": ("Segoe UI", 10),
    "body_sm": ("Segoe UI", 9),
    "mono": ("Consolas", 9),
    "mono_sm": ("Consolas", 8),
    "label": ("Segoe UI", 9),
    "button": ("Segoe UI", 10, "bold"),
    "title": ("Segoe UI", 20, "bold"),
}

# Step labels shown in sidebar and progress
PIPELINE_STEPS = [
    ("download",  "📥 Download"),
    ("convert",   "🔊 Extract Audio"),
    ("transcribe","📝 Transcribe"),
    ("translate", "🌐 Translate"),
    ("format",    "📄 Format Subtitle"),
    ("dub",       "🎙️ Dub (TTS)"),
    ("merge",     "🎬 Render Video"),
]
