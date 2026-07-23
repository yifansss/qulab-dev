from pathlib import Path

from qulab.config import load_experiment_config, parse_experiment_config
from qulab.core import ActionStep, MeasurementStep, ScanStep


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/experiments/esr_pse_ai1_lmx_com12.yaml"


def test_esr_frequency_scan_is_bound_to_lmx_and_uses_supported_ai_timing() -> None:
    parsed = parse_experiment_config(load_experiment_config(CONFIG))
    scan = parsed.procedure.body[0]
    assert isinstance(scan, ScanStep)
    point = scan.body[0]
    assert isinstance(point, MeasurementStep)
    calls = [step for step in point.body if isinstance(step, ActionStep)]
    configure = next(step for step in calls if step.action == "daq.configure_ai_external_trigger")
    frequency = next(step for step in calls if step.action == "mw.set_frequency")

    assert configure.kwargs["channels"] == ["ai1"]
    assert configure.kwargs["sample_rate"] == 1_000_000
    assert configure.kwargs["samples"] == 5
    assert configure.kwargs["sample_clock"] is None
    assert configure.kwargs["trigger_count"] == 2
    assert frequency.kwargs["freq_hz"].name == "mw_freq_hz"
