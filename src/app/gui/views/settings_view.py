"""
app/gui/views/settings_view.py
===============================
System Settings View with Basic & Advanced Configurations.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QFrame, QLabel, QLineEdit,
    QPushButton, QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget,
    QListWidgetItem, QMessageBox, QGroupBox
)

from app.core.config import config_instance
from app.core.prompt_engine import prompt_library_instance
from app.gui.components.key_manager_dialog import KeyManagerDialog
from app.gui.components.prompt_generator_dialog import PromptGeneratorDialog


class SettingsView(QWidget):
    """System Settings View for configuring default module behaviors & credentials."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        top_h = QHBoxLayout()
        top_h.addWidget(QLabel("🛠️ ReupTool V3 System Settings"))
        top_h.addStretch()

        btn_save_all = QPushButton("💾 Save All Settings")
        btn_save_all.setProperty("class", "PrimaryButton")
        btn_save_all.clicked.connect(self.save_settings)
        top_h.addWidget(btn_save_all)

        layout.addLayout(top_h)

        # Tab Widget
        self.tabs = QTabWidget()

        # 1. General Tab
        self.tabs.addTab(self._create_general_tab(), "General")

        # 2. Prompt Library Tab
        self.tabs.addTab(self._create_prompt_tab(), "Prompt Library")

        # 3. Audio & Chunking Tab
        self.tabs.addTab(self._create_audio_tab(), "Audio & Chunker")

        # 4. Transcriber & Translator Tab
        self.tabs.addTab(self._create_trans_tab(), "Transcriber & Translator")

        # 5. Dubber & Separation Tab
        self.tabs.addTab(self._create_dubber_tab(), "Dubber & Separator")

        # 6. Render Tab
        self.tabs.addTab(self._create_render_tab(), "Render Engine")

        layout.addWidget(self.tabs)

        self.load_settings()

    def _create_general_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        grp_api = QGroupBox("API Keys Pool Management")
        v_api = QVBoxLayout(grp_api)

        lbl_api = QLabel("Manage your Groq API Keys and Gemini API Keys with auto rotation & health checks.")
        v_api.addWidget(lbl_api)

        btn_key_mgr = QPushButton("🔑 Open API Key Pool Manager...")
        btn_key_mgr.setProperty("class", "PrimaryButton")
        btn_key_mgr.clicked.connect(lambda: KeyManagerDialog(self).exec())
        v_api.addWidget(btn_key_mgr)

        v.addWidget(grp_api)

        grp_gen = QGroupBox("General Options")
        v_gen = QVBoxLayout(grp_gen)

        self.chk_cache = QCheckBox("Enable Caching (Skip previously succeeded steps)")
        v_gen.addWidget(self.chk_cache)

        self.chk_retry = QCheckBox("Enable Global Automatic Retry on Step Failures")
        v_gen.addWidget(self.chk_retry)

        h_ret = QHBoxLayout()
        h_ret.addWidget(QLabel("Max Retries:"))
        self.spn_max_retries = QSpinBox()
        self.spn_max_retries.setRange(1, 10)
        h_ret.addWidget(self.spn_max_retries)
        v_gen.addLayout(h_ret)

        v.addWidget(grp_gen)
        v.addStretch()
        return w

    def _create_prompt_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        hint_lbl = QLabel(
            "Để quản lý đầy đủ (thêm/sửa/đổi tên/nhân bản/xóa/kích hoạt), dùng màn hình "
            "\"📝 Prompt dịch\" ở sidebar. Danh sách dưới đây chỉ mang tính tham khảo."
        )
        hint_lbl.setWordWrap(True)
        hint_lbl.setStyleSheet("color: #a0a0b0; font-size: 11px; margin-bottom: 4px;")
        v.addWidget(hint_lbl)

        top_h = QHBoxLayout()
        top_h.addWidget(QLabel("Saved Prompts:"))
        top_h.addStretch()

        btn_gen = QPushButton("⚡ Launch SRT Prompt Generator...")
        btn_gen.setProperty("class", "PrimaryButton")
        btn_gen.clicked.connect(lambda: PromptGeneratorDialog(self).exec())
        top_h.addWidget(btn_gen)

        v.addLayout(top_h)

        self.prompt_list = QListWidget()
        v.addWidget(self.prompt_list)

        self.reload_prompts()
        return w

    def reload_prompts(self):
        self.prompt_list.clear()
        prompts = prompt_library_instance.list_prompts()
        for p in prompts:
            status = "🟢 Active" if p.get("active") else "⚪ Inactive"
            item = QListWidgetItem(
                f"[{'Builtin' if p.get('is_builtin') else 'User'}] {p.get('name')} — {p.get('description')} ({status})"
            )
            self.prompt_list.addItem(item)

    def _create_audio_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        grp_ext = QGroupBox("Audio Extractor")
        v_ext = QVBoxLayout(grp_ext)

        h_sr = QHBoxLayout()
        h_sr.addWidget(QLabel("Sample Rate:"))
        self.cmb_sr = QComboBox()
        self.cmb_sr.addItems(["44100", "48000", "22050", "16000", "8000"])
        h_sr.addWidget(self.cmb_sr)
        v_ext.addLayout(h_sr)

        self.chk_norm = QCheckBox("Normalize Audio Loudness (loudnorm)")
        v_ext.addWidget(self.chk_norm)

        v.addWidget(grp_ext)

        grp_chk = QGroupBox("Smart Audio Chunker")
        v_chk = QVBoxLayout(grp_chk)

        h_size = QHBoxLayout()
        h_size.addWidget(QLabel("Max File Size (MB):"))
        self.spn_chunk_size = QDoubleSpinBox()
        self.spn_chunk_size.setRange(5.0, 50.0)
        self.spn_chunk_size.setValue(19.5)
        h_size.addWidget(self.spn_chunk_size)
        v_chk.addLayout(h_size)

        v.addWidget(grp_chk)
        v.addStretch()
        return w

    def _create_trans_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        grp_tr = QGroupBox("Transcriber (Groq Whisper)")
        v_tr = QVBoxLayout(grp_tr)

        h_m = QHBoxLayout()
        h_m.addWidget(QLabel("Model:"))
        self.cmb_groq_model = QComboBox()
        self.cmb_groq_model.addItems(["whisper-large-v3-turbo", "whisper-large-v3"])
        h_m.addWidget(self.cmb_groq_model)
        v_tr.addLayout(h_m)

        v.addWidget(grp_tr)

        grp_tl = QGroupBox("Translator (Gemini / Selenium)")
        v_tl = QVBoxLayout(grp_tl)

        h_mode = QHBoxLayout()
        h_mode.addWidget(QLabel("Mode:"))
        self.cmb_trans_mode = QComboBox()
        self.cmb_trans_mode.addItems(["auto", "gemini_api", "selenium"])
        h_mode.addWidget(self.cmb_trans_mode)
        v_tl.addLayout(h_mode)

        v.addWidget(grp_tl)
        v.addStretch()
        return w

    def _create_dubber_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        grp_dub = QGroupBox("Smart Dubber Pro (Edge TTS)")
        v_dub = QVBoxLayout(grp_dub)

        h_voice = QHBoxLayout()
        h_voice.addWidget(QLabel("Female Voice:"))
        self.cmb_voice_f = QComboBox()
        self.cmb_voice_f.addItems(["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"])
        h_voice.addWidget(self.cmb_voice_f)
        v_dub.addLayout(h_voice)

        h_mode = QHBoxLayout()
        h_mode.addWidget(QLabel("Dubbing Mode:"))
        self.cmb_dub_mode = QComboBox()
        self.cmb_dub_mode.addItems(["balanced", "time_first", "quality_first"])
        h_mode.addWidget(self.cmb_dub_mode)
        v_dub.addLayout(h_mode)

        v.addWidget(grp_dub)
        v.addStretch()
        return w

    def _create_render_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        grp_ren = QGroupBox("Render Engine (FFmpeg)")
        v_ren = QVBoxLayout(grp_ren)

        h_pre = QHBoxLayout()
        h_pre.addWidget(QLabel("Preset:"))
        self.cmb_preset = QComboBox()
        self.cmb_preset.addItems(["medium", "fast", "slow", "ultrafast"])
        h_pre.addWidget(self.cmb_preset)
        v_ren.addLayout(h_pre)

        h_crf = QHBoxLayout()
        h_crf.addWidget(QLabel("CRF Quality (Lower = Better):"))
        self.spn_crf = QSpinBox()
        self.spn_crf.setRange(10, 30)
        self.spn_crf.setValue(18)
        h_crf.addWidget(self.spn_crf)
        v_ren.addLayout(h_crf)

        v.addWidget(grp_ren)
        v.addStretch()
        return w

    def load_settings(self):
        self.chk_cache.setChecked(config_instance.get("general.enable_cache", True))
        self.chk_retry.setChecked(config_instance.get("general.enable_global_retry", True))
        self.spn_max_retries.setValue(config_instance.get("general.max_retries", 3))

        self.cmb_sr.setCurrentText(str(config_instance.get("modules.audio_extractor.sample_rate", 44100)))
        self.chk_norm.setChecked(config_instance.get("modules.audio_extractor.normalize", True))

        self.spn_chunk_size.setValue(config_instance.get("modules.audio_chunker.max_file_size_mb", 19.5))

        self.cmb_groq_model.setCurrentText(config_instance.get("modules.transcriber.model", "whisper-large-v3-turbo"))
        self.cmb_trans_mode.setCurrentText(config_instance.get("modules.translator.mode", "auto"))

        self.cmb_voice_f.setCurrentText(config_instance.get("modules.dubber.voice_female", "vi-VN-HoaiMyNeural"))
        self.cmb_dub_mode.setCurrentText(config_instance.get("modules.dubber.mode", "balanced"))

        self.cmb_preset.setCurrentText(config_instance.get("modules.render.preset", "medium"))
        self.spn_crf.setValue(config_instance.get("modules.render.crf", 18))

    def save_settings(self):
        config_instance.set("general.enable_cache", self.chk_cache.isChecked(), save_immediately=False)
        config_instance.set("general.enable_global_retry", self.chk_retry.isChecked(), save_immediately=False)
        config_instance.set("general.max_retries", self.spn_max_retries.value(), save_immediately=False)

        config_instance.set("modules.audio_extractor.sample_rate", int(self.cmb_sr.currentText()), save_immediately=False)
        config_instance.set("modules.audio_extractor.normalize", self.chk_norm.isChecked(), save_immediately=False)

        config_instance.set("modules.audio_chunker.max_file_size_mb", self.spn_chunk_size.value(), save_immediately=False)

        config_instance.set("modules.transcriber.model", self.cmb_groq_model.currentText(), save_immediately=False)
        config_instance.set("modules.translator.mode", self.cmb_trans_mode.currentText(), save_immediately=False)

        config_instance.set("modules.dubber.voice_female", self.cmb_voice_f.currentText(), save_immediately=False)
        config_instance.set("modules.dubber.mode", self.cmb_dub_mode.currentText(), save_immediately=False)

        config_instance.set("modules.render.preset", self.cmb_preset.currentText(), save_immediately=False)
        config_instance.set("modules.render.crf", self.spn_crf.value(), save_immediately=False)

        if config_instance.save():
            QMessageBox.information(self, "Saved", "All settings saved successfully!")
        else:
            QMessageBox.critical(self, "Error", "Failed to save settings!")
