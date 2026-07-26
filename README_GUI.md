# ReupTool GUI Edition

A Windows desktop application that wraps the ReupTool video re-dubbing pipeline in a modern dark-mode GUI.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure API keys
# Edit .env and fill in your keys:
GROQ_API_KEY=gsk_...         # Required — Groq Whisper transcription
GEMINI_API_KEY=AIza...       # Optional — faster translation (comma-separated for rotation)

# 3. Launch the GUI
python main_gui.py
```

## Requirements
- Python 3.10+
- FFmpeg installed and on PATH
- Chrome browser (for Selenium steps: download, audio conversion, Selenium translation)
- Windows 10/11 (tested)

## Architecture

```
GUI (Tkinter)
   ↓  calls on background thread
Backend Pipeline (unchanged from original)
   ↓
Output assets
```

### Pipeline steps
| # | Step | Module |
|---|------|--------|
| 1 | Download from Douyin/TikTok | downloader.py |
| 2 | Extract audio (MP3) | audio_converter.py |
| 3 | Speech-to-text (Groq Whisper) | transcriber.py |
| 4 | Translate to Vietnamese | translator.py |
| 5 | Format subtitle text | subtitle_formatter.py |
| 6 | Generate dubbed audio (Edge TTS) | dubber.py |
| ⏸ | **PAUSE** — Subtitle Editor | gui only |
| 7 | Render final video (FFmpeg) | video_merger.py |

### Subtitle Editor
After step 6, the pipeline pauses and opens the Subtitle Editor:
- Grab any frame from the video for live preview
- Drag the subtitle overlay to reposition
- Adjust font, size, color, outline, shadow, background, alignment, etc.
- Changes are saved to `config/subtitle_style.json`
- Backend reads this config when rendering the final video
- Click **Continue Render** to resume

### Directory structure
```
reuptool/
├── main_gui.py          ← Entry point (GUI)
├── main.py              ← Original CLI entry point (unchanged)
├── gui/
│   ├── app.py           ← Main window + pipeline orchestration
│   ├── theme.py         ← Colors, fonts
│   └── widgets/
│       ├── sidebar.py
│       ├── progress_panel.py
│       ├── log_panel.py
│       ├── source_panel.py
│       ├── subtitle_editor.py
│       ├── cleanup_dialog.py
│       ├── output_panel.py
│       └── settings_panel.py
├── src/reup_tool/       ← Backend (unchanged)
├── config/
│   ├── settings.json
│   └── subtitle_style.json  ← Written by GUI, read by backend
└── assets/              ← Input/output files
```
