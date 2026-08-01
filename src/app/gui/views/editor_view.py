"""
app/gui/views/editor_view.py
=============================
Visual Editor View - Simple Edit.

Timeline scrubbing with guaranteed real-frame capture (no placeholder/mock fallback),
plus full Add / Edit / Delete management for:
  - Multiple custom subtitles (text, position, font size/color, background on/off + color)
  - Multiple blur regions (position, size, blur strength)
  - Multiple logo/watermark overlays (position, size, opacity)

All fields write directly into EditorOverlayConfig and are persisted to editor_config.json,
which RenderService reads to actually build the FFmpeg filter graph used by Preview/Render.
"""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QSlider, QSpinBox, QDoubleSpinBox, QCheckBox, QFileDialog, QMessageBox,
    QTabWidget, QListWidget, QListWidgetItem, QLineEdit, QColorDialog,
    QFormLayout, QSizePolicy
)

from app.core.project import Project
from app.editor.editor_config import EditorOverlayConfig
from app.editor.frame_extractor import FrameExtractor
from app.gui.components.editor_canvas import EditorCanvasView, KIND_SUBTITLE, KIND_BLUR, KIND_LOGO
from render import get_video_duration


class ColorButton(QPushButton):
    """Small button showing a color swatch; click opens a color picker."""

    def __init__(self, hex_color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self.hex_color = hex_color
        self.setFixedSize(48, 24)
        self._on_changed = None
        self.clicked.connect(self._pick_color)
        self._refresh()

    def set_on_changed(self, callback):
        self._on_changed = callback

    def set_color(self, hex_color: str):
        self.hex_color = hex_color or "#FFFFFF"
        self._refresh()

    def _refresh(self):
        self.setStyleSheet(
            f"background-color: {self.hex_color}; border: 1px solid #555; border-radius: 4px;"
        )

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self.hex_color), self, "Chọn màu")
        if color.isValid():
            self.hex_color = color.name()
            self._refresh()
            if self._on_changed:
                self._on_changed(self.hex_color)


class VisualEditorView(QWidget):
    """Simple Edit visual overlay editor: Subtitle / Blur / Logo, all list-managed."""

    # Emitted with project_id right after editor_config.json is written by
    # "Save & Continue", so the app can automatically resume the pipeline
    # (Audio Extraction -> STT -> Translation -> TTS -> ... -> Render).
    config_saved = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_project: Optional[Project] = None
        self.overlay_config: Optional[EditorOverlayConfig] = None
        self.frame_extractor = FrameExtractor()

        self.video_duration_sec = 0.0
        self.current_time_sec = 0.0

        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.timeout.connect(lambda: self.update_frame(force=True))

        self._selected_subtitle_id: Optional[str] = None
        self._selected_blur_id: Optional[str] = None
        self._selected_logo_id: Optional[str] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # ---------------- Left Column: Canvas & Timeline ----------------
        left_layout = QVBoxLayout()

        self.canvas = EditorCanvasView(self)
        self.canvas.overlay_changed.connect(self._on_canvas_dragged)
        self.canvas.item_selected.connect(self._on_canvas_item_selected)
        left_layout.addWidget(self.canvas)

        timeline_card = QFrame()
        timeline_card.setProperty("class", "CardFrame")
        v_time = QVBoxLayout(timeline_card)

        h_time_lbl = QHBoxLayout()
        self.lbl_current_time = QLabel("Timestamp: 00.00s")
        self.lbl_current_time.setStyleSheet("font-weight: bold; color: #0078d4;")
        h_time_lbl.addWidget(self.lbl_current_time)
        h_time_lbl.addStretch()
        self.lbl_duration = QLabel("Duration: 00.00s")
        h_time_lbl.addWidget(self.lbl_duration)
        v_time.addLayout(h_time_lbl)

        self.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setRange(0, 1000)
        self.timeline_slider.valueChanged.connect(self._on_slider_changed)
        v_time.addWidget(self.timeline_slider)

        h_seek = QHBoxLayout()
        btn_prev = QPushButton("◀ Prev Frame")
        btn_prev.setProperty("class", "SecondaryButton")
        btn_prev.clicked.connect(lambda: self.seek(self.current_time_sec - 0.04))
        h_seek.addWidget(btn_prev)

        btn_capture = QPushButton("📷 Capture Frame")
        btn_capture.setProperty("class", "PrimaryButton")
        btn_capture.clicked.connect(lambda: self.update_frame(force=True))
        h_seek.addWidget(btn_capture)

        btn_next = QPushButton("Next Frame ▶")
        btn_next.setProperty("class", "SecondaryButton")
        btn_next.clicked.connect(lambda: self.seek(self.current_time_sec + 0.04))
        h_seek.addWidget(btn_next)

        v_time.addLayout(h_seek)
        left_layout.addWidget(timeline_card)
        layout.addLayout(left_layout, stretch=3)

        # ---------------- Right Column: Tabbed Overlay Manager ----------------
        right_panel = QFrame()
        right_panel.setFixedWidth(360)
        right_panel.setProperty("class", "CardFrame")
        v_right = QVBoxLayout(right_panel)
        v_right.addWidget(QLabel("🎛️ Simple Edit - Overlays"))

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_subtitle_tab(), "Subtitle")
        self.tabs.addTab(self._build_blur_tab(), "Blur")
        self.tabs.addTab(self._build_logo_tab(), "Logo")
        v_right.addWidget(self.tabs, stretch=1)

        btn_save = QPushButton("💾 Save & Continue")
        btn_save.setProperty("class", "PrimaryButton")
        btn_save.setStyleSheet("font-size: 15px; padding: 10px;")
        btn_save.clicked.connect(self.save_configuration)
        v_right.addWidget(btn_save)

        layout.addWidget(right_panel, stretch=1)

    # ==================================================================
    # Tab builders
    # ==================================================================
    def _build_subtitle_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        self.list_subs = QListWidget()
        self.list_subs.currentItemChanged.connect(self._on_subtitle_list_selection)
        v.addWidget(self.list_subs)

        h_btn = QHBoxLayout()
        btn_add = QPushButton("+ Add Subtitle")
        btn_add.clicked.connect(self._add_subtitle)
        btn_del = QPushButton("🗑 Delete")
        btn_del.clicked.connect(self._delete_subtitle)
        h_btn.addWidget(btn_add)
        h_btn.addWidget(btn_del)
        v.addLayout(h_btn)

        form = QFormLayout()
        self.sub_chk_enabled = QCheckBox("Enabled")
        self.sub_chk_enabled.toggled.connect(self._on_subtitle_field_changed)
        form.addRow(self.sub_chk_enabled)

        self.sub_txt = QLineEdit()
        self.sub_txt.textChanged.connect(self._on_subtitle_field_changed)
        form.addRow("Text:", self.sub_txt)

        self.sub_x = QDoubleSpinBox(); self.sub_x.setRange(0, 100); self.sub_x.setSuffix(" %")
        self.sub_x.valueChanged.connect(self._on_subtitle_field_changed)
        form.addRow("Vị trí X:", self.sub_x)

        self.sub_y = QDoubleSpinBox(); self.sub_y.setRange(0, 100); self.sub_y.setSuffix(" %")
        self.sub_y.valueChanged.connect(self._on_subtitle_field_changed)
        form.addRow("Vị trí Y:", self.sub_y)

        self.sub_font_size = QSpinBox(); self.sub_font_size.setRange(6, 200)
        self.sub_font_size.valueChanged.connect(self._on_subtitle_field_changed)
        form.addRow("Cỡ chữ:", self.sub_font_size)

        self.sub_font_color = ColorButton("#FFFFFF")
        self.sub_font_color.set_on_changed(lambda c: self._on_subtitle_field_changed())
        form.addRow("Màu chữ:", self.sub_font_color)

        self.sub_bg_enabled = QCheckBox("Bật nền")
        self.sub_bg_enabled.toggled.connect(self._on_subtitle_field_changed)
        form.addRow(self.sub_bg_enabled)

        self.sub_bg_color = ColorButton("#000000")
        self.sub_bg_color.set_on_changed(lambda c: self._on_subtitle_field_changed())
        form.addRow("Màu nền:", self.sub_bg_color)

        self.sub_bg_opacity = QDoubleSpinBox(); self.sub_bg_opacity.setRange(0, 1); self.sub_bg_opacity.setSingleStep(0.05)
        self.sub_bg_opacity.valueChanged.connect(self._on_subtitle_field_changed)
        form.addRow("Độ mờ nền:", self.sub_bg_opacity)

        self.sub_bg_pad_x = QSpinBox(); self.sub_bg_pad_x.setRange(0, 200); self.sub_bg_pad_x.setSuffix(" px")
        self.sub_bg_pad_x.valueChanged.connect(self._on_subtitle_field_changed)
        form.addRow("Padding ngang:", self.sub_bg_pad_x)

        self.sub_bg_pad_y = QSpinBox(); self.sub_bg_pad_y.setRange(0, 200); self.sub_bg_pad_y.setSuffix(" px")
        self.sub_bg_pad_y.valueChanged.connect(self._on_subtitle_field_changed)
        form.addRow("Padding dọc:", self.sub_bg_pad_y)

        self.sub_bg_radius = QSpinBox(); self.sub_bg_radius.setRange(0, 100); self.sub_bg_radius.setSuffix(" px")
        self.sub_bg_radius.valueChanged.connect(self._on_subtitle_field_changed)
        form.addRow("Bo góc nền:", self.sub_bg_radius)

        v.addLayout(form)
        self._sub_form_widgets = [
            self.sub_chk_enabled, self.sub_txt, self.sub_x, self.sub_y,
            self.sub_font_size, self.sub_font_color, self.sub_bg_enabled,
            self.sub_bg_color, self.sub_bg_opacity,
            self.sub_bg_pad_x, self.sub_bg_pad_y, self.sub_bg_radius
        ]
        self._set_widgets_enabled(self._sub_form_widgets, False)
        return w

    def _build_blur_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        self.list_blurs = QListWidget()
        self.list_blurs.currentItemChanged.connect(self._on_blur_list_selection)
        v.addWidget(self.list_blurs)

        h_btn = QHBoxLayout()
        btn_add = QPushButton("+ Add Blur")
        btn_add.clicked.connect(self._add_blur)
        btn_del = QPushButton("🗑 Delete")
        btn_del.clicked.connect(self._delete_blur)
        h_btn.addWidget(btn_add)
        h_btn.addWidget(btn_del)
        v.addLayout(h_btn)

        form = QFormLayout()
        self.blur_chk_enabled = QCheckBox("Enabled")
        self.blur_chk_enabled.toggled.connect(self._on_blur_field_changed)
        form.addRow(self.blur_chk_enabled)

        self.blur_x = QDoubleSpinBox(); self.blur_x.setRange(0, 100); self.blur_x.setSuffix(" %")
        self.blur_x.valueChanged.connect(self._on_blur_field_changed)
        form.addRow("X:", self.blur_x)

        self.blur_y = QDoubleSpinBox(); self.blur_y.setRange(0, 100); self.blur_y.setSuffix(" %")
        self.blur_y.valueChanged.connect(self._on_blur_field_changed)
        form.addRow("Y:", self.blur_y)

        self.blur_w = QDoubleSpinBox(); self.blur_w.setRange(1, 100); self.blur_w.setSuffix(" %")
        self.blur_w.valueChanged.connect(self._on_blur_field_changed)
        form.addRow("Width:", self.blur_w)

        self.blur_h = QDoubleSpinBox(); self.blur_h.setRange(1, 100); self.blur_h.setSuffix(" %")
        self.blur_h.valueChanged.connect(self._on_blur_field_changed)
        form.addRow("Height:", self.blur_h)

        self.blur_strength = QSpinBox(); self.blur_strength.setRange(1, 50)
        self.blur_strength.valueChanged.connect(self._on_blur_field_changed)
        form.addRow("Độ mạnh blur:", self.blur_strength)

        v.addLayout(form)
        self._blur_form_widgets = [
            self.blur_chk_enabled, self.blur_x, self.blur_y, self.blur_w, self.blur_h, self.blur_strength
        ]
        self._set_widgets_enabled(self._blur_form_widgets, False)
        return w

    def _build_logo_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        self.list_logos = QListWidget()
        self.list_logos.currentItemChanged.connect(self._on_logo_list_selection)
        v.addWidget(self.list_logos)

        h_btn = QHBoxLayout()
        btn_add = QPushButton("+ Add Logo")
        btn_add.clicked.connect(self._add_logo)
        btn_del = QPushButton("🗑 Delete")
        btn_del.clicked.connect(self._delete_logo)
        h_btn.addWidget(btn_add)
        h_btn.addWidget(btn_del)
        v.addLayout(h_btn)

        form = QFormLayout()
        self.logo_chk_enabled = QCheckBox("Enabled")
        self.logo_chk_enabled.toggled.connect(self._on_logo_field_changed)
        form.addRow(self.logo_chk_enabled)

        self.logo_path_lbl = QLabel("(no image)")
        self.logo_path_lbl.setWordWrap(True)
        form.addRow("Ảnh:", self.logo_path_lbl)

        btn_pick = QPushButton("Chọn ảnh logo...")
        btn_pick.clicked.connect(self._pick_logo_image)
        form.addRow(btn_pick)

        self.logo_x = QDoubleSpinBox(); self.logo_x.setRange(0, 100); self.logo_x.setSuffix(" %")
        self.logo_x.valueChanged.connect(self._on_logo_field_changed)
        form.addRow("X:", self.logo_x)

        self.logo_y = QDoubleSpinBox(); self.logo_y.setRange(0, 100); self.logo_y.setSuffix(" %")
        self.logo_y.valueChanged.connect(self._on_logo_field_changed)
        form.addRow("Y:", self.logo_y)

        self.logo_w = QDoubleSpinBox(); self.logo_w.setRange(1, 100); self.logo_w.setSuffix(" %")
        self.logo_w.valueChanged.connect(self._on_logo_field_changed)
        form.addRow("Width:", self.logo_w)

        self.logo_h = QDoubleSpinBox(); self.logo_h.setRange(1, 100); self.logo_h.setSuffix(" %")
        self.logo_h.valueChanged.connect(self._on_logo_field_changed)
        form.addRow("Height:", self.logo_h)

        self.logo_opacity = QDoubleSpinBox(); self.logo_opacity.setRange(0, 1); self.logo_opacity.setSingleStep(0.05)
        self.logo_opacity.valueChanged.connect(self._on_logo_field_changed)
        form.addRow("Opacity:", self.logo_opacity)

        v.addLayout(form)
        self._logo_form_widgets = [
            self.logo_chk_enabled, self.logo_x, self.logo_y, self.logo_w, self.logo_h, self.logo_opacity
        ]
        self._set_widgets_enabled(self._logo_form_widgets, False)
        return w

    @staticmethod
    def _set_widgets_enabled(widgets, enabled: bool):
        for w in widgets:
            w.setEnabled(enabled)

    # ==================================================================
    # Project loading
    # ==================================================================
    def set_project(self, project_id: str):
        self.active_project = Project(project_id)
        self.overlay_config = EditorOverlayConfig(project_id)

        if self.active_project.editor_config_path.exists():
            self.overlay_config.load(self.active_project.editor_config_path)

        video_path = self.active_project.raw_video_path
        if video_path.exists():
            self.video_duration_sec = get_video_duration(video_path)
            self.lbl_duration.setText(f"Duration: {self.video_duration_sec:.2f}s")
        else:
            self.video_duration_sec = 0.0
            self.lbl_duration.setText("Duration: (no video)")

        self._refresh_subtitle_list()
        self._refresh_blur_list()
        self._refresh_logo_list()
        self.update_frame(force=True)

    # ==================================================================
    # Timeline / Frame capture (fixed: always uses a REAL extracted frame,
    # never a gray placeholder, unless there genuinely is no video file yet)
    # ==================================================================
    def seek(self, target_sec: float):
        target_sec = max(0.0, min(self.video_duration_sec, target_sec))
        self.current_time_sec = target_sec

        if self.video_duration_sec > 0:
            val = int((target_sec / self.video_duration_sec) * 1000)
            self.timeline_slider.blockSignals(True)
            self.timeline_slider.setValue(val)
            self.timeline_slider.blockSignals(False)

        self.lbl_current_time.setText(f"Timestamp: {target_sec:.2f}s")
        self.update_frame(force=True)

    def _on_slider_changed(self, val: int):
        if self.video_duration_sec <= 0:
            return
        self.current_time_sec = (val / 1000.0) * self.video_duration_sec
        self.lbl_current_time.setText(f"Timestamp: {self.current_time_sec:.2f}s")
        # Debounce rapid drag: only fire the real ffmpeg extraction after the
        # slider has been still for a short moment, but ALWAYS force a real
        # frame once it does (never fall back to a placeholder).
        self._seek_timer.start(120)

    def update_frame(self, force: bool = False):
        if not self.active_project or not self.overlay_config:
            return

        video_path = self.active_project.raw_video_path
        if not video_path.exists():
            # No video uploaded yet for this project - legitimately nothing to show.
            self.canvas.load_frame(None, self.overlay_config)
            return

        frame_path = self.frame_extractor.get_frame(video_path, self.current_time_sec, force=force)
        if frame_path is None:
            if force:
                QMessageBox.warning(
                    self, "Frame Capture Failed",
                    f"Không thể trích xuất frame thực tế tại {self.current_time_sec:.2f}s.\n"
                    "Video hiện tại vẫn được giữ nguyên trên canvas."
                )
            # Keep whatever frame is already displayed instead of showing a fake one.
            return

        self.canvas.load_frame(frame_path, self.overlay_config)

    def _on_canvas_dragged(self):
        """Called after the user drags an overlay item on the canvas."""
        self._sync_forms_from_config()

    def _on_canvas_item_selected(self, kind: str, item_id: str):
        if kind == KIND_SUBTITLE:
            self.tabs.setCurrentIndex(0)
            self._select_list_item(self.list_subs, item_id)
        elif kind == KIND_BLUR:
            self.tabs.setCurrentIndex(1)
            self._select_list_item(self.list_blurs, item_id)
        elif kind == KIND_LOGO:
            self.tabs.setCurrentIndex(2)
            self._select_list_item(self.list_logos, item_id)

    @staticmethod
    def _select_list_item(list_widget: QListWidget, item_id: str):
        for i in range(list_widget.count()):
            it = list_widget.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == item_id:
                list_widget.setCurrentItem(it)
                return

    def _sync_forms_from_config(self):
        if self._selected_subtitle_id:
            self._load_subtitle_form(self._selected_subtitle_id)
        if self._selected_blur_id:
            self._load_blur_form(self._selected_blur_id)
        if self._selected_logo_id:
            self._load_logo_form(self._selected_logo_id)

    # ==================================================================
    # Subtitle CRUD
    # ==================================================================
    def _refresh_subtitle_list(self):
        self.list_subs.blockSignals(True)
        self.list_subs.clear()
        for s in self.overlay_config.subtitles:
            label = f"{'✓' if s.get('enabled', True) else '✗'} {s.get('text', '')[:28] or '(empty)'}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.list_subs.addItem(item)
        self.list_subs.blockSignals(False)

    def _add_subtitle(self):
        if not self.overlay_config:
            return
        item = self.overlay_config.add_subtitle()
        self._refresh_subtitle_list()
        self._select_list_item(self.list_subs, item["id"])
        self.update_frame(force=False)

    def _delete_subtitle(self):
        if not self.overlay_config or not self._selected_subtitle_id:
            return
        self.overlay_config.remove_subtitle(self._selected_subtitle_id)
        self._selected_subtitle_id = None
        self._refresh_subtitle_list()
        self._set_widgets_enabled(self._sub_form_widgets, False)
        self.update_frame(force=False)

    def _on_subtitle_list_selection(self, current, _previous):
        if current is None:
            self._selected_subtitle_id = None
            self._set_widgets_enabled(self._sub_form_widgets, False)
            return
        item_id = current.data(Qt.ItemDataRole.UserRole)
        self._selected_subtitle_id = item_id
        self._load_subtitle_form(item_id)

    def _load_subtitle_form(self, item_id: str):
        data = self.overlay_config.get_subtitle(item_id)
        if not data:
            return
        for w in self._sub_form_widgets:
            w.blockSignals(True)
        self.sub_chk_enabled.setChecked(data.get("enabled", True))
        self.sub_txt.setText(data.get("text", ""))
        self.sub_x.setValue(data.get("x_pct", 50.0))
        self.sub_y.setValue(data.get("y_pct", 85.0))
        self.sub_font_size.setValue(data.get("font_size", 24))
        self.sub_font_color.set_color(data.get("font_color", "#FFFFFF"))
        self.sub_bg_enabled.setChecked(data.get("bg_enabled", True))
        self.sub_bg_color.set_color(data.get("bg_color", "#000000"))
        self.sub_bg_opacity.setValue(data.get("bg_opacity", 0.5))
        self.sub_bg_pad_x.setValue(int(data.get("bg_padding_x", 12.0)))
        self.sub_bg_pad_y.setValue(int(data.get("bg_padding_y", 8.0)))
        self.sub_bg_radius.setValue(int(data.get("bg_corner_radius", 6.0)))
        for w in self._sub_form_widgets:
            w.blockSignals(False)
        self._set_widgets_enabled(self._sub_form_widgets, True)

    def _on_subtitle_field_changed(self, *_args):
        if not self.overlay_config or not self._selected_subtitle_id:
            return
        self.overlay_config.update_subtitle(
            self._selected_subtitle_id,
            enabled=self.sub_chk_enabled.isChecked(),
            text=self.sub_txt.text(),
            x_pct=self.sub_x.value(),
            y_pct=self.sub_y.value(),
            font_size=self.sub_font_size.value(),
            font_color=self.sub_font_color.hex_color,
            bg_enabled=self.sub_bg_enabled.isChecked(),
            bg_color=self.sub_bg_color.hex_color,
            bg_opacity=self.sub_bg_opacity.value(),
            bg_padding_x=self.sub_bg_pad_x.value(),
            bg_padding_y=self.sub_bg_pad_y.value(),
            bg_corner_radius=self.sub_bg_radius.value(),
        )
        self._refresh_subtitle_list()
        self._select_list_item(self.list_subs, self._selected_subtitle_id)
        self.update_frame(force=False)

    # ==================================================================
    # Blur CRUD
    # ==================================================================
    def _refresh_blur_list(self):
        self.list_blurs.blockSignals(True)
        self.list_blurs.clear()
        for i, b in enumerate(self.overlay_config.blur_regions):
            label = f"{'✓' if b.get('enabled', True) else '✗'} Blur #{i + 1} ({b.get('blur_strength', 10)})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, b["id"])
            self.list_blurs.addItem(item)
        self.list_blurs.blockSignals(False)

    def _add_blur(self):
        if not self.overlay_config:
            return
        item = self.overlay_config.add_blur()
        self._refresh_blur_list()
        self._select_list_item(self.list_blurs, item["id"])
        self.update_frame(force=False)

    def _delete_blur(self):
        if not self.overlay_config or not self._selected_blur_id:
            return
        self.overlay_config.remove_blur(self._selected_blur_id)
        self._selected_blur_id = None
        self._refresh_blur_list()
        self._set_widgets_enabled(self._blur_form_widgets, False)
        self.update_frame(force=False)

    def _on_blur_list_selection(self, current, _previous):
        if current is None:
            self._selected_blur_id = None
            self._set_widgets_enabled(self._blur_form_widgets, False)
            return
        item_id = current.data(Qt.ItemDataRole.UserRole)
        self._selected_blur_id = item_id
        self._load_blur_form(item_id)

    def _load_blur_form(self, item_id: str):
        data = self.overlay_config.get_blur(item_id)
        if not data:
            return
        for w in self._blur_form_widgets:
            w.blockSignals(True)
        self.blur_chk_enabled.setChecked(data.get("enabled", True))
        self.blur_x.setValue(data.get("x_pct", 10.0))
        self.blur_y.setValue(data.get("y_pct", 80.0))
        self.blur_w.setValue(data.get("width_pct", 80.0))
        self.blur_h.setValue(data.get("height_pct", 12.0))
        self.blur_strength.setValue(data.get("blur_strength", 10))
        for w in self._blur_form_widgets:
            w.blockSignals(False)
        self._set_widgets_enabled(self._blur_form_widgets, True)

    def _on_blur_field_changed(self, *_args):
        if not self.overlay_config or not self._selected_blur_id:
            return
        self.overlay_config.update_blur(
            self._selected_blur_id,
            enabled=self.blur_chk_enabled.isChecked(),
            x_pct=self.blur_x.value(),
            y_pct=self.blur_y.value(),
            width_pct=self.blur_w.value(),
            height_pct=self.blur_h.value(),
            blur_strength=self.blur_strength.value(),
        )
        self._refresh_blur_list()
        self._select_list_item(self.list_blurs, self._selected_blur_id)
        self.update_frame(force=False)

    # ==================================================================
    # Logo CRUD
    # ==================================================================
    def _refresh_logo_list(self):
        self.list_logos.blockSignals(True)
        self.list_logos.clear()
        for i, l in enumerate(self.overlay_config.logos):
            name = Path(l["image_path"]).name if l.get("image_path") else "(no image)"
            label = f"{'✓' if l.get('enabled', True) else '✗'} Logo #{i + 1} - {name}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, l["id"])
            self.list_logos.addItem(item)
        self.list_logos.blockSignals(False)

    def _add_logo(self):
        if not self.overlay_config:
            return
        item = self.overlay_config.add_logo()
        self._refresh_logo_list()
        self._select_list_item(self.list_logos, item["id"])
        self.update_frame(force=False)

    def _delete_logo(self):
        if not self.overlay_config or not self._selected_logo_id:
            return
        self.overlay_config.remove_logo(self._selected_logo_id)
        self._selected_logo_id = None
        self._refresh_logo_list()
        self._set_widgets_enabled(self._logo_form_widgets, False)
        self.logo_path_lbl.setText("(no image)")
        self.update_frame(force=False)

    def _on_logo_list_selection(self, current, _previous):
        if current is None:
            self._selected_logo_id = None
            self._set_widgets_enabled(self._logo_form_widgets, False)
            self.logo_path_lbl.setText("(no image)")
            return
        item_id = current.data(Qt.ItemDataRole.UserRole)
        self._selected_logo_id = item_id
        self._load_logo_form(item_id)

    def _load_logo_form(self, item_id: str):
        data = self.overlay_config.get_logo(item_id)
        if not data:
            return
        for w in self._logo_form_widgets:
            w.blockSignals(True)
        self.logo_chk_enabled.setChecked(data.get("enabled", True))
        self.logo_x.setValue(data.get("x_pct", 5.0))
        self.logo_y.setValue(data.get("y_pct", 5.0))
        self.logo_w.setValue(data.get("width_pct", 15.0))
        self.logo_h.setValue(data.get("height_pct", 10.0))
        self.logo_opacity.setValue(data.get("opacity", 0.8))
        for w in self._logo_form_widgets:
            w.blockSignals(False)
        img_path = data.get("image_path")
        self.logo_path_lbl.setText(Path(img_path).name if img_path else "(no image)")
        self._set_widgets_enabled(self._logo_form_widgets, True)

    def _pick_logo_image(self):
        if not self._selected_logo_id:
            QMessageBox.information(self, "Chưa chọn Logo", "Hãy bấm '+ Add Logo' trước, rồi chọn ảnh.")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Logo Image", "", "Images (*.png *.jpg *.jpeg)")
        if file_path:
            self.overlay_config.update_logo(self._selected_logo_id, image_path=file_path, enabled=True)
            self.logo_chk_enabled.blockSignals(True)
            self.logo_chk_enabled.setChecked(True)
            self.logo_chk_enabled.blockSignals(False)
            self.logo_path_lbl.setText(Path(file_path).name)
            self._refresh_logo_list()
            self._select_list_item(self.list_logos, self._selected_logo_id)
            self.update_frame(force=False)

    def _on_logo_field_changed(self, *_args):
        if not self.overlay_config or not self._selected_logo_id:
            return
        self.overlay_config.update_logo(
            self._selected_logo_id,
            enabled=self.logo_chk_enabled.isChecked(),
            x_pct=self.logo_x.value(),
            y_pct=self.logo_y.value(),
            width_pct=self.logo_w.value(),
            height_pct=self.logo_h.value(),
            opacity=self.logo_opacity.value(),
        )
        self._refresh_logo_list()
        self._select_list_item(self.list_logos, self._selected_logo_id)
        self.update_frame(force=False)

    # ==================================================================
    # Save
    # ==================================================================
    def save_configuration(self):
        """Serialize the entire in-memory editor session state into a single
        editor_config.json (this is the ONLY point where Simple Editor writes
        to disk - individual edits during the session never touch the file).
        The saved config applies to the whole video; the on-canvas frame was
        only ever a positioning reference."""
        if not self.active_project or not self.overlay_config:
            return

        cfg_path = self.active_project.editor_config_path
        if self.overlay_config.save(cfg_path):
            QMessageBox.information(
                self, "Saved",
                f"Simple Editor configuration saved to:\n{cfg_path.name}\n\nTiếp tục pipeline..."
            )
            self.config_saved.emit(self.active_project.project_id)
        else:
            QMessageBox.critical(self, "Error", "Failed to save Visual Editor configuration!")
