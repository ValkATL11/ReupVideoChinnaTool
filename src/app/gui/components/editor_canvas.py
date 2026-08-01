"""
app/gui/components/editor_canvas.py
===================================
Interactive QGraphicsView Canvas with Percentage-based Drag Subtitles, Blur Regions & Logos.

Supports an arbitrary number of items per overlay type at once. Each graphics item carries
its (kind, item_id) as Qt item-data so the scene can report moves/selection back to the
owning EditorOverlayConfig without needing a 1:1 attribute per overlay (as the old
single-item version did).
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QFont, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsTextItem, QGraphicsPixmapItem, QGraphicsItem, QGraphicsPathItem
)

from app.editor.editor_config import EditorOverlayConfig

logger = logging.getLogger("EditorCanvas")

KIND_SUBTITLE = "subtitle"
KIND_BLUR = "blur"
KIND_LOGO = "logo"


class _DraggableMixin:
    """Shared drag/select notification logic for canvas overlay items."""

    def _notify_moved(self):
        sc = self.scene()
        if sc is not None:
            sc.item_moved.emit(self.data(0), self.data(1), self.pos().x(), self.pos().y())

    def _notify_selected(self):
        sc = self.scene()
        if sc is not None:
            sc.item_selected.emit(self.data(0), self.data(1))

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._notify_moved()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged and value:
            self._notify_selected()
        return super().itemChange(change, value)


class BlurRegionItem(_DraggableMixin, QGraphicsRectItem):
    """Draggable rectangle representing a blur region (top-left anchored)."""

    def __init__(self, item_id: str, w: float, h: float, parent=None):
        super().__init__(QRectF(0, 0, w, h), parent)
        self.setData(0, KIND_BLUR)
        self.setData(1, item_id)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setPen(QPen(QColor(255, 165, 0, 220), 2, Qt.PenStyle.DashLine))
        self.setBrush(QBrush(QColor(255, 165, 0, 60)))


class LogoItem(_DraggableMixin, QGraphicsPixmapItem):
    """Draggable pixmap representing a logo/watermark overlay (top-left anchored)."""

    def __init__(self, item_id: str, pixmap: QPixmap, parent=None):
        super().__init__(pixmap, parent)
        self.setData(0, KIND_LOGO)
        self.setData(1, item_id)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )


class SubtitleItem(_DraggableMixin, QGraphicsTextItem):
    """Draggable text item representing a custom subtitle/caption (center anchored).

    The background is a *child* QGraphicsPathItem. In Qt, a child item is always
    painted on top of its parent regardless of zValue unless the
    ItemStacksBehindParent flag is explicitly set - a plain negative zValue alone
    (the old implementation) does NOT push it behind the parent, which is why the
    subtitle background could cover the text. Setting that flag here is the fix.
    """

    def __init__(self, item_id: str, text: str, parent=None):
        super().__init__(text, parent)
        self.setData(0, KIND_SUBTITLE)
        self.setData(1, item_id)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.bg_rect = QGraphicsPathItem(self)
        self.bg_rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, True)
        self.bg_rect.setZValue(-1)
        self.bg_rect.setPen(QPen(Qt.PenStyle.NoPen))
        self._pad_x = 0.0
        self._pad_y = 0.0

    def apply_style(self, font_size: int, font_color_hex: str, bg_enabled: bool,
                     bg_color_hex: str, bg_opacity: float,
                     pad_x: float = 12.0, pad_y: float = 8.0, corner_radius: float = 6.0):
        self.setFont(QFont("Arial", max(6, int(font_size)), QFont.Weight.Bold))
        self.setDefaultTextColor(QColor(font_color_hex))

        # Background is always (re)computed from the CURRENT text's real bounding
        # box + padding, never a fixed-size rectangle, so it stays correct whenever
        # font size / text content changes (req: background must track the text).
        self._pad_x = max(0.0, float(pad_x))
        self._pad_y = max(0.0, float(pad_y))
        text_rect = self.boundingRect()

        if bg_enabled:
            padded = text_rect.adjusted(-self._pad_x, -self._pad_y, self._pad_x, self._pad_y)
            path = QPainterPath()
            radius = max(0.0, float(corner_radius))
            path.addRoundedRect(padded, radius, radius)
            color = QColor(bg_color_hex)
            color.setAlphaF(max(0.0, min(1.0, bg_opacity)))
            self.bg_rect.setBrush(QBrush(color))
            self.bg_rect.setPath(path)
            self.bg_rect.show()
        else:
            self.bg_rect.hide()

    def full_bounding_rect(self) -> QRectF:
        """Bounding rect of text + background padding, used to center the whole
        subtitle item (not just the bare text) at x_pct/y_pct."""
        rect = self.boundingRect()
        return rect.adjusted(-self._pad_x, -self._pad_y, self._pad_x, self._pad_y)


class EditorCanvasScene(QGraphicsScene):
    """Scene emitting item move / select events keyed by (kind, item_id)."""

    item_moved = Signal(str, str, float, float)
    item_selected = Signal(str, str)


class EditorCanvasView(QGraphicsView):
    """Interactive View displaying the video frame with all overlay items drawn on top."""

    # Emitted after a drag finishes syncing percentages back into overlay_config.
    overlay_changed = Signal()
    item_selected = Signal(str, str)  # kind, item_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = EditorCanvasScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        self.scene.item_moved.connect(self._on_item_moved)
        self.scene.item_selected.connect(self.item_selected.emit)

        self.overlay_config: Optional[EditorOverlayConfig] = None
        self.frame_width = 1280
        self.frame_height = 720

    def load_frame(self, image_path_or_pixmap, overlay_config: EditorOverlayConfig):
        """Redraw the current frame image plus every enabled overlay item."""
        self.scene.clear()
        self.overlay_config = overlay_config

        if isinstance(image_path_or_pixmap, QPixmap):
            pixmap = image_path_or_pixmap
        elif isinstance(image_path_or_pixmap, str) or hasattr(image_path_or_pixmap, "exists"):
            pixmap = QPixmap(str(image_path_or_pixmap))
        else:
            # No video associated with the project yet - legitimate empty state.
            pixmap = QPixmap(1280, 720)
            pixmap.fill(QColor(30, 30, 35))

        self.frame_width = max(1, pixmap.width())
        self.frame_height = max(1, pixmap.height())

        self.scene.setSceneRect(0, 0, self.frame_width, self.frame_height)
        self.scene.addPixmap(pixmap)

        if overlay_config is None:
            self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            return

        # Blur regions
        for b in overlay_config.blur_regions:
            if not b.get("enabled", True):
                continue
            bw = (float(b.get("width_pct", 80.0)) / 100.0) * self.frame_width
            bh = (float(b.get("height_pct", 12.0)) / 100.0) * self.frame_height
            bx = (float(b.get("x_pct", 10.0)) / 100.0) * self.frame_width
            by = (float(b.get("y_pct", 80.0)) / 100.0) * self.frame_height
            item = BlurRegionItem(b["id"], bw, bh)
            self.scene.addItem(item)
            item.setPos(bx, by)

        # Logos
        for l in overlay_config.logos:
            if not l.get("enabled", True) or not l.get("image_path"):
                continue
            lw = max(1, int((float(l.get("width_pct", 15.0)) / 100.0) * self.frame_width))
            lh = max(1, int((float(l.get("height_pct", 10.0)) / 100.0) * self.frame_height))
            pix = QPixmap(str(l["image_path"]))
            if pix.isNull():
                continue
            pix = pix.scaled(lw, lh, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            item = LogoItem(l["id"], pix)
            item.setOpacity(float(l.get("opacity", 0.8)))
            self.scene.addItem(item)
            lx = (float(l.get("x_pct", 5.0)) / 100.0) * self.frame_width
            ly = (float(l.get("y_pct", 5.0)) / 100.0) * self.frame_height
            item.setPos(lx, ly)

        # Custom subtitles
        for s in overlay_config.subtitles:
            if not s.get("enabled", True):
                continue
            item = SubtitleItem(s["id"], s.get("text", ""))
            item.apply_style(
                s.get("font_size", 24), s.get("font_color", "#FFFFFF"),
                s.get("bg_enabled", True), s.get("bg_color", "#000000"), s.get("bg_opacity", 0.5),
                s.get("bg_padding_x", 12.0), s.get("bg_padding_y", 8.0), s.get("bg_corner_radius", 6.0)
            )
            self.scene.addItem(item)
            rect = item.full_bounding_rect()
            cx = (float(s.get("x_pct", 50.0)) / 100.0) * self.frame_width
            cy = (float(s.get("y_pct", 85.0)) / 100.0) * self.frame_height
            item.setPos(cx - rect.width() / 2.0 - rect.left(), cy - rect.height() / 2.0 - rect.top())

        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene:
            self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _on_item_moved(self, kind: str, item_id: str, x: float, y: float):
        """Convert a dragged item's pixel position back into % coords on the config."""
        if not self.overlay_config or self.frame_width <= 0 or self.frame_height <= 0:
            return

        if kind == KIND_BLUR:
            item = self.overlay_config.get_blur(item_id)
            if item:
                item["x_pct"] = max(0.0, min(100.0, (x / self.frame_width) * 100.0))
                item["y_pct"] = max(0.0, min(100.0, (y / self.frame_height) * 100.0))
        elif kind == KIND_LOGO:
            item = self.overlay_config.get_logo(item_id)
            if item:
                item["x_pct"] = max(0.0, min(100.0, (x / self.frame_width) * 100.0))
                item["y_pct"] = max(0.0, min(100.0, (y / self.frame_height) * 100.0))
        elif kind == KIND_SUBTITLE:
            item = self.overlay_config.get_subtitle(item_id)
            if item:
                # Find the on-canvas item to know its current size (text + background
                # padding) for center calc.
                for gi in self.scene.items():
                    if gi.data(0) == KIND_SUBTITLE and gi.data(1) == item_id:
                        rect = gi.full_bounding_rect() if hasattr(gi, "full_bounding_rect") else gi.boundingRect()
                        cx = x + rect.left() + rect.width() / 2.0
                        cy = y + rect.top() + rect.height() / 2.0
                        item["x_pct"] = max(0.0, min(100.0, (cx / self.frame_width) * 100.0))
                        item["y_pct"] = max(0.0, min(100.0, (cy / self.frame_height) * 100.0))
                        break

        self.overlay_changed.emit()
