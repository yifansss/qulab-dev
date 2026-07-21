from pathlib import Path

from qulab.config import load_yaml_config, parse_experiment_config


ROOT = Path(__file__).resolve().parents[2]


def test_real_nv_setup_template_parses_and_preflights() -> None:
    config = load_yaml_config(ROOT / "configs" / "setups" / "real_nv_setup.template.yaml")
    parsed = parse_experiment_config(config)

    assert parsed.validation.ok
    assert {"mw_drive", "asg", "daq", "awg"} <= set(parsed.context.resources)
    assert parsed.context.resources["mw_drive"].connected is False


def test_hardware_odmr_template_parses_and_preflights_without_outputs() -> None:
    config = load_yaml_config(ROOT / "configs" / "experiments" / "hardware_odmr.template.yaml")
    parsed = parse_experiment_config(config)

    assert parsed.validation.ok
    assert parsed.sync_plan is not None
    assert parsed.sync_plan.master == "asg"
