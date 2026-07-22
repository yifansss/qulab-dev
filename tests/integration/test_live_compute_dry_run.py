import json

from qulab.config import run_dry_config


def test_dry_run_persists_raw_before_derived(tmp_path):
    config = {"name": "live", "resources": {"mock": {"adapter": "mock_microwave", "simulation": True}},
              "procedure": [{"measurement": {"name": "point", "body": [
                  {"call": "mock.set_frequency", "args": {"freq_hz": 2870000000.0}, "save_as": "source_value"}]}}],
              "analysis": {"live": {"enabled": True}, "modules": [{
                  "name": "scale_preview", "module": "analysis_modules.examples.passthrough_scale",
                  "class": "PassthroughScale", "inputs": ["source_value"], "outputs": ["scaled_value"],
                  "run_post": True, "args": {"scale": 2}}]}}
    result = run_dry_config(config, tmp_path)
    events = [json.loads(line) for line in (result.run_path / "events.jsonl").read_text().splitlines()]
    types = [event["type"] for event in events]
    assert types.index("DataPoint") < types.index("DerivedData")
    data = [json.loads(line) for line in (result.run_path / "data.jsonl").read_text().splitlines()]
    assert [row["kind"] for row in data] == ["data_point", "derived_data"]
    assert result.analysis_summary["metrics"]["scale_preview"]["processed"] == 1
