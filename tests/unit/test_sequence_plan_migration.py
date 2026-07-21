from pathlib import Path

import pytest

from qulab.config import load_experiment_config
from qulab.sequence_generation import prepare_sequence_config
from qulab.sequence_generation.migration import inspect_bundle_for_migration, sequence_plan_from_template, write_sequence_plan_from_template


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "configs/sequences/examples/generic_rabi_base.json"


def test_migration_is_conservative_and_preparable(tmp_path):
    source_before = TEMPLATE.read_bytes()
    config = sequence_plan_from_template(TEMPLATE, project_root=ROOT, plan_id="imported")
    assert config["sequence_plans"]["imported"]["targets"] == {}
    assert "warnings" in config["migration"]
    output = tmp_path / "imported.yaml"
    write_sequence_plan_from_template(TEMPLATE, output, project_root=ROOT, plan_id="imported")
    assert TEMPLATE.read_bytes() == source_before
    loaded = load_experiment_config(output)
    prepared = prepare_sequence_config(loaded, cache_root=tmp_path / "cache")
    assert prepared.ok, [issue.to_dict() for issue in prepared.issues]
    with pytest.raises(FileExistsError):
        write_sequence_plan_from_template(TEMPLATE, output, project_root=ROOT)


def test_bundle_report_is_explicitly_irreversible():
    report = inspect_bundle_for_migration(ROOT / "configs/sequences/examples/rabi_tau_bundle/manifest.yaml")
    assert report["reversible"] is False
    assert report["coordinates"] == ["tau_s"]
