from __future__ import annotations


def test_operator_and_viewer_panel_import_without_launching_qt() -> None:
    from qulab.gui.pyqt_views import PyQtOperatorWindow
    from qulab.viewer.pyqt_viewer_app import create_data_viewer_panel, main

    assert PyQtOperatorWindow.__name__ == "PyQtOperatorWindow"
    assert create_data_viewer_panel.__name__ == "create_data_viewer_panel"
    assert main.__name__ == "main"
