from pathlib import Path

from qulab.config import load_experiment_config
from qulab.gui.operator_parameters import apply_operator_parameter, discover_operator_parameters


ROOT = Path(__file__).resolve().parents[2]


def test_operator_parameters_do_not_invent_resource_global_sequence_file() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")

    specs = discover_operator_parameters(None, config)

    assert not any(spec.source == "resources.asg.sequence_file" for spec in specs)
    assert "sequence_file" not in config["resources"]["asg"]


def test_explicit_legacy_resource_sequence_parameter_remains_supported() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    config["resources"]["asg"]["sequence_file"] = "configs/sequences/legacy.json"
    config["operator_parameters"] = [
        {"name": "legacy_sequence", "source": "resources.asg.sequence_file", "widget": "file_picker"}
    ]

    apply_operator_parameter(None, config, "legacy_sequence", "configs/sequences/updated.json")

    assert config["resources"]["asg"]["sequence_file"] == "configs/sequences/updated.json"
