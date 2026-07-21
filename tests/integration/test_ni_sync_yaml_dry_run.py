from pathlib import Path

from qulab.config import load_yaml_config, parse_experiment_config
from qulab.core import ActionStep, MeasurementStep, RunStep, ScanStep


ROOT = Path(__file__).resolve().parents[2]


def test_ni_sync_templates_describe_stateful_configure_arm_read_flows() -> None:
    config = load_yaml_config(ROOT / "configs" / "experiments" / "hardware_asg_master_counter.template.yaml")
    parsed = parse_experiment_config(config)
    measurement = parsed.procedure.body[0]

    assert isinstance(measurement, MeasurementStep)
    assert isinstance(measurement.body[0], ActionStep)
    assert measurement.body[0].action == "daq.configure_counter_external_clock"
    assert isinstance(measurement.body[1], RunStep)
    assert [step.action for step in measurement.body[1].body if isinstance(step, ActionStep)] == [
        "daq.arm",
        "asg.arm",
        "asg.start",
        "daq.read",
    ]


def test_mixed_template_keeps_one_scan_point_to_many_counter_bins_shape() -> None:
    config = load_yaml_config(ROOT / "configs" / "experiments" / "hardware_mixed_ao_asg_counter.template.yaml")
    parsed = parse_experiment_config(config)
    scan = parsed.procedure.body[0]

    assert isinstance(scan, ScanStep)
    assert len(scan.values) == 3
    assert parsed.resolved_config["procedure"][0]["scan"]["body"][0]["measurement"]["body"][2]["call"] == (
        "daq.configure_point_readout"
    )
