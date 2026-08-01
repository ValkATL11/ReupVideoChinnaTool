from pathlib import Path
import sys
import numpy as np
from scipy import signal
from pydub import AudioSegment

def load_audio(file_path: Path):
    """Đọc file MP3 và chuyển thành numpy array (Stereo, float32 [-1.0, 1.0])."""
    audio = AudioSegment.from_file(file_path)
    sr = audio.frame_rate
    channels = audio.channels

    if channels < 2:
        raise ValueError("File audio phải là Stereo (2 kênh) để xử lý.")

    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    max_val = float(1 << (8 * audio.sample_width - 1))
    samples /= max_val
    samples = samples.reshape((-1, channels)).T
    return samples, sr

def save_audio(samples: np.ndarray, sr: int, output_path: Path):
    """Chuyển numpy array thành MP3 và lưu file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    samples = np.clip(samples, -1.0, 1.0)
    int16_samples = (samples * 32767).astype(np.int16)
    interleaved = int16_samples.T.flatten()

    audio = AudioSegment(
        data=interleaved.tobytes(),
        sample_width=2,
        frame_rate=sr,
        channels=2
    )
    audio.export(output_path, format="mp3")

# =====================================================================
# CHẾ ĐỘ 1: Pure Phase Cancellation (Lồng tiếng + Nhạc nhẹ + SFX rõ)
# =====================================================================
def process_voiceover_mode(stereo_audio: np.ndarray, sr: int) -> np.ndarray:
    L, R = stereo_audio[0], stereo_audio[1]
    
    accompaniment_mono = (L - R) * 0.5
    
    # Bảo toàn dải Bass (< 120Hz)
    sos = signal.butter(4, 120, "lowpass", fs=sr, output="sos")
    bass_mono = signal.sosfilt(sos, (L + R) * 0.5)

    out_L = accompaniment_mono + bass_mono
    out_R = -accompaniment_mono + bass_mono
    return np.ascontiguousarray(np.vstack((out_L, out_R)))

# =====================================================================
# CHẾ ĐỘ 2: Multi-band Mid-Side (Nhạc nền có lời + SFX dày đặc)
# =====================================================================
def process_music_sfx_mode(stereo_audio: np.ndarray, sr: int, vocal_leak: float = 0.12) -> np.ndarray:
    L, R = stereo_audio[0], stereo_audio[1]

    mid = (L + R) * 0.5
    side = (L - R) * 0.5

    # 1. Dải Bass (< 150Hz) - Giữ nguyên 100%
    sos_bass = signal.butter(4, 150, btype='lowpass', fs=sr, output='sos')
    mid_bass = signal.sosfilt(sos_bass, mid)

    # 2. Dải Treble SFX (> 5000Hz) - Giữ nguyên 100%
    sos_treble = signal.butter(4, 5000, btype='highpass', fs=sr, output='sos')
    mid_treble = signal.sosfilt(sos_treble, mid)

    # 3. Dải Vocal Zone (150Hz - 5000Hz) - Hạ sâu, chỉ giữ lại 12%
    sos_vocal = signal.butter(4, [150, 5000], btype='bandpass', fs=sr, output='sos')
    mid_vocal_reduced = signal.sosfilt(sos_vocal, mid) * vocal_leak

    # Reconstruct
    mid_reconstructed = mid_bass + mid_treble + mid_vocal_reduced

    out_L = mid_reconstructed + side
    out_R = mid_reconstructed - side
    return np.ascontiguousarray(np.vstack((out_L, out_R)))

def show_menu() -> str:
    """Hiển thị menu cho người dùng chọn chế độ."""
    print("==================================================")
    print("       CHỌN CHẾ ĐỘ XỬ LÝ VOCAL & SFX              ")
    print("==================================================")
    print("1. Chế độ 1: Lồng tiếng rõ + Nhạc nhẹ (Cắt sạch vocal, SFX rõ)")
    print("2. Chế độ 2: Nhạc nền có lời + SFX dày (Ép nhỏ vocal, giữ tối đa SFX)")
    print("==================================================")
    
    while True:
        choice = input("Nhập lựa chọn của bạn (1 hoặc 2): ").strip()
        if choice in ["1", "2"]:
            return choice
        print("[!] Lựa chọn không hợp lệ. Vui lòng chọn 1 hoặc 2.")

def main():
    input_dir = Path("original_audios")
    output_dir = Path("separated_audios")

    if not input_dir.exists():
        print(f"[-] Thư mục '{input_dir}' không tồn tại. Vui lòng tạo thư mục và thêm file MP3.")
        sys.exit(1)

    input_files = list(input_dir.glob("*_Oaudio.mp3"))
    if not input_files:
        print(f"[-] Không tìm thấy file dạng '*_Oaudio.mp3' trong thư mục '{input_dir}'.")
        sys.exit(1)

    # Cho người dùng chọn chế độ từ terminal
    choice = show_menu()
    mode_name = "Lồng tiếng (Pure Phase)" if choice == "1" else "Nhạc + SFX dày (Multi-band)"
    print(f"\n[➔] Đã chọn chế độ: {mode_name}\n")

    for input_path in input_files:
        project_id = input_path.stem.removesuffix("_Oaudio")
        output_path = output_dir / f"{project_id}_Nvocal.mp3"

        print(f"[+] Đang xử lý PROJECT_ID: {project_id}")
        print(f"    In:  {input_path}")
        print(f"    Out: {output_path}")

        try:
            stereo_audio, sr = load_audio(input_path)

            if choice == "1":
                processed_audio = process_voiceover_mode(stereo_audio, sr)
            else:
                processed_audio = process_music_sfx_mode(stereo_audio, sr, vocal_leak=0.12)

            save_audio(processed_audio, sr, output_path)
            print(f"[✔] Hoàn thành: {output_path.name}\n")

        except Exception as e:
            print(f"[!] Lỗi khi xử lý file {input_path.name}: {e}\n")

if __name__ == "__main__":
    main()