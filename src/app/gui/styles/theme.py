"""
app/gui/styles/theme.py
========================
Fluent Dark Desktop UI Theme & QSS Stylesheet Manager.
"""

DARK_THEME_QSS = """
/* Global Application Palette */
QWidget {
    background-color: #1a1a1e;
    color: #e0e0e6;
    font-family: "Segoe UI", "Roboto", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

/* Main Navigation Sidebar */
QFrame#Sidebar {
    background-color: #121215;
    border-right: 1px solid #2a2a30;
}

QPushButton.NavButton {
    background-color: transparent;
    color: #a0a0b0;
    border: none;
    border-radius: 6px;
    padding: 10px 16px;
    text-align: left;
    font-size: 14px;
    font-weight: 500;
}

QPushButton.NavButton:hover {
    background-color: #25252b;
    color: #ffffff;
}

QPushButton.NavButton:checked, QPushButton.NavButton:pressed {
    background-color: #0078d4;
    color: #ffffff;
}

/* Cards & Containers */
QFrame.CardFrame {
    background-color: #222228;
    border: 1px solid #2e2e38;
    border-radius: 8px;
    padding: 12px;
}

/* Primary Buttons */
QPushButton.PrimaryButton {
    background-color: #0078d4;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
}

QPushButton.PrimaryButton:hover {
    background-color: #1084d8;
}

QPushButton.PrimaryButton:pressed {
    background-color: #006cc1;
}

QPushButton.PrimaryButton:disabled {
    background-color: #33333d;
    color: #707080;
}

/* Secondary Buttons */
QPushButton.SecondaryButton {
    background-color: #2c2c34;
    color: #d0d0dc;
    border: 1px solid #3e3e4a;
    border-radius: 6px;
    padding: 7px 16px;
}

QPushButton.SecondaryButton:hover {
    background-color: #363642;
    color: #ffffff;
}

QPushButton.SecondaryButton:pressed {
    background-color: #24242c;
}

/* Inputs & ComboBoxes */
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
    background-color: #161619;
    border: 1px solid #33333e;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f0f0f8;
}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QSpinBox:focus {
    border: 1px solid #0078d4;
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}

/* Table / Tree Views */
QTableWidget, QTreeWidget, QListWidget {
    background-color: #18181c;
    border: 1px solid #2d2d36;
    gridline-color: #282832;
    border-radius: 6px;
}

QHeaderView::section {
    background-color: #202026;
    color: #b0b0c0;
    padding: 6px;
    border: none;
    border-right: 1px solid #2a2a34;
    border-bottom: 1px solid #2a2a34;
    font-weight: 600;
}

/* Progress Bars */
QProgressBar {
    background-color: #18181c;
    border: 1px solid #30303c;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
    font-weight: 600;
}

QProgressBar::chunk {
    background-color: #0078d4;
    border-radius: 3px;
}

/* Scrollbars */
QScrollBar:vertical {
    background-color: #141417;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #33333e;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background-color: #4a4a58;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Tab Widgets */
QTabWidget::pane {
    border: 1px solid #2c2c36;
    border-radius: 6px;
    background-color: #1c1c22;
}

QTabBar::tab {
    background-color: #141417;
    color: #9090a0;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #1c1c22;
    color: #ffffff;
    font-weight: 600;
    border-bottom: 2px solid #0078d4;
}
"""


def apply_theme(app) -> None:
    """Apply Fluent Dark theme to PySide6 QApplication."""
    app.setStyleSheet(DARK_THEME_QSS)
