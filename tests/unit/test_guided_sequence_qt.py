from pathlib import Path
import hashlib
import shutil

import pytest

from qulab.gui.qt_compat import QT_AVAILABLE, QtCore, QtGui, QtWidgets

pytestmark = pytest.mark.skipif(not QT_AVAILABLE, reason="PySide6/PyQt6 is not installed")
ROOT = Path(__file__).resolve().parents[2]


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_sequence_workspace_has_bundle_browser_and_six_step_generic_sweep(tmp_path: Path) -> None:
    from qulab.gui.controller import OperatorController
    from qulab.gui.sequence_authoring_view import create_guided_sequence_widget

    _app(); controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    controller.config["resources"]["asg_backup"] = dict(controller.config["resources"]["asg"])
    widget = create_guided_sequence_widget(QtWidgets, QtCore, QtGui, controller)
    assert [widget.tabText(index) for index in range(widget.count())] == ["Bundle Browser", "Generic Sweep"]
    assert widget.steps.count() == 6
    assert widget.pages.count() == 9
    names = {widget.fixed_parameter_table.item(row, 0).text() for row in range(widget.fixed_parameter_table.rowCount())}
    names |= {widget.sweep_parameter_table.item(row, 0).text() for row in range(widget.sweep_parameter_table.rowCount())}
    assert {item.name for item in controller.sequence_authoring().parameter_fields("generic_rabi")} == names
    assert "tau_s" in names
    widget.resource_combo.setCurrentText("asg_backup"); widget.generic_sweep._apply_source()
    assert controller.current_config["sequence_plans"]["generic_rabi"]["resource"] == "asg_backup"


def test_guided_parameter_interaction_updates_shared_config_and_preview(tmp_path: Path) -> None:
    from qulab.gui.controller import OperatorController
    from qulab.gui.sequence_authoring_view import create_guided_sequence_widget

    _app(); controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    widget = create_guided_sequence_widget(QtWidgets, QtCore, QtGui, controller)
    row = next(row for row in range(widget.sweep_parameter_table.rowCount())
               if widget.sweep_parameter_table.item(row, 0).text() == "tau_s")
    widget.sweep_parameter_table.cellWidget(row, 1).setCurrentText("linspace")
    widget.sweep_parameter_table.item(row, 3).setText("2e-8")
    widget.sweep_parameter_table.item(row, 4).setText("6e-8")
    widget.sweep_parameter_table.item(row, 5).setText("3")
    widget._apply_parameters()
    raw = controller.current_config["sequence_plans"]["generic_rabi"]["parameters"]["tau_s"]
    assert raw["mode"] == "linspace" and raw["points"] == 3
    widget._refresh_preview()
    assert widget.timeline.preview is not None and widget.timeline.preview.pulses


def test_generic_operations_come_from_model_and_macro_updates_workflow(tmp_path: Path) -> None:
    from qulab.gui.controller import OperatorController
    from qulab.gui.sequence_authoring_view import create_guided_sequence_widget

    _app(); controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    widget = create_guided_sequence_widget(QtWidgets, QtCore, QtGui, controller)
    catalog = controller.sequence_authoring().generic_operation_catalog()
    assert [widget.property_combo.itemText(i) for i in range(widget.property_combo.count())] == list(catalog["Basic Timing"])
    assert widget.pulse_table.rowCount() > 0
    before = sum(1 for item in controller.current_config["procedure"] if "sequence_sweep" in item)
    widget._insert_macro()
    after = sum(1 for item in controller.current_config["procedure"] if "sequence_sweep" in item)
    assert after == before  # existing macro is updated/reused, never duplicated


def test_generic_sweep_exposes_no_curated_or_standalone_mode(tmp_path: Path, monkeypatch) -> None:
    from qulab.gui.controller import OperatorController
    from qulab.gui.sequence_authoring_view import create_guided_sequence_widget

    _app(); controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    widget = create_guided_sequence_widget(QtWidgets, QtCore, QtGui, controller)
    assert [widget.mode_combo.itemText(index) for index in range(widget.mode_combo.count())] == ["generic"]
    assert not widget.editor_button.isVisible()


def test_generic_pulse_binding_and_issue_navigation(tmp_path: Path) -> None:
    from qulab.gui.controller import OperatorController
    from qulab.gui.sequence_authoring_view import create_guided_sequence_widget

    _app(); controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    widget = create_guided_sequence_widget(QtWidgets, QtCore, QtGui, controller)
    widget.pulse_table.selectRow(0); widget.target_alias.setText("mw_pulse"); widget.target_parameter.setText("tau_s")
    widget.property_combo.setCurrentText("duration"); widget.propagation_combo.setCurrentText("none"); widget._apply_target()
    target = controller.current_config["sequence_plans"]["generic_rabi"]["targets"]["mw_pulse"]
    assert target["fingerprint"] and target["channel"] == "Channel 1"
    config = controller.config
    config["sequence_plans"]["generic_rabi"]["options"]["trigger_channels"] = ["Channel 5"]
    widget.refresh()
    row = next(row for row in range(widget.issues.rowCount())
               if widget.issues.item(row, 1).text() == "sequence_trigger_channel_mismatch")
    widget._issue_clicked(row, 1)
    assert widget.steps.currentRow() == 2


def test_existing_operator_window_uses_only_guided_sequence_tab(tmp_path: Path) -> None:
    from qulab.gui.controller import OperatorController
    from qulab.gui.pyqt_views import PyQtOperatorWindow

    _app(); window = PyQtOperatorWindow(OperatorController(tmp_path / "runs"), ROOT / "configs/experiments/dry_run_rabi_sequence_family.yaml")
    labels = [window.submode_tabs.tabText(index) for index in range(window.submode_tabs.count())]
    assert sum("Sequence Sweep" in label for label in labels) == 1
    assert window.submode_tabs.widget(labels.index(next(label for label in labels if "Sequence Sweep" in label))) is window.guided_sequence_widget
    assert window.guided_sequence_widget.count() == 2
    window.close()


def test_sampling_order_compare_and_timeline_selection_are_wired(tmp_path: Path) -> None:
    from qulab.gui.controller import OperatorController
    from qulab.gui.sequence_authoring_view import create_guided_sequence_widget

    _app(); controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    widget = create_guided_sequence_widget(QtWidgets, QtCore, QtGui, controller)
    assert widget.sampling_order.count() == 2
    original = [widget.sampling_order.item(i).text() for i in range(2)]
    widget.sampling_order.setCurrentRow(1); widget._move_sampling(-1)
    assert controller.current_config["sequence_plans"]["generic_rabi"]["sampling"]["order"] == original[::-1]
    widget.preview_choice.setCurrentText("Difference first/last"); widget._refresh_preview()
    assert widget.timeline.preview is not None and widget.timeline.comparison is not None and widget.timeline.difference
    channel = widget.pulse_table.item(0, 0).text(); pulse = int(widget.pulse_table.item(0, 1).text())
    widget.timeline.pulseSelected.emit(channel, pulse)
    assert widget.pulse_table.currentRow() == 0


def test_editor_saved_artifact_updates_widget_plan_and_stales_prepare(tmp_path: Path) -> None:
    from qulab.gui.controller import OperatorController
    from qulab.gui.sequence_authoring_view import create_guided_sequence_widget
    from qulab.gui.sequence_bridge import SequenceEditorProtocolResult

    _app(); controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    controller.change_sequence_mode("generic_rabi", "standalone",
                                    template="configs/sequences/examples/generic_rabi_base.json")
    controller.prepare_sequence_plan("generic_rabi")
    artifact = tmp_path / "editor_saved.json"
    shutil.copyfile(ROOT / "configs/sequences/examples/generic_rabi_base.json", artifact)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    widget = create_guided_sequence_widget(QtWidgets, QtCore, QtGui, controller)
    result = SequenceEditorProtocolResult(True, 1, "test", ("save", "validate"), str(artifact), False,
                                          (), {"channels": 2}, {"path": str(artifact), "sha256": digest})
    widget._editor_done(result)
    assert controller.current_config["sequence_plans"]["generic_rabi"]["template"] == str(artifact)
    assert controller.get_guided_sequence_state("generic_rabi").prepared_state == "stale"
