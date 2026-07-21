from __future__ import annotations

from pathlib import Path

from qulab.config import load_experiment_config, parse_experiment_config
from qulab.config.refs import parameter_refs_to_strings
from qulab.core import ParameterRef
from qulab.gui.workflow_model import update_node
from qulab.gui.yaml_editor import save_config_yaml


ROOT = Path(__file__).resolve().parents[2]


def test_rabi_yaml_roundtrip_preserves_call_arg_parameter_ref(tmp_path: Path) -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    call_path = ("procedure", 0, "scan", "body", 0, "measurement", "body", 0)
    config = update_node(config, call_path, {"args": {"name": "tau_s", "value": "${tau_s}"}})

    path = tmp_path / "edited_rabi.yaml"
    save_config_yaml(config, path)
    reloaded = load_experiment_config(path)
    parsed = parse_experiment_config(reloaded)

    action = parsed.procedure.body[0].body[0].body[0]
    assert isinstance(action.kwargs["value"], ParameterRef)
    assert parameter_refs_to_strings(action.kwargs)["value"] == "${tau_s}"


def test_two_mw_yaml_roundtrip_after_probe_points_edit(tmp_path: Path) -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_two_mw_scan.yaml")
    probe_scan_path = ("procedure", 0, "scan", "body", 1)
    config = update_node(config, probe_scan_path, {"scan": {"values": {"start": 2.86e9, "stop": 2.88e9, "points": 2}}})

    path = tmp_path / "edited_two_mw.yaml"
    save_config_yaml(config, path)
    reloaded = load_experiment_config(path)
    parsed = parse_experiment_config(reloaded)

    probe_scan = parsed.procedure.body[0].body[1]
    assert len(list(probe_scan.values)) == 2
