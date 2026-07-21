from pathlib import Path

from qulab.config import load_yaml_config, parse_experiment_config


ROOT = Path(__file__).resolve().parents[2]


def test_ni_sync_hardware_templates_parse_and_preflight() -> None:
    for name in [
        "hardware_asg_master_counter.template.yaml",
        "hardware_ni_master_ao_ai.template.yaml",
        "hardware_mixed_ao_asg_counter.template.yaml",
    ]:
        config = load_yaml_config(ROOT / "configs" / "experiments" / name)
        parsed = parse_experiment_config(config)

        assert parsed.validation.ok, (name, parsed.validation.issues)
        assert parsed.sync_plan is not None
        assert parsed.context.resources["daq"].snapshot()["settings"]["driver"] == "sync"
