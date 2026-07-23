from pathlib import Path
import json

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
    assert parsed.procedure.metadata["storage"]["backends"] == ["zarr"]


def test_esr_rabi_template_has_two_channel_1_ai_trigger_edges_with_safe_spacing() -> None:
    raw = json.loads((ROOT / "configs/sequences/rabi.json").read_text(encoding="utf-8"))
    channel_one = next(channel for channel in raw if channel["channel_name"] == "Channel 1")
    starts_us = sorted(float(pulse["start_time"]) for pulse in channel_one["pulses"])

    assert starts_us == [360.0, 420.0]
    # ESR uses 5 samples at 1 MHz: each retriggered record occupies 5 us.
    assert starts_us[1] - starts_us[0] > 5.0
