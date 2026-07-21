"""Optional Qt binding compatibility for the PyQt/PySide operator console."""

from __future__ import annotations

import os

QT_AVAILABLE = False
QT_API: str | None = None
QtCore = None
QtGui = None
QtWidgets = None


def _preferred_apis() -> tuple[str, ...]:
    requested = os.environ.get("QULAB_QT_API", "").strip()
    if requested:
        return (requested,)
    return ("PySide6", "PyQt6")


for _api in _preferred_apis():  # pragma: no cover - depends on optional local Qt install
    try:
        if _api == "PySide6":
            from PySide6 import QtCore as _QtCore, QtGui as _QtGui, QtWidgets as _QtWidgets
        elif _api == "PyQt6":
            from PyQt6 import QtCore as _QtCore, QtGui as _QtGui, QtWidgets as _QtWidgets
        else:
            continue
    except ImportError:
        continue
    QtCore = _QtCore
    QtGui = _QtGui
    QtWidgets = _QtWidgets
    QT_AVAILABLE = True
    QT_API = _api
    break


def missing_qt_message() -> str:
    return (
        "Qt binding not installed. Install PySide6 or PyQt6 to launch "
        "the PyQt Operator Console. The Tkinter MVP remains available via "
        "`python -m qulab.gui.operator_app`. Set QULAB_QT_API=PySide6 or "
        "QULAB_QT_API=PyQt6 to force one Qt binding."
    )
