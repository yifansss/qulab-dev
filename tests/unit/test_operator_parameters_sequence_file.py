from pathlib import Path

from qulab.config import load_experiment_config
from qulab.gui.operator_parameters import apply_operator_parameter, discover_operator_parameters


ROOT = Path(__file__).resolve().parents[2]


def test_operator_parameters_can_create_asg_sequence_file_field() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    config["resources"]["asg"].pop("sequence_file", None)

    spec = next(item for item in discover_operator_parameters(None, config) if item.name == "asg_sequence_file")
    apply_operator_parameter(None, config, spec.name, "configs/sequences/rabi.seq")

    assert spec.source == "resources.asg.sequence_file"
    assert config["resources"]["asg"]["sequence_file"] == "configs/sequences/rabi.seq"
