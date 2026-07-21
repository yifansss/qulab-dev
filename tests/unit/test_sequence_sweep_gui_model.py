from copy import deepcopy

from qulab.config import load_experiment_config
from qulab.gui.controller import OperatorController
from qulab.gui.sequence_sweep_model import SequenceSweepEditorModel


CONFIG = "configs/experiments/dry_run_generic_asg_template_sweep.yaml"


def test_model_update_duplicate_delete_and_mode_cleanup():
    config = load_experiment_config(CONFIG)
    model = SequenceSweepEditorModel.load(config)
    assert model.list_plans()[0].point_count == 4
    model.update_parameter("generic_rabi", "tau_s", {"mode": "fixed", "value": 30e-9})
    raw = config["sequence_plans"]["generic_rabi"]
    assert raw["parameters"]["tau_s"] == {"mode": "fixed", "value": 30e-9, "unit": "s", "transform": raw["parameters"]["tau_s"]["transform"]}
    assert raw["sampling"]["order"] == ["readout_shift_s"]
    model.duplicate_plan("generic_rabi", "copy")
    assert len(model.list_plans()) == 2
    model.remove_plan("copy"); assert len(model.list_plans()) == 1


def test_controller_preview_prepare_and_mutation_invalidation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    controller = OperatorController(tmp_path / "runs")
    controller.load_config(
        "/Users/matt/Library/CloudStorage/SynologyDrive-Workspace/00_Workspace/30_Projects/Dev/qulab/" + CONFIG
    )
    estimate = controller.estimate_sequence_plan("generic_rabi")
    assert estimate.point_count == 4
    preview = controller.preview_sequence_plan("generic_rabi", dict(estimate.last))
    assert preview.total_duration_s > 0
    view = controller.prepare(); assert view.ok
    assert controller.list_sequence_plans()[0].state == "prepared"
    assert controller.compiled_sequence_workflow_preview()["procedure"][0].get("scan")
    controller.update_sequence_plan_parameter("generic_rabi", "tau_s", {"mode": "explicit", "values": [40e-9]})
    assert controller.parsed is None
    assert controller.list_sequence_plans()[0].state == "stale"


def test_yaml_authoring_patch_has_no_compiled_paths():
    config = load_experiment_config(CONFIG); original = deepcopy(config)
    model = SequenceSweepEditorModel.load(config)
    patch = model.to_config_patch()
    assert patch["sequence_plans"] == original["sequence_plans"]
    assert "sequence_bundles" not in patch
