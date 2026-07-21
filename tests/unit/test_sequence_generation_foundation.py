from copy import deepcopy

import pytest

from qulab.config import load_experiment_config, parse_experiment_config
from qulab.config.errors import ConfigLoadError
from qulab.sequence_bundles import load_sequence_bundle, validate_bundle_coverage
from qulab.sequence_generation import prepare_sequence_config
from qulab.sequence_generation.preparation import parse_sequence_plans
from qulab.sequence_generation.registry import SequenceProviderRegistry
from qulab.sequence_generation.sampling import enumerate_plan_points, normalize_parameter_values


def _config():
    return load_experiment_config("configs/experiments/dry_run_rabi_sequence_plan.yaml")


def test_sampling_and_cartesian_order():
    config = _config()
    raw = config["sequence_plans"]["rabi_main"]
    raw["parameters"]["readout_s"] = {"mode": "explicit", "values": [1e-6, 2e-6]}
    raw["sampling"]["order"] = ["tau_s", "readout_s"]
    plan = parse_sequence_plans(config)["rabi_main"]
    provider, _ = SequenceProviderRegistry().load(plan.provider, "2")
    values = normalize_parameter_values(plan, provider.describe())
    points = enumerate_plan_points(plan, values)
    assert [tuple(p.coordinates.values()) for p in points] == [
        (20e-9, 1e-6), (20e-9, 2e-6), (40e-9, 1e-6),
        (40e-9, 2e-6), (60e-9, 1e-6), (60e-9, 2e-6),
    ]


def test_prepare_materializes_compiles_and_hits_cache(tmp_path):
    config = _config(); original = deepcopy(config)
    first = prepare_sequence_config(config, cache_root=tmp_path)
    assert first.ok and config == original
    assert not first.generation_records[0].cache_hit
    second = prepare_sequence_config(config, cache_root=tmp_path)
    assert second.ok and second.generation_records[0].cache_hit
    bundle = load_sequence_bundle(first.materialized["rabi_main"].manifest_path)
    assert validate_bundle_coverage(bundle, ({"tau_s": v} for v in (20e-9, 40e-9, 60e-9))).ok
    scan = first.compiled_config["procedure"][0]["scan"]
    assert scan["name"] == "tau_s"
    measurement = scan["body"][0]["measurement"]
    assert measurement["body"][0]["call"] == "asg.load_sequence_from_bundle"
    assert first.compiled_config["parameters"]["laser_init_s"]["value"] == 3e-6


def test_legacy_noop_and_direct_macro_parse_message(tmp_path):
    legacy = {"name": "legacy", "resources": {}, "procedure": []}
    prepared = prepare_sequence_config(legacy, cache_root=tmp_path)
    assert prepared.ok and prepared.compiled_config == legacy
    with pytest.raises(ConfigLoadError, match="prepare_sequence_config"):
        parse_experiment_config(_config())


def test_version_mismatch_has_stable_issue(tmp_path):
    config = _config()
    config["sequence_plans"]["rabi_main"]["family"]["version"] = "999"
    prepared = prepare_sequence_config(config, cache_root=tmp_path)
    assert prepared.issues[0].code == "sequence_provider_version_mismatch"
