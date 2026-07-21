from __future__ import annotations

from pathlib import Path

from qulab.config import load_experiment_config
from qulab.gui.models import extract_parameter_edits, parse_parameter_value, update_config_value


ROOT = Path(__file__).resolve().parents[2]


def test_extract_and_update_scan_and_average_parameters() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")

    edits = extract_parameter_edits(config)
    labels = {edit.label: edit for edit in edits}

    assert labels["tau_s start"].value == 2.0e-8
    assert labels["tau_s stop"].value == 1.0e-7
    assert labels["tau_s points"].value == 5
    assert labels["avg count"].value == 2

    update_config_value(config, labels["tau_s points"].path, 7)
    update_config_value(config, labels["avg count"].path, 3)

    edited = extract_parameter_edits(config)
    edited_labels = {edit.label: edit for edit in edited}
    assert edited_labels["tau_s points"].value == 7
    assert edited_labels["avg count"].value == 3


def test_parse_parameter_value_supports_scientific_notation_and_lists() -> None:
    assert parse_parameter_value("2.5e-8", "number") == 2.5e-8
    assert parse_parameter_value("11", "int") == 11
    assert parse_parameter_value("1, 2.5e3, label", "list") == [1, 2500.0, "label"]
