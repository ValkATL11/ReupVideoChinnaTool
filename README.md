<h1 align="center">
  <img src="https://img.shields.io/badge/ReupTool-V3-blueviolet?style=for-the-badge&logo=python" alt="ReupTool V3"/>
</h1>

<p align="center">
  <b>Automated Video Dubbing &amp; Processing Workstation</b><br/>
  Tải video · Trích âm · Transcribe (Whisper) · Dịch (Gemini AI) · TTS Lồng tiếng (Edge-TTS) · Tách vocal · Mix &amp; Render
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue?logo=python" />
  <img src="https://img.shields.io/badge/PySide6-GUI-green?logo=qt" />
  <img src="https://img.shields.io/badge/Groq-Whisper-orange" />
  <img src="https://img.shields.io/badge/Google-Gemini-red" />
  <img src="https://img.shields.io/badge/Edge--TTS-Microsoft-lightblue" />
  <img src="https://img.shields.io/badge/License-MIT-brightgreen" />
</p>

---

## 📖 Giới thiệu

**ReupTool V3** là một workstation tự động hóa toàn bộ quy trình **re-upload video với lồng tiếng tiếng Việt**, chạy trên desktop (Windows/Linux/macOS). Từ một URL video (Douyin, TikTok, v.v.) hoặc file local, công cụ thực hiện pipeline 9 bước:

> **Tải video → Trích audio → Phân đoạn → Transcribe → Dịch AI → Lồng tiếng TTS → Tách vocal → Mix âm thanh → Render video cuối**

Hỗ trợ cả giao diện đồ họa (**PySide6 GUI**) và chế độ tự động (**Headless CLI**), tích hợp bộ quản lý API key, Prompt Library với full CRUD, Simple Visual Editor để cấu hình subtitle/blur/logo trước khi render.

---

## ✨ Tính năng

| # | Tính năng | Chi tiết |
|---|-----------|----------|
| 🖥️ | **Desktop GUI (PySide6)** | 6 view: Dashboard, Projects, Pipeline, Visual Editor, Prompt Manager, Settings |
| ⚡ | **Headless CLI Mode** | Chạy pipeline tự động không cần GUI (`--cli --url`) |
| 📥 | **Video Downloader** | Hỗ trợ URL (Selenium headless) hoặc local file copy |
| 🎵 | **Audio Extraction** | FFmpeg — stereo/mono, normalize, 44.1kHz, 192kbps |
| ✂️ | **Audio Chunking** | Tự động phân đoạn theo kích thước file (≤19.5MB/chunk, silence-aware) |
| 🗣️ | **Transcription (STT)** | Groq API — Whisper Large v3 Turbo, auto-detect ngôn ngữ |
| 🌏 | **Translation AI** | Gemini API hoặc Selenium fallback; prompt-driven, SRT-format-preserving |
| 🔊 | **TTS Dubbing** | Microsoft Edge-TTS — vi-VN-HoaiMyNeural / vi-VN-NamMinhNeural, balanced/strict mode |
| 🎙️ | **Vocal Separation** | Tách vocal gốc khỏi nhạc nền (mode_1/mode_2, vocal_leak configurable) |
| 🎚️ | **Audio Mixing** | Mix TTS dub + nhạc nền (voice_volume, background_volume) |
| 🎬 | **Video Rendering** | FFmpeg — libx264/aac, CRF configurable, subtitle burn-in, blur mask, logo overlay |
| 📝 | **Prompt Library** | CRUD prompts dịch, built-in SRT v1 (Duration Cap + Filler-word rules), AI generator |
| 🔑 | **API Key Manager** | Pool Groq + Gemini, rotation, cooldown, health tracking, masked display |
| ⚙️ | **Config System** | JSON schema-versioned, dot-notation access, schema migration, `.env` support |
| 💾 | **Pipeline State** | JSON state machine, fingerprint caching, resume từ bước lỗi, retry, cancel |
| 🖼️ | **Visual Editor** | Cấu hình subtitle style, blur region, logo position trước khi render |

---

## 🗂️ Cấu trúc Project

```
ReupTool_V3_Release/
├── src/
│   ├── main.py                     # Entry point (GUI + CLI)
│   ├── __init__.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── core/
│   │   │   ├── config.py           # ConfigManager — JSON config, .env, dot-notation
│   │   │   ├── key_manager.py      # ApiKeyManager — Groq & Gemini pools, rotation
│   │   │   ├── pipeline.py         # PipelineEngine — 9-step orchestrator + state machine
│   │   │   ├── project.py          # Project / ProjectManager — ID system, path layout
│   │   │   └── prompt_engine.py    # PromptLibrary, PromptGenerator, CRUD
│   │   ├── editor/
│   │   │   ├── editor_config.py    # EditorConfig — subtitle/blur/logo settings
│   │   │   └── frame_extractor.py  # FFmpeg frame extraction for visual editor preview
│   │   ├── gui/
│   │   │   ├── main_window.py      # MainWindow (PySide6) — 6-view shell
│   │   │   ├── components/
│   │   │   │   ├── header.py
│   │   │   │   ├── sidebar.py
│   │   │   │   ├── editor_canvas.py
│   │   │   │   ├── prompt_card.py
│   │   │   │   ├── prompt_editor_dialog.py
│   │   │   │   ├── prompt_generator_dialog.py
│   │   │   │   ├── key_manager_dialog.py
│   │   │   │   └── log_viewer_dialog.py
│   │   │   ├── styles/
│   │   │   │   └── theme.py        # Dark theme stylesheet
│   │   │   ├── views/
│   │   │   │   ├── dashboard_view.py
│   │   │   │   ├── projects_view.py
│   │   │   │   ├── pipeline_view.py
│   │   │   │   ├── editor_view.py
│   │   │   │   ├── prompt_manager_view.py
│   │   │   │   └── settings_view.py
│   │   │   └── workers/
│   │   │       └── pipeline_worker.py  # QThread worker for async pipeline execution
│   │   └── services/               # Service wrappers (thin layer over modules/)
│   │       ├── downloader.py
│   │       ├── extractor.py
│   │       ├── chunker.py
│   │       ├── transcriber.py
│   │       ├── translator.py
│   │       ├── dubber.py
│   │       ├── separator.py
│   │       ├── mixer.py
│   │       └── renderer.py
│   ├── modules/                    # Core processing engines
│   │   ├── downloader.py           # Selenium-based video downloader
│   │   ├── audio_extractor.py      # FFmpeg audio extraction
│   │   ├── audio_chunker.py        # Silence-based audio splitter
│   │   ├── transcriber.py          # Groq Whisper STT
│   │   ├── translator.py           # Gemini API / Selenium translator
│   │   ├── dubber.py               # Edge-TTS dubbing engine
│   │   ├── vocal_separator.py      # Vocal separation (FFmpeg filters)
│   │   ├── mix_audio.py            # Audio mixer (pydub)
│   │   └── render.py               # Final video renderer (FFmpeg)
│   └── tests/                      # Unit & integration tests
│       ├── test_prompt_manager.py
│       ├── test_v3_core.py
│       └── test_v3_pipeline.py
├── config/
│   ├── config.json                 # ⚠️ Gitignored — tạo tự động khi chạy
│   └── prompts.json                # Prompt library (SRT translation prompts)
├── data/
│   └── projects/                   # ⚠️ Gitignored — dữ liệu runtime
├── tests/                          # Top-level test mirror
├── .env.example                    # Template biến môi trường
├── .gitignore
├── pyproject.toml
└── requirements.txt
```

> **Lưu ý:** `config/config.json` và toàn bộ `data/` bị gitignore (dữ liệu local + API keys).

---

## ⚙️ Yêu cầu môi trường

| Thành phần | Phiên bản tối thiểu |
|-----------|---------------------|
| Python | 3.9+ |
| FFmpeg | 4.x+ (phải có trong `PATH`) |
| Google Chrome | Phiên bản mới nhất (dùng cho Selenium downloader / Selenium translator) |
| ChromeDriver | Tự động qua `webdriver-manager` |

### API Keys cần thiết

| Service | Dùng cho | Lấy tại |
|---------|----------|---------|
| **Groq API Key** | Transcription (Whisper) | [console.groq.com](https://console.groq.com) |
| **Google Gemini API Key** | Translation AI | [aistudio.google.com](https://aistudio.google.com) |

> Translation có thể fallback sang **Selenium + Gemini Web** nếu không có Gemini API key (chậm hơn nhưng miễn phí).

---

## 🚀 Cài đặt

### 1. Clone & tạo môi trường ảo

```bash
git clone https://github.com/ValkATL11/ReupTool.git
cd ReupTool

python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 2. Cài dependencies

```bash
pip install -r requirements.txt
```

Hoặc cài qua `pyproject.toml` (bao gồm cả dev tools):

```bash
pip install -e ".[dev]"
```

### 3. Cài FFmpeg

- **Windows:** Tải tại [ffmpeg.org/download](https://ffmpeg.org/download.html), thêm thư mục `bin/` vào `PATH`
- **Linux:** `sudo apt install ffmpeg`
- **macOS:** `brew install ffmpeg`

Kiểm tra: `ffmpeg -version`

---

## 🔧 Cấu hình

### Bước 1 — Tạo file `.env`

```bash
cp .env.example .env
```

Chỉnh sửa `.env`:

```env
# Bắt buộc nếu dùng Groq Whisper
GROQ_API_KEY=gsk_XXXXXXXXXXXXXXXXXXXXXXXX

# Bắt buộc nếu dùng Gemini API translation
GEMINI_API_KEY=AIzaXXXXXXXXXXXXXXXXXXXXXXXX

# Optional: "api" hoặc "selenium" (mặc định: auto)
TRANSLATOR_ENGINE=api
```

> **Lưu ý bảo mật:** File `.env` bị gitignore và **không bao giờ** được commit lên Git.

### Bước 2 — Config ứng dụng

Khi chạy lần đầu, `config/config.json` được tạo tự động với giá trị mặc định. Bạn có thể chỉnh qua:
- **GUI → Settings** (khuyến nghị)
- Hoặc sửa trực tiếp `config/config.json`

### Bước 3 — Thêm API Keys qua GUI

Vào **Settings → API Key Manager** để thêm, xóa, bật/tắt các API key Groq và Gemini. Key được lưu trong `config.json` (gitignored).

---

## ▶️ Cách chạy

### GUI Desktop (mặc định)

```bash
cd src
python main.py
```

### Headless CLI — Tải URL và xử lý

```bash
cd src
python main.py --cli --url "https://www.douyin.com/video/XXXXXXXXXXXX"
```

### Headless CLI — Xử lý file local

```bash
cd src
python main.py --cli --input "D:/my_video.mp4"
```

### Headless CLI — Resume project đã có

```bash
cd src
python main.py --cli --project "PRJ-260730-0001"
```

### Debug verbose

```bash
cd src
python main.py --verbose
```

### Tùy chọn CLI đầy đủ

```
usage: main.py [-h] [--cli] [-p PROJECT] [-u URL] [-i INPUT] [-v]

Options:
  --cli           Chạy Headless CLI thay vì GUI
  -p, --project   Project ID (ví dụ: PRJ-260730-37TG)
  -u, --url       URL video cần tải & xử lý
  -i, --input     Đường dẫn file video local
  -v, --verbose   Bật debug logging
```

---

## 🔄 Pipeline / Workflow

Pipeline gồm **9 bước** chạy tuần tự, mỗi bước có state caching, retry và resume:

```
┌─────────────────────────────────────────────────────────┐
│                    REUPTOOL V3 PIPELINE                 │
├────┬──────────────────┬──────────────────────────────────┤
│ #  │ Step Key         │ Mô tả                            │
├────┼──────────────────┼──────────────────────────────────┤
│ 1  │ download         │ Tải video (URL/local)            │
│ 2  │ visual_editor    │ Simple Editor — cấu hình render  │
│ 3  │ audio_extraction │ Trích audio từ video (FFmpeg)    │
│ 4  │ audio_chunking   │ Phân đoạn audio theo size/silence│
│ 5  │ transcription    │ STT qua Groq Whisper → SRT       │
│ 6  │ translation      │ Dịch SRT → tiếng Việt (Gemini)  │
│ 7  │ dubbing          │ TTS lồng tiếng (Edge-TTS)        │
│ 8  │ vocal_separation │ Tách vocal gốc, giữ nhạc nền     │
│ 9  │ rendering        │ Mix audio + Render video cuối    │
└────┴──────────────────┴──────────────────────────────────┘
```

**Flow đặc biệt ở bước 2 (Simple Editor):**
Sau khi tải video, pipeline **dừng** và yêu cầu user mở Simple Editor để cấu hình subtitle style, blur region và logo. Sau khi nhấn "Save & Continue", pipeline tự động resume từ bước 3.

**Caching & Resume:**
- Mỗi bước lưu kết quả vào `state.json` trong thư mục project
- Nếu output đã có và fingerprint khớp → bước được **skip tự động**
- Translation cache bị invalidate nếu active prompt thay đổi
- Có thể force rerun từng bước qua GUI

---

## 📦 Dependencies

| Package | Phiên bản | Dùng cho |
|---------|-----------|---------|
| `PySide6` | ≥6.6.0 | Desktop GUI |
| `pydub` | ≥0.25.1 | Audio mixing |
| `ffmpeg-python` | ≥0.2.0 | FFmpeg Python bindings |
| `groq` | ≥0.4.0 | Groq Whisper API (STT) |
| `google-genai` | ≥0.1.0 | Google Gemini API (Translation) |
| `edge-tts` | ≥6.1.0 | Microsoft Edge TTS (Dubbing) |
| `selenium` | ≥4.15.0 | Video downloader & Selenium translator |
| `webdriver-manager` | ≥4.0.0 | ChromeDriver auto-management |
| `requests` | ≥2.31.0 | HTTP utilities |
| `numpy` | ≥1.24.0 | Audio signal processing |
| `scipy` | ≥1.11.0 | Audio filtering |
| `python-dotenv` | ≥1.0.0 | `.env` file loading |

**Dev dependencies:** `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `pre-commit`

---

## 🗃️ Project ID System

Mỗi project có ID dạng: `PRJ-YYMMDD-XXXX`

Ví dụ: `PRJ-260801-A3TK`

Mỗi project được tổ chức trong `data/projects/<PROJECT_ID>/` với:
- `state.json` — trạng thái pipeline
- `editor_config.json` — cấu hình Visual Editor

Dữ liệu xử lý (video, audio, SRT, ...) được lưu tại các thư mục dùng chung trong `data/`:

```
data/
├── projects/<PROJECT_ID>/      # State & editor config
├── original_videos/            # Video gốc tải về
├── original_audios/            # Audio gốc extracted
├── chunked_audio/              # Audio phân đoạn
├── transcriber_output/         # SRT transcribed
├── translated/                 # SRT đã dịch
├── dubbing/                    # TTS audio segments
├── separated_audios/           # Non-vocal tracks
├── mixed_audios/               # Mixed audio
└── output/                     # Video cuối <PROJECT_ID>_Final.mp4
```

---

## 🔐 Bảo mật

- **Không bao giờ** lưu API key vào `config.json` plain text khi commit
- API key được load từ `.env` (gitignored) hoặc biến môi trường
- Key được **mask** khi hiển thị trong log và UI (`gsk_****...****`)
- `config/config.json` bị gitignore (chứa key pool đã add qua GUI)
- Pool key hỗ trợ cooldown tự động khi gặp lỗi rate-limit

---

## 🧪 Tests

```bash
# Chạy toàn bộ test suite
pytest src/tests/ -v

# Chạy với coverage
pytest src/tests/ --cov=src --cov-report=html
```

Test files:
- `test_prompt_manager.py` — Unit tests cho PromptLibrary CRUD
- `test_v3_core.py` — Tests cho ConfigManager, ProjectManager
- `test_v3_pipeline.py` — Integration tests cho PipelineEngine

---

## 📝 Ghi chú sử dụng

1. **FFmpeg phải được cài và có trong `PATH`** trước khi chạy — đây là dependency bắt buộc cho hầu hết các bước xử lý.

2. **Bước Visual Editor (bước 2) là bắt buộc** trong pipeline GUI. Pipeline sẽ dừng tại đây và chờ user cấu hình trước khi tiếp tục. Trong CLI mode, bước này được skip tự động nếu `editor_config.json` đã tồn tại.

3. **Translation engine:**
   - `auto` (mặc định): dùng Gemini API nếu có key, fallback sang Selenium
   - `gemini_api`: bắt buộc Gemini API key
   - `selenium`: dùng Gemini Web qua Chrome (chậm, không cần API key)

4. **Edge-TTS cần kết nối Internet** để tổng hợp giọng nói.

5. **Prompt Library:** Prompt `builtin_srt_v1` là built-in, không thể sửa/xóa. Tạo prompt tùy chỉnh qua GUI → Prompt Manager hoặc dùng AI Generator. Thay đổi active prompt sẽ invalidate cache bước dịch.

6. **Caching:** Nếu muốn force rerun một bước, dùng chức năng "Rerun Step" trong Pipeline View của GUI.

---

## 📄 License

MIT License — xem file [LICENSE](LICENSE) để biết thêm chi tiết.

---

<p align="center">
  Made with ❤️ for the Vietnamese content creator community
</p>
