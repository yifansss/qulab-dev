from copy import deepcopy
from pathlib import Path

import yaml

from qulab.config import load_experiment_config, parse_experiment_config


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "dry_run_rabi_sequence_bundle.yaml"


def _config() -> dict:
    return load_experiment_config(CONFIG)


def _codes(parsed, severity="error") -> set[str]:
    return {issue.code for issue in parsed.validation.issues if issue.severity == severity}


def _bundle_action(config: dict) -> dict:
    return config["procedure"][0]["scan"]["body"][0]["measurement"]["body"][0]


def test_valid_bundle_coverage_trigger_route_and_window_pass() -> None:
    parsed = parse_experiment_config(_config())

    assert parsed.validation.ok
    assert parsed.validation.issues == []


def test_missing_coverage_is_preflight_error() -> None:
    config = _config()
    config["procedure"][0]["scan"]["values"].append(80e-9)

    parsed = parse_experiment_config(config)

    assert "bundle_coverage_missing" in _codes(parsed)


def test_nearest_tolerance_is_used_during_preflight() -> None:
    config = _config()
    config["procedure"][0]["scan"]["values"] = [21e-9, 41e-9, 59e-9]
    config["sequence_bundles"]["rabi_tau"]["match"] = {
        "mode": "nearest",
        "tolerance": {"tau_s": 2e-9},
    }

    assert parse_experiment_config(config).validation.ok


def test_unknown_bundle_and_resource_mismatch_have_stable_codes() -> None:
    config = _config()
    _bundle_action(config)["args"]["bundle"] = "unknown"
    assert "bundle_unknown" in _codes(parse_experiment_config(config))

    config = _config()
    config["resources"]["asg_other"] = {
        "adapter": "mock_asg",
        "capabilities": ["pulse_sequencer"],
    }
    _bundle_action(config)["call"] = "asg_other.load_sequence_from_bundle"
    assert "bundle_resource_mismatch" in _codes(parse_experiment_config(config))


def test_trigger_channel_route_and_window_mismatches_are_errors() -> None:
    config = _config()
    config["sync"]["triggers"][0]["source"] = "asg.ch5"
    assert "bundle_trigger_channel_mismatch" in _codes(parse_experiment_config(config))

    config = _config()
    config["sync"]["triggers"][0]["target"] = "daq.PFI1"
    assert "bundle_trigger_route_mismatch" in _codes(parse_experiment_config(config))

    config = _config()
    config["setup"][0]["args"]["samples"] = 4
    assert "bundle_acquisition_window_short" in _codes(parse_experiment_config(config))


def test_missing_optional_metadata_warns_but_does_not_block(tmp_path: Path) -> None:
    sequence = tmp_path / "sequence.json"
    sequence.write_text("[]", encoding="utf-8")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "kind": "sequence_bundle",
                "id": "plain_bundle",
                "resource": "asg",
                "entries": [
                    {"id": "one", "coordinates": {"tau_s": 1.0}, "sequence_file": "sequence.json"}
                ],
            }
        ),
        encoding="utf-8",
    )
    config = deepcopy(_config())
    config["sequence_bundles"] = {"plain_bundle": {"manifest": str(manifest), "resource": "asg"}}
    _bundle_action(config)["args"]["bundle"] = "plain_bundle"
    config["procedure"][0]["scan"]["values"] = [1.0]

    parsed = parse_experiment_config(config)

    assert parsed.validation.ok
    assert {
        "bundle_trigger_metadata_missing",
        "bundle_duration_metadata_missing",
    } <= _codes(parsed, "warning")
