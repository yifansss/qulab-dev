from __future__ import annotations

from pathlib import Path

from qulab.core import DataPoint
from qulab.gui.controller import OperatorController
from qulab.gui.workflow_model import update_node


ROOT = Path(__file__).resolve().parents[2]


def test_controller_save_reload_and_run_two_mw_roundtrip(tmp_path: Path) -> None:
    controller = OperatorController(run_root=tmp_path / "runs")
    controller.load_config(ROOT / "configs" / "experiments" / "dry_run_two_mw_scan.yaml")
    controller.update_workflow_node(
        ("procedure", 0, "scan", "body", 1),
        {"scan": {"values": {"start": 2.86e9, "stop": 2.88e9, "points": 2}}},
    )
    saved_path = controller.save_config(tmp_path / "two_mw_edited.yaml")

    reloaded = OperatorController(run_root=tmp_path / "runs2")
    reloaded.load_config(saved_path)
    preflight = reloaded.prepare()
    assert preflight.ok

    events = []
    result = reloaded.start_dry_run(event_callback=events.append)

    assert result.status == "completed"
    assert Path(result.run_path).exists()
    assert len([event for event in events if isinstance(event, DataPoint)]) == 4
