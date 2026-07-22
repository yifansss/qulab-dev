import json
from pathlib import Path

from qulab.config import load_experiment_config
from qulab.gui.sequence_authoring import AUTHORING_STEPS, SequenceAuthoringModel
from qulab.gui.sequence_bridge import parse_editor_protocol, run_sequence_editor_protocol

ROOT = Path(__file__).resolve().parents[2]


def test_curated_fields_are_provider_declared_and_previews_deterministic() -> None:
    config = load_experiment_config(ROOT / "configs/experiments/dry_run_rabi_sequence_family.yaml")
    model = SequenceAuthoringModel(config)
    plan_id = next(iter(config["sequence_plans"]))
    fields = model.parameter_fields(plan_id)
    assert fields and set(config["sequence_plans"][plan_id]["parameters"]) <= {field.name for field in fields}
    assert all(field.label and field.dtype for field in fields)
    previews = model.previews(plan_id)
    assert previews.point_count == 3
    assert previews.first.to_dict() == model.previews(plan_id).first.to_dict()
    assert len(model.ordered_status(plan_id)) == len(AUTHORING_STEPS)


def test_generic_catalog_inspection_stale_detection_and_macro_insertion(tmp_path: Path) -> None:
    config = load_experiment_config(ROOT / "configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    model = SequenceAuthoringModel(config); plan_id = "generic_rabi"
    assert "duration" in model.generic_operation_catalog()["Basic Timing"]
    inspection = model.inspect_generic_template(plan_id)
    assert inspection.channels
    config["procedure"] = []
    path = model.insert_or_update_macro(plan_id)
    assert path == ("procedure", 0)
    assert not any(issue.code == "sequence_workflow_link_missing" for issue in model.validate(plan_id))


def test_mode_change_requires_explicit_migration_and_shared_plan_state() -> None:
    config = load_experiment_config(ROOT / "configs/experiments/dry_run_rabi_sequence_family.yaml")
    model = SequenceAuthoringModel(config); plan_id = next(iter(config["sequence_plans"]))
    preview = model.preview_mode_change(plan_id, "generic")
    assert preview.old_mode == "curated" and preview.removed_paths
    model.change_mode(plan_id, "generic", template="configs/sequences/examples/generic_rabi_base.json")
    assert model.mode(plan_id) == "generic"
    assert config["sequence_plans"][plan_id]["family"]["provider"] == "asg_template"
    assert model.sweep.states[plan_id] == "edited"


def test_editor_protocol_success_version_error_and_timeout(tmp_path: Path) -> None:
    payload = {"protocol_version": 1, "editor_version": "1", "capabilities": ["open", "save"],
               "source": "a.json", "dirty": False, "validation": [],
               "summary": {"channels": ["ch1"], "pulse_count": 1, "duration_s": 1e-6},
               "saved_artifact": {"path": "a.json", "sha256": "abc"}}
    assert parse_editor_protocol(json.dumps(payload)).ok
    payload["protocol_version"] = 2
    assert "incompatible" in parse_editor_protocol(json.dumps(payload)).message
    assert not parse_editor_protocol("editor log\n{}").ok

    editor = tmp_path / "editor.py"; editor.write_text("", encoding="utf-8")
    def timeout(*args, **kwargs):
        import subprocess
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    assert "timed out" in run_sequence_editor_protocol(editor, timeout_s=0.1, run_factory=timeout).message


def test_editor_saved_artifact_is_reinspected_and_invalidates_prepare(tmp_path: Path) -> None:
    config = load_experiment_config(ROOT / "configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    model = SequenceAuthoringModel(config); plan_id = "generic_rabi"
    artifact = tmp_path / "edited.json"
    artifact.write_bytes((ROOT / "configs/sequences/examples/generic_rabi_base.json").read_bytes())
    import hashlib
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    model.sweep.mark_prepared(plan_id, "old")
    model.accept_editor_result(plan_id, {"path": str(artifact), "sha256": digest})
    assert model.sweep.states[plan_id] == "stale"
    assert config["sequence_plans"][plan_id]["template"] == str(artifact)
