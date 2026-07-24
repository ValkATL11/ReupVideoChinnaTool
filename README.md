# ReupToolV1

**Pipeline tự động hóa quy trình reup video (Douyin/TikTok → Video thuyết minh tiếng Việt)**

Tải video → Tách audio → Nhận diện giọng nói (ASR) → Dịch phụ đề bằng AI → Lồng tiếng AI (TTS) → Ghép video hoàn chỉnh, tất cả chạy trong một lệnh duy nhất, có thanh tiến trình thời gian thực và log chi tiết theo từng bước.

---

## 📋 Mục lục

- [Tổng quan](#-tổng-quan)
- [Luồng xử lý (Pipeline)](#-luồng-xử-lý-pipeline)
- [Cấu trúc thư mục](#-cấu-trúc-thư-mục)
- [Yêu cầu hệ thống](#-yêu-cầu-hệ-thống)
- [Cài đặt](#-cài-đặt)
- [Cấu hình](#-cấu-hình)
- [Sử dụng](#-sử-dụng)
- [Log & Debug](#-log--debug)
- [Trạng thái phát triển](#-trạng-thái-phát-triển)
- [Lưu ý về bản quyền](#-lưu-ý-về-bản-quyền)

---

## 🎯 Tổng quan

ReupToolV1 là công cụ dòng lệnh (CLI) giúp tự động hóa toàn bộ quy trình biên tập video ngắn tiếng Trung (Douyin) thành video thuyết minh tiếng Việt, phục vụ việc tái sản xuất nội dung. Toàn bộ pipeline được điều phối bởi `main.py`, chạy tuần tự 7 module độc lập, mỗi module ghi log riêng và báo cáo tiến trình về một thanh progress bar chung trên terminal.

**Công nghệ chính sử dụng:**

| Hạng mục | Công nghệ |
|---|---|
| Tải video | Selenium + SnapWC (Douyin/TikTok downloader) |
| Xử lý audio/video | FFmpeg, pydub |
| Nhận diện giọng nói (ASR) | Groq API – `whisper-large-v3-turbo` |
| Dịch phụ đề | Google Gemini (`google-genai` / Selenium automation) |
| Lồng tiếng AI (TTS) | Microsoft Edge TTS (`edge-tts`) – giọng `vi-VN-NamMinhNeural`, `vi-VN-HoaiMyNeural` |
| Xử lý phụ đề | `pysrt` |

---

## 🔄 Luồng xử lý (Pipeline)

Mỗi lần chạy, tool thực hiện tuần tự 7 bước sau:

```
[1] Downloader           Tải video từ link Douyin/TikTok → assets/original_video/
[2] Audio Converter      Tách audio từ video               → assets/original_audio/
[3] Transcriber          Audio → phụ đề gốc (SRT, Groq Whisper) → assets/original_srt/
[4] Translator           Dịch SRT Trung → Việt (Gemini)     → assets/translated_srt/
[5] Subtitle Formatter   Chuẩn hóa SRT → văn bản đọc cho TTS → assets/subtitle_text/
[6] Dubber               Văn bản → giọng đọc AI (Edge TTS)   → assets/dubbing/
[7] Video Merger         Ghép audio lồng tiếng + phụ đề + video gốc → assets/output/
```

Nếu không truyền `--url` hoặc `--input`, chương trình sẽ hỏi trực tiếp link video ngay khi khởi động (có thể bỏ trống để dùng video đã có sẵn trong `assets/original_video/`).

---

## 📁 Cấu trúc thư mục

```
ReupToolV1/
├── main.py                      # Orchestrator chính, điều phối toàn bộ pipeline
├── requirements.txt              # Danh sách thư viện Python
├── .env.example                  # Mẫu khai báo API key
├── config/
│   └── settings.json             # Cấu hình chi tiết cho từng module
├── prompts/
│   └── translate_prompt.txt      # System prompt dịch phụ đề (tối ưu cho AI lồng tiếng)
├── scripts/
│   └── setup_env.py              # Script khởi tạo môi trường (.env + pip install)
├── src/
│   └── reup_tool/                # Package chứa logic xử lý từng bước pipeline
├── assets/
│   ├── original_video/           # Video gốc tải về
│   ├── original_audio/           # Audio tách từ video gốc
│   ├── original_srt/             # Phụ đề gốc (tiếng Trung)
│   ├── translated_srt/           # Phụ đề đã dịch (tiếng Việt)
│   ├── subtitle_text/            # Văn bản phụ đề dùng cho TTS
│   ├── dubbing/                  # File audio lồng tiếng AI
│   └── output/                   # Video thành phẩm cuối cùng
└── logs/
    ├── main.log                  # Log tổng quan toàn hệ thống
    └── modules/                  # Log chi tiết riêng từng module
```

---

## 💻 Yêu cầu hệ thống

- **Python** 3.9 trở lên
- **FFmpeg** đã cài đặt và có trong `PATH` (dùng để xử lý audio/video và burn phụ đề)
- **Google Chrome** (dùng cho Selenium – tải video và/hoặc dịch qua Gemini web)
- API key của **Groq** (dùng cho ASR) và **Google Gemini** (dùng cho dịch thuật)

---

## ⚙️ Cài đặt

1. Clone hoặc tải project về máy:

   ```bash
   git clone <repository-url>
   cd ReupToolV1
   ```

2. Chạy script thiết lập môi trường (tự tạo `.env` từ mẫu và cài thư viện):

   ```bash
   python scripts/setup_env.py
   ```

   Hoặc cài đặt thủ công:

   ```bash
   python -m venv venv
   venv\Scripts\activate        # Windows
   # source venv/bin/activate   # macOS/Linux

   pip install -r requirements.txt
   cp .env.example .env
   ```

3. Mở file `.env` và điền API key:

   ```env
   GROQ_API_KEY=your_groq_api_key
   GEMINI_API_KEY=your_gemini_api_key
   ```

---

## 🔧 Cấu hình

Toàn bộ tham số vận hành của pipeline được khai báo tập trung tại `config/settings.json`, bao gồm:

- **`downloader`** – chế độ headless, user-agent cho trình duyệt tự động hóa
- **`audio_converter`** – chất lượng audio đầu ra (VBR)
- **`transcriber`** – ngôn ngữ nhận diện, model Whisper sử dụng
- **`translator`** – engine dịch, prompt sử dụng (`prompts/translate_prompt.txt`)
- **`dubber`** – giọng đọc (nam/nữ), tốc độ đọc, định dạng audio TTS
- **`video_merger`** – cấu hình encode video/audio đầu ra (codec, bitrate, framerate) và style phụ đề burn-in (font, màu sắc, viền)

Prompt dịch tại `prompts/translate_prompt.txt` được thiết kế chuyên biệt để bản dịch **không bao giờ dài hơn thời lượng thoại gốc**, đảm bảo khớp thời gian khi đưa vào hệ thống lồng tiếng AI, đồng thời xử lý xưng hô, thành ngữ và tên riêng Hán Việt theo văn phong bản địa hóa chuyên nghiệp.

---

## 🚀 Sử dụng

**Chạy toàn bộ pipeline (sẽ hỏi link video nếu chưa có video sẵn):**

```bash
python main.py
```

**Tải và xử lý video từ một link cụ thể:**

```bash
python main.py --url "https://www.douyin.com/video/xxxxxxxx"
```

**Xử lý một video có sẵn trong `assets/original_video/`:**

```bash
python main.py --input "ten_video.mp4"
```

Video thành phẩm (đã lồng tiếng và gắn phụ đề) sẽ được lưu tại `assets/output/`.

---

## 🪵 Log & Debug

- `logs/main.log` – log tổng quan toàn bộ pipeline (thời gian bắt đầu/kết thúc từng bước, lỗi tổng quát)
- `logs/modules/<tên_module>.log` – log chi tiết nội bộ của từng bước xử lý, dùng để debug khi một bước cụ thể thất bại

Khi một bước trong pipeline lỗi, chương trình dừng ngay lập tức và in đường dẫn log tương ứng để kiểm tra.

---

## 🚧 Trạng thái phát triển

Project đang trong quá trình **tái cấu trúc (refactor)** từ tập hợp script rời rạc sang kiến trúc package chuẩn hóa tại `src/reup_tool/`. Tại thời điểm hiện tại:

- [x] `main.py` – orchestrator, quản lý pipeline, log và progress bar đã hoàn chỉnh
- [x] `config/settings.json`, `prompts/translate_prompt.txt`, `scripts/setup_env.py` – đã hoàn chỉnh
- [ ] `src/reup_tool/audio_converter.py` – đang khởi tạo, **chưa có logic xử lý**
- [ ] `src/reup_tool/config.py`, `downloader.py`, `transcriber.py`, `translator.py`, `subtitle_formatter.py`, `dubber.py`, `video_merger.py` – **chưa được tạo**, cần triển khai để pipeline chạy được end-to-end

Logic tương ứng hiện vẫn tồn tại ở các phiên bản script cũ (`downloader.py`, `audio_to_text.py`, `translate_AI.py`, `translate_google.py`, `translate_AI_Selenium.py`, `convert_srt_to_subtitle_text.py`, `dub.py`, `merge_simple.py`) trong lịch sử commit đầu tiên, và cần được chuyển hóa dần vào package `src/reup_tool/` theo đúng interface mà `main.py` đang gọi (`process_all(single_file, progress_callback)`).

---

## ⚠️ Lưu ý về bản quyền

Công cụ này thao tác trên nội dung video của bên thứ ba (Douyin/TikTok). Người dùng chịu trách nhiệm đảm bảo việc tải, dịch, lồng tiếng và tái phân phối nội dung tuân thủ điều khoản sử dụng của nền tảng gốc cũng như luật bản quyền hiện hành tại khu vực sử dụng.
