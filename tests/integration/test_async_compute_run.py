import json

from qulab.config import run_dry_config


def test_async_run_raw_priority_derived_drain_and_metadata(tmp_path):
    config = {"name": "async", "resources": {"mw": {"adapter": "mock_microwave"}},
        "procedure": [{"scan": {"name": "freq", "values": [1, 2, 3], "body": [{"measurement": {"name": "p", "body": [
            {"call": "mw.set_frequency", "args": {"freq_hz": "${freq}"}, "save_as": "source_value"}]}}]}}],
        "analysis": {"live": {"enabled": True, "execution": "async", "queue_size": 2, "backpressure": "skip_newest",
                               "drain_on_close": True, "drain_timeout_s": 2}, "modules": [{"name": "scale_preview",
            "module": "analysis_modules.examples.passthrough_scale", "class": "PassthroughScale", "inputs": ["source_value"],
            "outputs": ["scaled_value"], "args": {"scale": 2}}]}}
    result = run_dry_config(config, tmp_path)
    rows = [json.loads(line) for line in (result.run_path / "data.jsonl").read_text().splitlines()]
    raw = [row for row in rows if row["kind"] == "data_point"]; derived = [row for row in rows if row["kind"] == "derived_data"]
    assert len(raw) == 3 and len(derived) == 3
    metadata = json.loads((result.run_path / "metadata.json").read_text())
    assert metadata["analysis_summary"]["engine_metrics"]["completed"] == 3
    assert metadata["status"] == "completed"
