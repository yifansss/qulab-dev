import json

import pytest

from qulab.config import load_experiment_config
from qulab.sequence_bundles import load_sequence_bundle
from qulab.sequence_generation import prepare_sequence_config
from qulab.sequence_generation.preparation import parse_sequence_plans
from qulab.sequence_generation.providers.asg_model import AsgSequence, PulseSelector, inspect_template, normalize_channel_name
from qulab.sequence_generation.providers.asg_transforms import resolve_targets, transform_sequence


TEMPLATE = "configs/sequences/examples/generic_rabi_base.json"


def test_model_roundtrip_unknown_fields_and_channel_normalization():
    raw = open(TEMPLATE, "rb").read()
    model = AsgSequence.from_bytes(raw)
    roundtrip = json.loads(model.to_bytes())
    assert roundtrip[0]["vendor_note"] == "microwave"
    assert normalize_channel_name("Channel 06") == normalize_channel_name("ch6")
    inspection = inspect_template(TEMPLATE)
    assert inspection.channels[1]["pulses"][0]["start_s"] == pytest.approx(5e-6)


def test_duration_all_channel_propagation_and_immutable_base():
    config = load_experiment_config("configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    plan = parse_sequence_plans(config)["generic_rabi"]
    base = AsgSequence.from_path(plan.template)
    changed = transform_sequence(base, plan, {"tau_s": 0.6e-6, "readout_shift_s": 0.5e-6})
    targets = resolve_targets(base, plan)
    assert base.pulse_view(targets["mw_pulse"]).duration_s == pytest.approx(0.1e-6)
    assert changed.pulse_view(targets["mw_pulse"]).duration_s == pytest.approx(0.6e-6)
    # direct +0.5 us shift plus +0.5 us following propagation
    assert changed.pulse_view(targets["readout_gate"]).start_s == pytest.approx(6e-6)


def test_anchor_chain_and_cycle():
    config = load_experiment_config("configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    raw = config["sequence_plans"]["generic_rabi"]
    raw["parameters"].pop("readout_shift_s")
    raw["sampling"]["order"] = ["tau_s"]
    raw["parameters"]["tau_s"]["transform"]["propagation"] = {"mode": "none"}
    raw["constraints"] = [{"type": "anchor", "target": "readout_gate.start", "reference": "mw_pulse.end", "offset_s": 1e-6}]
    plan = parse_sequence_plans(config)["generic_rabi"]
    base = AsgSequence.from_path(plan.template)
    changed = transform_sequence(base, plan, {"tau_s": 0.5e-6})
    assert changed.pulse_view(resolve_targets(base, plan)["readout_gate"]).start_s == pytest.approx(4.5e-6)
    raw["constraints"] = [
        {"type": "anchor", "target": "readout_gate.start", "reference": "mw_pulse.start", "offset_s": 0},
        {"type": "anchor", "target": "mw_pulse.start", "reference": "readout_gate.start", "offset_s": 0},
    ]
    cycle_plan = parse_sequence_plans(config)["generic_rabi"]
    with pytest.raises(Exception, match="cycle"):
        transform_sequence(base, cycle_plan, {"tau_s": 0.5e-6})


def test_generic_provider_materializes_2d_bundle(tmp_path):
    config = load_experiment_config("configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    prepared = prepare_sequence_config(config, cache_root=tmp_path)
    assert prepared.ok, [issue.to_dict() for issue in prepared.issues]
    bundle = load_sequence_bundle(prepared.materialized["generic_rabi"].manifest_path)
    assert len(bundle.entries) == 4
    assert tuple(bundle.entries[0].coordinates) == ("tau_s", "readout_shift_s")
    assert bundle.entries[0].metadata["trigger_channels"] == ["Channel 6"]
