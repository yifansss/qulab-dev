from __future__ import annotations

from pathlib import Path

from qulab.config import load_experiment_config, parse_experiment_config
from qulab.gui.workflow_model import (
    add_step,
    build_workflow_tree,
    delete_step,
    duplicate_step,
    make_default_step,
    update_node,
)


ROOT = Path(__file__).resolve().parents[2]


def test_build_workflow_tree_contains_sections_and_nested_steps() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_two_mw_scan.yaml")

    root = build_workflow_tree(config)

    assert [child.kind for child in root.children] == ["setup", "procedure", "cleanup"]
    procedure = root.children[1]
    assert procedure.children[0].kind == "scan"
    assert procedure.children[0].children[1].kind == "scan"


def test_workflow_add_duplicate_delete_step_roundtrip() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")

    config = add_step(config, ("procedure",), make_default_step("call"))
    assert config["procedure"][-1]["call"] == "resource.method"

    config = duplicate_step(config, ("procedure", 0))
    assert len(config["procedure"]) == 3

    config = delete_step(config, ("procedure", 1))
    assert len(config["procedure"]) == 2
    parse_experiment_config(config)


def test_workflow_update_scan_and_enabled_flag_are_parsed() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    config = update_node(
        config,
        ("procedure", 0),
        {"enabled": False, "scan": {"values": {"start": 1e-8, "stop": 3e-8, "points": 4}}},
    )

    parsed = parse_experiment_config(config)
    values = list(parsed.procedure.body[0].values)

    assert parsed.procedure.body[0].enabled is False
    assert len(values) == 4
    assert values[0] == 1e-8
    assert values[-1] == 3e-8


def test_workflow_update_call_args_replaces_deleted_keys() -> None:
    config = {
        "name": "args_delete",
        "setup": [{"call": "mw.set_power", "args": {"power_dbm": -10, "unused": 1}}],
        "procedure": [],
        "cleanup": [],
    }

    updated = update_node(config, ("setup", 0), {"args": {"power_dbm": -12}})

    assert updated["setup"][0]["args"] == {"power_dbm": -12}
