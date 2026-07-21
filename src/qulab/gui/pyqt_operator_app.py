"""PySide6/PyQt6 operator console entry point."""

from __future__ import annotations

import sys

from .qt_compat import QT_AVAILABLE, QtWidgets, missing_qt_message


def main() -> None:
    if not QT_AVAILABLE:
        print(missing_qt_message(), file=sys.stderr)
        raise SystemExit(1)

    from .pyqt_views import PyQtOperatorWindow

    assert QtWidgets is not None
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = PyQtOperatorWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
