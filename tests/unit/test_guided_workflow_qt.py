from pathlib import Path

import pytest

from qulab.gui.qt_compat import QT_AVAILABLE, QtWidgets


pytestmark = pytest.mark.skipif(not QT_AVAILABLE, reason="PySide6/PyQt6 is not installed")
ROOT = Path(__file__).resolve().parents[2]


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _widget(tmp_path: Path):
    from qulab.gui.controller import OperatorController
    from qulab.gui.workflow_composer_view import create_guided_workflow_widget

    _app(); controller = OperatorController(tmp_path / "runs")
    assert controller.load_config(ROOT / "configs/experiments/dry_run_rabi.yaml").activated
    return controller, create_guided_workflow_widget(QtWidgets, controller)


def test_guided_workflow_selects_and_edits_existing_scan(tmp_path: Path) -> None:
    controller, widget = _widget(tmp_path)
    path = ("procedure", 0)
    assert widget._select_outline_path(path)
    assert widget.selected_path == path
    assert widget._edit_fields["kind"] == "scan"
    widget._edit_fields["name"].setText("guided_axis")
    widget._apply_selected_edit()
    assert controller.current_config["procedure"][0]["scan"]["name"] == "guided_axis"


def test_guided_workflow_duplicate_move_delete_and_undo(tmp_path: Path, monkeypatch) -> None:
    controller, widget = _widget(tmp_path)
    widget.selected_path = ("procedure", 0)
    widget._duplicate_selected()
    assert len(controller.current_config["procedure"]) == 2
    widget._move_sibling(-1)
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *args: QtWidgets.QMessageBox.StandardButton.Yes)
    widget._delete_selected()
    assert len(controller.current_config["procedure"]) == 1
    widget._undo()
    assert len(controller.current_config["procedure"]) == 2


def test_guided_workflow_diagnostic_focus_and_management_controls_exist(tmp_path: Path) -> None:
    _controller, widget = _widget(tmp_path)
    assert widget.undo_button is not None and widget.redo_button is not None
    assert widget.move_parent.count() >= 3
    assert widget.apply_edit_button is not None
