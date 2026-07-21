from __future__ import annotations


def test_operator_app_import_does_not_start_window() -> None:
    from qulab.gui.operator_app import main

    assert main.__name__ == "main"
