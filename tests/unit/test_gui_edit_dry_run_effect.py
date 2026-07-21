from __future__ import annotations

from pathlib import Path

from qulab.core import DataPoint
from qulab.gui.controller import OperatorController
from qulab.gui.workflow_model import update_node


ROOT = Path(__file__).resolve().parents[2]


def test_edit_scan_points_changes_dry_run_data_points(tmp_path: Path) -> None:
    controller = OperatorController(run_root=tmp_path)
    controller.load_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    controller.config = update_node(
        controller.current_config,
        ("procedure", 0),
        {"scan": {"values": {"start": 2e-8, "stop": 4e-8, "points": 3}}},
    )

    events = []
    controller.prepare()
    controller.start_dry_run(event_callback=events.append)

    data_points = [event for event in events if isinstance(event, DataPoint)]
    assert len(data_points) == 6


def test_edit_average_count_changes_dry_run_data_points(tmp_path: Path) -> None:
    controller = OperatorController(run_root=tmp_path)
    controller.load_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    controller.config = update_node(
        controller.current_config,
        ("procedure", 0, "scan", "body", 0, "measurement", "body", 1),
        {"average": {"count": 1}},
    )

    events = []
    controller.prepare()
    controller.start_dry_run(event_callback=events.append)

    data_points = [event for event in events if isinstance(event, DataPoint)]
    assert len(data_points) == 5
