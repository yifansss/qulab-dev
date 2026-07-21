"""Shared Qt theme for Qulab operator tools."""

from __future__ import annotations


def classic_qt_stylesheet() -> str:
    """Classic white/gray Qt theme inspired by the standalone sequence editor."""

    return """
    QMainWindow, QWidget {
        background-color: #f0f0f0;
        color: #000000;
        font-family: "Segoe UI", Arial, sans-serif;
        font-size: 12px;
    }
    QGroupBox {
        border: 1px solid #a0a0a0;
        border-radius: 4px;
        margin-top: 14px;
        padding: 6px 4px 4px 4px;
        background-color: #f5f5f5;
        color: #000000;
        font-weight: bold;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
        color: #000000;
    }
    QLabel {
        color: #000000;
        background: transparent;
    }
    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QTreeWidget, QTableWidget, QListWidget, QScrollArea {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #808080;
        border-radius: 2px;
        selection-background-color: #c8e0f8;
        selection-color: #000000;
    }
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
    QTreeWidget:focus, QTableWidget:focus {
        border: 1px solid #0078d7;
    }
    QPushButton, QToolButton {
        background-color: #e1e1e1;
        color: #000000;
        border: 1px solid #a0a0a0;
        border-radius: 3px;
        padding: 5px 14px;
        min-height: 24px;
        font-weight: 500;
    }
    QPushButton:hover, QToolButton:hover {
        background-color: #c8e0f8;
        border-color: #0078d7;
    }
    QPushButton:pressed, QToolButton:pressed {
        background-color: #0078d7;
        color: #ffffff;
    }
    QPushButton:disabled, QToolButton:disabled {
        background-color: #eeeeee;
        color: #808080;
        border-color: #c0c0c0;
    }
    QPushButton#primaryButton, QToolButton#primaryButton {
        background-color: #0078d7;
        color: #ffffff;
        border: 1px solid #005fa3;
        font-weight: bold;
    }
    QPushButton#primaryButton:hover, QToolButton#primaryButton:hover {
        background-color: #005fa3;
    }
    QPushButton#accentButton, QToolButton#accentButton {
        color: #0078d7;
        font-weight: bold;
    }
    QPushButton#dangerButton, QToolButton#dangerButton {
        color: #ff0000;
        font-weight: bold;
    }
    QPushButton#dangerButton:hover, QToolButton#dangerButton:hover {
        background-color: #ffe6e6;
        border-color: #cc0000;
    }
    QHeaderView::section {
        background-color: #e5e5e5;
        border: 0;
        border-right: 1px solid #b8b8b8;
        border-bottom: 1px solid #b8b8b8;
        padding: 4px;
        color: #000000;
    }
    QToolBar {
        background-color: #f0f0f0;
        border-bottom: 1px solid #a0a0a0;
        spacing: 6px;
        padding: 4px;
    }
    QTabWidget::pane {
        border: 1px solid #a0a0a0;
        background-color: #f5f5f5;
    }
    QTabBar::tab {
        background-color: #e1e1e1;
        border: 1px solid #a0a0a0;
        padding: 5px 12px;
        margin-right: 1px;
    }
    QTabBar::tab:selected {
        background-color: #ffffff;
        border-bottom-color: #ffffff;
    }
    QSplitter::handle {
        background-color: #c0c0c0;
    }
    """
