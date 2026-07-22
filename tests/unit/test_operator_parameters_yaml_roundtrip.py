from pathlib import Path

from qulab.config import load_experiment_config, load_yaml_config, parse_experiment_config
from qulab.core import DataPoint, Event
from qulab.gui.controller import OperatorController
from qulab.gui.yaml_editor import save_config_yaml


ROOT = Path(__file__).resolve().parents[2]


def test_operator_parameter_yaml_roundtrip_is_parseable(tmp_path: Path) -> None:
    controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")

    controller.apply_operator_parameter("tau_s_points", "4")
    controller.apply_operator_parameter("avg_count", "1")
    path = controller.save_config(tmp_path / "edited.yaml")

    config = load_yaml_config(path)
    parsed = parse_experiment_config(config)

    assert parsed.validation.ok
    assert "sequence_file" not in config["resources"]["asg"]


def test_operator_parameter_scan_and_average_changes_dry_run_points(tmp_path: Path) -> None:
    controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    controller.apply_operator_parameter("tau_s_points", "3")
    controller.apply_operator_parameter("avg_count", "1")
    events: list[Event] = []

    controller.start_dry_run(event_callback=events.append)

    assert sum(isinstance(event, DataPoint) for event in events) == 3


def test_explicit_operator_parameter_source_for_sequence_file(tmp_path: Path) -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    config["operator_parameters"] = [
        {
            "name": "sequence_file",
            "label": "ASG sequence",
            "source": "resources.asg.sequence_file",
            "widget": "file_picker",
        }
    ]
    path = save_config_yaml(config, tmp_path / "explicit.yaml")
    controller = OperatorController(tmp_path / "runs")
    controller.load_config(path)

    controller.apply_operator_parameter("sequence_file", "configs/sequences/odmr.seq")

    assert controller.get_sequence_file("asg") == "configs/sequences/odmr.seq"
