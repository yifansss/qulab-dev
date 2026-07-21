import json

import pytest

from qulab.sequence_generation.providers.experiments.rabi import PROVIDER as RABI
from qulab.sequence_generation.providers.experiments.ramsey import PROVIDER as RAMSEY
from qulab.sequence_generation.providers.experiments.hahn_echo import PROVIDER as HAHN


def _defaults(provider, **patch):
    values = {item.name: item.default for item in provider.describe().parameters}
    values.update(patch); return values


def _pulses(provider, **patch):
    generated = provider.generate_point(_defaults(provider, **patch), template=None)
    return json.loads(generated.sequence_bytes), generated.metadata


def _typed(sequence, label):
    return next(pulse for channel in sequence for pulse in channel["pulses"] if pulse["type"] == label)


def test_family_specs_and_rabi_anchors():
    assert {item.name for item in RABI.describe().parameters} >= {"tau_s", "laser_to_mw_s", "mw_to_readout_s", "sequence_period_s"}
    short, metadata = _pulses(RABI, tau_s=20e-9)
    long, _ = _pulses(RABI, tau_s=100e-9)
    assert _typed(long, "readout")["start_time"] - _typed(short, "readout")["start_time"] == pytest.approx(0.08)
    assert metadata["trigger_channels"] == ["ch6"]
    assert metadata["required_acquisition_s"] == 2e-6


def test_ramsey_and_hahn_timing_definitions():
    ramsey, _ = _pulses(RAMSEY, free_evolution_s=1e-6)
    first = _typed(ramsey, "pi2_1"); second = _typed(ramsey, "pi2_2")
    assert second["start_time"] == pytest.approx(first["start_time"] + first["time_on"] + 1.0)
    hahn, metadata = _pulses(HAHN, tau_s=0.5e-6)
    first = _typed(hahn, "pi2_1"); middle = _typed(hahn, "pi"); last = _typed(hahn, "pi2_2")
    assert middle["start_time"] == pytest.approx(first["start_time"] + first["time_on"] + 0.5)
    assert last["start_time"] == pytest.approx(middle["start_time"] + middle["time_on"] + 0.5)
    assert metadata["timing"]["tau_definition"] == "each_free_evolution_arm"
    assert metadata["timing"]["total_free_evolution_s"] == pytest.approx(1e-6)


def test_deterministic_output_and_resolution_rejected():
    point = _defaults(RABI, tau_s=60e-9)
    assert RABI.generate_point(point, template=None).sequence_bytes == RABI.generate_point(point, template=None).sequence_bytes
    with pytest.raises(Exception, match="align"):
        RABI.generate_point(_defaults(RABI, tau_s=60.5e-9), template=None)
