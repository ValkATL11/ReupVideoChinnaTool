"""
app/gui/components/key_manager_dialog.py
========================================
API Key Pool Management Dialog (Groq & Gemini).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QPushButton, QLineEdit, QLabel, QMessageBox, QHeaderView
)

from app.core.key_manager import key_manager_instance, mask_key
from app.gui.styles.theme import DARK_THEME_QSS


class KeyManagerDialog(QDialog):
    """Dialog for managing Groq & Gemini API key pools."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API Key Pool Manager - ReupTool V3")
        self.resize(650, 450)
        self.setStyleSheet(DARK_THEME_QSS)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()

        # Groq Tab
        self.groq_tab = self.create_provider_tab("groq", key_manager_instance.groq)
        self.tabs.addTab(self.groq_tab, "Groq API Keys Pool")

        # Gemini Tab
        self.gemini_tab = self.create_provider_tab("gemini", key_manager_instance.gemini)
        self.tabs.addTab(self.gemini_tab, "Gemini API Keys Pool")

        layout.addWidget(self.tabs)

        # Bottom Close Button
        btn_close = QPushButton("Done")
        btn_close.setProperty("class", "PrimaryButton")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def create_provider_tab(self, provider_name: str, pool) -> QWidget:
        tab = QWidget()
        vbox = QVBoxLayout(tab)

        # Input Bar
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Add API Key:"))
        key_input = QLineEdit()
        key_input.setPlaceholderText(f"Paste your {provider_name.capitalize()} API key here...")
        hbox.addWidget(key_input)

        btn_add = QPushButton("Add Key")
        btn_add.setProperty("class", "PrimaryButton")
        hbox.addWidget(btn_add)

        vbox.addLayout(hbox)

        # Keys Table
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["ID", "API Key (Masked)", "Status", "Actions"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        vbox.addWidget(table)

        def refresh_table():
            pool.reload()
            table.setRowCount(0)
            for idx, k in enumerate(pool.keys):
                row = table.rowCount()
                table.insertRow(row)

                table.setItem(row, 0, QTableWidgetItem(k.get("id", str(idx+1))))
                table.setItem(row, 1, QTableWidgetItem(mask_key(k.get("key", ""))))

                status_str = "Enabled" if k.get("enabled", True) else "Disabled"
                table.setItem(row, 2, QTableWidgetItem(status_str))

                # Actions Widget
                act_widget = QWidget()
                act_box = QHBoxLayout(act_widget)
                act_box.setContentsMargins(2, 2, 2, 2)

                btn_toggle = QPushButton("Disable" if k.get("enabled", True) else "Enable")
                btn_toggle.setProperty("class", "SecondaryButton")
                key_id = k.get("id")
                btn_toggle.clicked.connect(lambda _, kid=key_id, en=k.get("enabled", True): toggle_action(kid, not en))
                act_box.addWidget(btn_toggle)

                btn_del = QPushButton("Delete")
                btn_del.setProperty("class", "SecondaryButton")
                btn_del.clicked.connect(lambda _, kid=key_id: delete_action(kid))
                act_box.addWidget(btn_del)

                table.setCellWidget(row, 3, act_widget)

        def add_action():
            val = key_input.text().strip()
            if val:
                if pool.add_key(val):
                    key_input.clear()
                    refresh_table()
                else:
                    QMessageBox.warning(self, "Warning", "Failed to add API key (duplicate or empty).")

        def toggle_action(kid, enable_flag):
            pool.toggle_key(kid, enable_flag)
            refresh_table()

        def delete_action(kid):
            pool.remove_key(kid)
            refresh_table()

        btn_add.clicked.connect(add_action)
        refresh_table()

        return tab
