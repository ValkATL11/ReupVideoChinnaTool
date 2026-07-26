"""
scripts/setup_env.py - Script khởi tạo môi trường cho ReupVideoChinnaTool
"""

import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check_and_install_requirements():
    req_file = PROJECT_ROOT / "requirements.txt"
    if req_file.exists():
        print(f"📦 Đang cài đặt thư viện từ {req_file.name}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_file)])
            print("✅ Cài đặt pip requirements thành công!")
        except Exception as e:
            print(f"❌ Cài đặt thất bại: {e}")
    else:
        print("⚠️ Không tìm thấy requirements.txt")


def init_env_file():
    env_file = PROJECT_ROOT / ".env"
    env_example = PROJECT_ROOT / ".env.example"

    if not env_file.exists():
        if env_example.exists():
            env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
            print("📝 Đã khởi tạo file .env từ .env.example. Vui lòng cập nhật API key vào .env!")
        else:
            env_file.write_text("GROQ_API_KEY=\nGEMINI_API_KEY=\n", encoding="utf-8")
            print("📝 Đã tạo file .env mới.")
    else:
        print("✅ File .env đã tồn tại.")


def main():
    print("==================================================")
    print("🛠️ SETUP ENVIRONMENT - REUP VIDEO CHINNA TOOL")
    print("==================================================")
    init_env_file()
    check_and_install_requirements()
    print("\n✅ Hoàn tất thiết lập môi trường!")


if __name__ == "__main__":
    main()
