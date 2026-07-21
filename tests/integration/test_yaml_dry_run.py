import json
from pathlib import Path

from qulab.config import load_yaml_config, parse_experiment_config, run_dry_config


ROOT = Path(__file__).resolve().parents[2]


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_load_dry_run_rabi_preflight_and_execute_to_run_store(tmp_path) -> None:
    config_path = ROOT / "configs" / "experiments" / "dry_run_rabi.yaml"
    config = load_yaml_config(config_path)
    parsed = parse_experiment_config(config)

    assert parsed.name == "dry_run_rabi"
    assert set(parsed.context.resources) == {"mw", "asg", "daq"}
    assert parsed.validation.ok

    result = run_dry_config(config_path, tmp_path)

    assert result.executor_state == "completed"
    assert result.validation.ok
    assert (result.run_path / "metadata.json").exists()
    assert (result.run_path / "events.jsonl").exists()
    assert (result.run_path / "data.jsonl").exists()
    assert (result.run_path / "points.jsonl").exists()
    assert (tmp_path / "run_index.sqlite").exists()

    metadata = json.loads((result.run_path / "metadata.json").read_text(encoding="utf-8"))
    events = _read_jsonl(result.run_path / "events.jsonl")
    data = _read_jsonl(result.run_path / "data.jsonl")
    points = _read_jsonl(result.run_path / "points.jsonl")

    assert metadata["status"] == "completed"
    assert metadata["point_count"] == 5
    assert metadata["completed_point_count"] == 5
    assert any(event["type"] == "RunStarted" for event in events)
    assert any(event["type"] == "RunCompleted" for event in events)
    assert len(data) == 10
    assert data[0]["point_id"] == "p000001"
    assert data[0]["coords"]["tau_s"] == 2.0e-8
    assert data[0]["data"]["counts"]["photon_bins"] == [1000, 1001, 1002]
    assert points[-1]["point_id"] == "p000005"
    assert points[-1]["status"] == "ok"


def test_dry_run_odmr_yaml_is_parseable_and_preflight_ok() -> None:
    config = load_yaml_config(ROOT / "configs" / "experiments" / "dry_run_odmr.yaml")
    parsed = parse_experiment_config(config)

    assert parsed.validation.ok
    assert parsed.sync_plan is not None
    assert len(parsed.sync_plan.triggers) == 1
