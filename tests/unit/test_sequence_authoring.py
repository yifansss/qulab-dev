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


def test_dynamic_generic_fields_roles_targets_and_normalized_preview() -> None:
    config = load_experiment_config(ROOT / "configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    model = SequenceAuthoringModel(config); plan_id = "generic_rabi"
    assert {item.name for item in model.parameter_fields(plan_id)} == {"tau_s", "readout_shift_s"}
    model.update_roles(plan_id, {"daq_trigger_channel": "Channel 6"})
    model.inspect_generic_template(plan_id)
    model.update_target_transform(plan_id, "mw_pulse", "Channel 1", 0, parameter="tau_s",
                                  property_name="duration", propagation="shift_after", scope="all_channels")
    raw = config["sequence_plans"][plan_id]
    assert raw["options"]["channel_roles_confirmed"] is True
    assert raw["parameters"]["tau_s"]["transform"]["propagation"]["mode"] == "shift_after"
    first, current, last = model.normalized_previews(plan_id, 1)
    assert first.pulses and current.pulses and last.pulses
    assert first.channels and first.duration_s > 0


def test_invalid_parameter_edit_is_transactional_and_non_sweepable_fails() -> None:
    config = load_experiment_config(ROOT / "configs/experiments/dry_run_rabi_sequence_family.yaml")
    model = SequenceAuthoringModel(config); plan_id = "rabi"
    before = model.revision(plan_id)
    try: model.update_parameter(plan_id, "tau_s", {"mode": "explicit", "values": []})
    except Exception: pass
    else: raise AssertionError("empty sweep was accepted")
    assert model.revision(plan_id) == before
    try: model.update_parameter(plan_id, "sequence_period_s", {"mode": "linspace", "start": 1e-6, "stop": 2e-6, "points": 2})
    except ValueError as exc: assert "not sweepable" in str(exc)
    else: raise AssertionError("non-sweepable parameter was swept")


def test_trigger_acquisition_and_issue_step_mapping() -> None:
    config = load_experiment_config(ROOT / "configs/experiments/dry_run_generic_asg_template_sweep.yaml")
    config["sequence_plans"]["generic_rabi"]["options"]["trigger_channels"] = ["Channel 5"]
    config["setup"] = [{"call": "daq.configure_counter", "args": {"sample_rate": 1e6, "samples": 10}}]
    config["sequence_plans"]["generic_rabi"]["options"]["readout_window_s"] = 1e-6
    issues = SequenceAuthoringModel(config).located_issues("generic_rabi")
    by_code = {item.code: item for item in issues}
    assert by_code["sequence_trigger_channel_mismatch"].step == "channel_roles"
    assert by_code["sequence_acquisition_window_mismatch"].step == "channel_roles"
