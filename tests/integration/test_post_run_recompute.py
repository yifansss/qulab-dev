import json

from qulab.analysis.recompute import recompute_run
from qulab.config import run_dry_config
from qulab.storage import RunReader


def source_config():
    return {"name": "post", "resources": {"mw": {"adapter": "mock_microwave"}},
            "procedure": [{"scan": {"name": "freq", "values": [1, 2], "body": [{"measurement": {"name": "p", "body": [
                {"call": "mw.set_frequency", "args": {"freq_hz": "${freq}"}, "save_as": "source_value"}]}}]}}],
            "analysis": {"live": {"enabled": True}, "modules": [{"name": "scale_preview",
                "module": "analysis_modules.examples.passthrough_scale", "class": "PassthroughScale",
                "inputs": ["source_value"], "outputs": ["scaled_value"], "run_post": True, "args": {"scale": 2}}]}}


def test_scalar_recompute_and_group_reader(tmp_path):
    source = run_dry_config(source_config(), tmp_path / "runs").run_path
    result = recompute_run(source, ["scale_preview"], result_id="post_v1")
    assert result.point_count == 2 and result.result_path.name == "post_v1"
    reader = RunReader(source)
    assert "analysis:post_v1" in reader.list_data_groups()
    assert reader.get_data_var("scaled_value", group="analysis:post_v1").values.tolist() == [2.0, 4.0]
    metadata = json.loads((result.result_path / "metadata.json").read_text())
    assert metadata["input_lineage"] == ["raw:source_value"]
    assert metadata["source_fingerprint"]["fingerprint"]
