# ReupTool GUI v2.0 — Major Update

ReupTool is a **local Windows video re-dubbing pipeline** designed to automate the complete workflow from source video to finished dubbed video with subtitles, voiceover, and final render.

This **GUI v2.0 major update** delivers a cleaner workflow, a more professional subtitle editing experience, improved pipeline visibility, and a smoother end-to-end user experience compared to the original CLI-oriented version.

---

## What is ReupTool?

ReupTool processes a video through a full local pipeline:

1. Download or load a source video
2. Extract audio
3. Transcribe speech to text
4. Translate subtitles to Vietnamese
5. Format and refine subtitle output
6. Generate dubbed audio
7. Edit subtitles in a visual GUI
8. Render the final video

Everything runs locally on your Windows machine, with cloud APIs used only where necessary for speech recognition and translation.

---

## GUI v2.0 — Major Update

Version 2.0 represents a significant upgrade centered around the **Subtitle Editor** and a more polished desktop experience.

### Highlights
- Modern dark-mode desktop UI
- Step-by-step pipeline visualization
- Live logs for each processing stage
- Subtitle Editor with visual preview
- Drag-and-drop subtitle repositioning
- Style controls for font, size, color, outline, shadow, and background
- Pause-and-resume workflow before final render
- Output and cleanup panels for easier file management
- Clear separation between backend processing and GUI interaction

---

## Main Features

### Pipeline Automation
- Download source video
- Extract audio
- Transcribe speech to subtitle text
- Translate subtitles
- Format subtitle output
- Generate dubbed speech with TTS
- Render final merged video

### Subtitle Editor
- Visual frame preview
- Subtitle repositioning via dragging
- Style editing for subtitle appearance
- Live preview of subtitle changes
- Save edited subtitle style before final render

### Output Management
- View generated files
- Open output folder
- Clean temporary assets
- Keep only finished results if needed

### Logging & Progress
- Real-time logs
- Step-by-step pipeline status
- Clear error reporting for debugging
- Easy monitoring of long processing tasks

---

## Requirements

- **Windows 10 / 11**
- **Python 3.10+**
- **FFmpeg** installed and available in PATH
- **Google Chrome** installed
- Internet connection for API-based steps
- Valid API keys in `.env`

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file and add your keys:

```env
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Launch the GUI

```bash
python main_gui.py
```

### 4. CLI mode still available

```bash
python main.py
```

---

## Workflow

### GUI Flow
1. Open the app
2. Load or download a video
3. Run the pipeline
4. Pause at Subtitle Editor
5. Adjust subtitle style and position
6. Continue to render
7. Export final output video

### CLI Flow
- Same backend pipeline
- No visual editing step
- Faster for batch processing or testing

---

## Project Structure

```
reuptool/
├── main.py               # CLI entry point
├── main_gui.py           # GUI entry point
├── gui/
│   ├── app.py
│   ├── theme.py
│   └── widgets/
│       ├── sidebar.py
│       ├── progress_panel.py
│       ├── log_panel.py
│       ├── source_panel.py
│       ├── subtitle_editor.py
│       ├── cleanup_dialog.py
│       ├── output_panel.py
│       └── settings_panel.py
├── src/
│   └── reup_tool/
│       ├── downloader.py
│       ├── audio_converter.py
│       ├── transcriber.py
│       ├── translator.py
│       ├── subtitle_formatter.py
│       ├── dubber.py
│       ├── video_merger.py
│       ├── config.py
│       └── utils.py
├── config/
│   ├── settings.json
│   └── subtitle_style.json
├── assets/
│   ├── original_video/
│   ├── original_audio/
│   ├── original_srt/
│   ├── translated_srt/
│   ├── subtitle_text/
│   ├── dubbing/
│   └── output/
└── logs/
    └── modules/
```

---

## Asset Folders

| Folder | Purpose |
|--------|---------|
| `assets/original_video/` | Source video files |
| `assets/original_audio/` | Extracted audio |
| `assets/original_srt/` | Transcribed subtitle files |
| `assets/translated_srt/` | Translated subtitle files |
| `assets/subtitle_text/` | Subtitle text / working output |
| `assets/dubbing/` | Generated voice tracks |
| `assets/output/` | Final rendered videos |

---

## Subtitle Editor

The Subtitle Editor is the centerpiece of GUI v2.0, offering:

- Video frame preview
- Drag subtitle position visually
- Adjust font family and size
- Toggle bold / italic / underline
- Change text color
- Adjust outline color and width
- Enable shadow and configure shadow settings
- Edit background styling
- Continue directly to final render

**Important:** The style edited in the GUI is saved and then used by the final render step. This makes the editor a true part of the pipeline, not just a preview tool.

---

## API-Based Steps

ReupTool uses cloud services only where necessary:

- **Groq API** for speech-to-text transcription
- **Gemini API** for subtitle translation

All other steps are handled locally by the Python pipeline and system tools.

---

## Troubleshooting

### FFmpeg not found
Ensure FFmpeg is installed and added to PATH.

### Chrome / Selenium issues
Verify Google Chrome is installed and matches the required WebDriver setup.

### API errors
Check your `.env` file and confirm your API keys are valid.

### Subtitle style not applied correctly
Ensure you save changes in the Subtitle Editor before continuing the render step.

### Output video issues
Check:
- Subtitle style settings
- Output file paths
- Merged audio/subtitle assets
- Logs in `logs/modules/`

---

## Development Notes

- GUI and backend are separated cleanly
- CLI version remains available alongside GUI
- GUI is designed for future expansion
- Logs are modular for easier debugging
- Asset folders support pipeline caching and intermediate files

---

## ReupTool GUI v2.0 — Major Update

This release focuses on transforming the tool into a true desktop application rather than a simple script runner.

### Major Update Goals
- Better UI
- Better subtitle editing
- Better preview
- Better pipeline control
- Better output management
- Better overall user experience

---

## License

Add your preferred license here.

---

## Credits

Built for automated local video re-dubbing workflows with a GUI-first experience in version 2.0.
