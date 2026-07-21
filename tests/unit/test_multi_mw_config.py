import json
from pathlib import Path

from qulab.config import load_yaml_config, parse_experiment_config, run_dry_config


ROOT = Path(__file__).resolve().parents[2]


def test_two_mw_yaml_parses_with_distinct_mock_resources() -> None:
    config = load_yaml_config(ROOT / "configs" / "experiments" / "dry_run_two_mw_scan.yaml")
    parsed = parse_experiment_config(config)

    assert parsed.validation.ok
    assert set(parsed.context.resources) == {"mw_drive", "mw_probe", "daq"}
    assert parsed.context.resources["mw_drive"] is not parsed.context.resources["mw_probe"]
    assert parsed.context.resources["mw_drive"].capabilities() == {"microwave_source"}
    assert parsed.context.resources["mw_probe"].capabilities() == {"microwave_source"}


def test_two_mw_dry_run_records_nested_frequency_coordinates(tmp_path) -> None:
    result = run_dry_config(ROOT / "configs" / "experiments" / "dry_run_two_mw_scan.yaml", tmp_path)

    assert result.executor_state == "completed"
    assert result.validation.ok
    points = [
        json.loads(line)
        for line in (result.run_path / "points.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    data = (result.run_path / "data.jsonl").read_text(encoding="utf-8").splitlines()

    assert sum(point["status"] == "ok" for point in points) == 6
    assert len(data) == 6
    assert "drive_freq_hz" in data[0]
    assert "probe_freq_hz" in data[0]
