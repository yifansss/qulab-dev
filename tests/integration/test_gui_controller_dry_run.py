from __future__ import annotations

from pathlib import Path

from qulab.core import DataPoint, RunCompleted, RunStarted
from qulab.gui.controller import OperatorController


ROOT = Path(__file__).resolve().parents[2]


def test_gui_controller_runs_dry_run_and_writes_run_store(tmp_path: Path) -> None:
    controller = OperatorController(run_root=tmp_path)
    controller.load_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")

    edits = {edit.label: edit for edit in controller.get_parameter_edit_model()}
    controller.update_parameter(edits["tau_s points"].id, "3")
    controller.update_parameter(edits["avg count"].id, "1")

    preflight = controller.prepare()
    assert preflight.ok
    assert {resource.name for resource in preflight.resources} == {"mw", "asg", "daq"}

    events = []
    result = controller.start_dry_run(event_callback=events.append)

    assert result.status == "completed"
    run_path = Path(result.run_path)
    assert run_path.exists()
    assert (run_path / "events.jsonl").exists()
    assert (run_path / "data.jsonl").exists()
    assert (run_path / "dataset_manifest.json").exists()
    assert (run_path / "tables" / "summaries" / "counts_mean.csv").exists()
    assert (run_path / "tables" / "traces" / "photon_bins.csv").exists()
    assert set(controller.list_run_data_keys()) >= {"counts_mean", "photon_bins"}
    assert any(isinstance(event, RunStarted) for event in events)
    assert any(isinstance(event, DataPoint) for event in events)
    assert any(isinstance(event, RunCompleted) for event in events)
