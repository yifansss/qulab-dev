"""PySide6/PyQt6 operator console entry point."""

from __future__ import annotations

import sys
import argparse

from .qt_compat import QT_AVAILABLE, QtWidgets, missing_qt_message


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Qulab Qt operator console")
    parser.add_argument("--config", help="experiment YAML to load on startup")
    args = parser.parse_args(argv)
    if not QT_AVAILABLE:
        print(missing_qt_message(), file=sys.stderr)
        raise SystemExit(1)

    from .pyqt_views import PyQtOperatorWindow

    assert QtWidgets is not None
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = PyQtOperatorWindow(config_path=args.config)
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
