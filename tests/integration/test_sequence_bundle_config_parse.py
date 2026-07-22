from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from qulab.config import ConfigLoadError, parse_experiment_config
from qulab.gui.controller import OperatorController


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = "configs/sequences/examples/rabi_tau_bundle/manifest.yaml"


def test_controller_bundle_browser_lists_entries_and_pulse_previews(tmp_path) -> None:
    controller = OperatorController(tmp_path / "runs")
    result = controller.load_config(ROOT / "configs/experiments/dry_run_rabi_sequence_bundle.yaml")
    assert result.activated
    summaries = controller.list_sequence_bundle_summaries()
    assert summaries[0]["id"] == "rabi_tau" and summaries[0]["entry_count"] == 3
    entries = controller.list_sequence_bundle_entries("rabi_tau")
    assert [entry["id"] for entry in entries] == ["tau_20ns", "tau_40ns", "tau_60ns"]
    preview = controller.preview_sequence_bundle_entry("rabi_tau", "tau_20ns")
    assert preview.pulses and preview.duration_s > 0


def _config() -> dict:
    return {
        "schema_version": 1,
        "name": "bundle_parse",
        "resources": {
            "asg": {"adapter": "mock_asg", "capabilities": ["pulse_sequencer"]},
        },
        "sequence_bundles": {
            "rabi_tau": {
                "manifest": MANIFEST,
                "resource": "asg",
                "match": {"mode": "nearest", "tolerance": {"tau_s": 1e-15}},
            }
        },
        "procedure": [],
    }


def test_parsed_experiment_exposes_bundle_without_mutating_serializable_config() -> None:
    config = _config()
    before = deepcopy(config)
    parsed = parse_experiment_config(config)

    assert parsed.sequence_bundles["rabi_tau"].resource == "asg"
    assert parsed.sequence_bundles["rabi_tau"].resolve({"tau_s": 40e-9}).entry_id == "tau_40ns"
    assert config == before
    yaml.safe_dump(parsed.config)
    yaml.safe_dump(parsed.resolved_config)


@pytest.mark.parametrize("value", [None, {}])
def test_null_or_empty_sequence_bundles_preserve_old_config_behavior(value) -> None:
    config = {"name": "legacy", "resources": {}, "procedure": []}
    if value is not None:
        config["sequence_bundles"] = value
    parsed = parse_experiment_config(config)

    assert parsed.sequence_bundles == {}
    assert parsed.procedure.name == "legacy"


def test_bundle_id_and_resource_mismatches_are_wrapped_as_config_errors() -> None:
    config = _config()
    config["sequence_bundles"] = {"wrong_id": config["sequence_bundles"]["rabi_tau"]}
    with pytest.raises(ConfigLoadError, match="does not match manifest id") as exc_info:
        parse_experiment_config(config)
    assert exc_info.value.__cause__ is not None

    config = _config()
    config["sequence_bundles"]["rabi_tau"]["resource"] = "other_asg"
    with pytest.raises(ConfigLoadError, match="does not match manifest resource"):
        parse_experiment_config(config)


def test_bundle_resource_must_exist_and_support_pulse_sequencer() -> None:
    config = _config()
    config["resources"] = {}
    with pytest.raises(ConfigLoadError, match="missing resource 'asg'"):
        parse_experiment_config(config)

    config = _config()
    config["resources"]["asg"] = {
        "adapter": "mock_microwave",
        "capabilities": ["microwave_source"],
    }
    with pytest.raises(ConfigLoadError, match="pulse_sequencer"):
        parse_experiment_config(config)

    config = _config()
    config["resources"]["asg"] = {
        "adapter": "mock_microwave",
        "capabilities": ["pulse_sequencer"],
    }
    with pytest.raises(ConfigLoadError, match="does not support pulse_sequencer"):
        parse_experiment_config(config)


def test_missing_project_relative_manifest_is_a_config_error() -> None:
    config = _config()
    config["sequence_bundles"]["rabi_tau"]["manifest"] = "configs/sequences/missing/manifest.yaml"

    with pytest.raises(ConfigLoadError, match="manifest not found"):
        parse_experiment_config(config)
