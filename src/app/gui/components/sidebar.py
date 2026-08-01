"""
app/gui/components/sidebar.py
==============================
App Sidebar Navigation Component.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QButtonGroup


class AppSidebar(QFrame):
    """Navigation Sidebar with 5 main views."""

    page_changed = Signal(int)  # 0: Dashboard, 1: Projects, 2: Pipeline, 3: Editor, 4: Prompt dịch, 5: Settings

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 16)
        layout.setSpacing(6)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        nav_items = [
            ("📊 Dashboard", 0),
            ("📁 Projects", 1),
            ("⚙️ Pipeline Engine", 2),
            ("🎬 Visual Editor", 3),
            ("📝 Prompt dịch", 4),
            ("🛠️ Settings", 5)
        ]

        for text, idx in nav_items:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setProperty("class", "NavButton")
            if idx == 0:
                btn.setChecked(True)
            self.btn_group.addButton(btn, idx)
            layout.addWidget(btn)

        layout.addStretch()

        self.btn_group.idClicked.connect(lambda idx: self.page_changed.emit(idx))
