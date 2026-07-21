import json
from pathlib import Path

import pytest

from qulab.config.runner import run_dry_config


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("family,coordinate", [("rabi", "tau_s"), ("ramsey", "free_evolution_s"), ("hahn_echo", "tau_s")])
def test_curated_family_dry_run_and_reconstructable_provenance(tmp_path, monkeypatch, family, coordinate):
    work = tmp_path / family; work.mkdir(); monkeypatch.chdir(work)
    result = run_dry_config(ROOT / f"configs/experiments/dry_run_{family}_sequence_family.yaml", work / "runs")
    assert result.executor_state == "completed"
    metadata = json.loads((result.run_path / "metadata.json").read_text())
    generation = metadata["sequence_generation"][0]
    assert generation["provider_source_hash"]
    assert generation["point_count"] == 3
    selections = [json.loads(line) for line in (result.run_path / "sequence_selections.jsonl").read_text().splitlines()]
    point_updates = [json.loads(line) for line in (result.run_path / "points.jsonl").read_text().splitlines()]
    points_by_id = {item["point_id"]: item for item in point_updates}
    points = list(points_by_id.values())
    assert len(selections) == 3
    assert [item["requested_coordinates"][coordinate] for item in selections] == [item["coords"][coordinate] for item in points]
    assert all((result.run_path / item["artifact_path"]).is_file() for item in selections)


def test_bench_templates_are_yaml_only_and_safety_gated():
    from qulab.config import load_experiment_config
    for number in (10, 11, 12):
        path = next((ROOT / "configs/experiments").glob(f"bench_{number}_*.template.yaml"))
        config = load_experiment_config(path)
        assert config["safety"]["template_only"] is True
        assert config["safety"]["requires_allow_output"] is True
        assert config["safety"]["physically_verified"] is False
