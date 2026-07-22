import json
from pathlib import Path

from qulab.config.runner import run_dry_config


ROOT = Path(__file__).resolve().parents[2]


def test_generated_rabi_dry_run_and_provenance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run_dry_config(
        ROOT / "configs" / "experiments" / "dry_run_rabi_sequence_plan.yaml",
        tmp_path / "runs",
    )
    assert result.executor_state == "completed"
    metadata = json.loads((result.run_path / "metadata.json").read_text())
    assert metadata["sequence_generation"][0]["plan_id"] == "rabi_main"
    assert metadata["sequence_generation"][0]["point_count"] == 3
    assert (result.run_path / "artifacts/sequence_generation/rabi_main/sequence_plan.yaml").is_file()
