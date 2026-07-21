from __future__ import annotations


def test_pyqt_operator_app_import_does_not_launch_window() -> None:
    from qulab.gui.pyqt_operator_app import main

    assert main.__name__ == "main"


def test_qt_compat_fallback_is_import_safe() -> None:
    from qulab.gui.qt_compat import QT_API, QT_AVAILABLE, missing_qt_message

    assert isinstance(QT_AVAILABLE, bool)
    assert QT_API in {None, "PySide6", "PyQt6"}
    assert "PySide6" in missing_qt_message()


def test_shared_qt_theme_imports() -> None:
    from qulab.gui.theme import classic_qt_stylesheet

    stylesheet = classic_qt_stylesheet()
    assert "QGroupBox" in stylesheet
    assert "QTabWidget" in stylesheet
    assert "QCheckBox::indicator:checked" not in stylesheet


def test_experiment_config_paths_are_discovered_from_folder() -> None:
    from qulab.gui.pyqt_views import _experiment_config_paths

    stems = {path.stem for path in _experiment_config_paths()}
    assert "dry_run_rabi" in stems
    assert "hardware_odmr.template" in stems
