from qulab.gui.workflow_composer import WorkflowComposerModel, convert_form_values
from qulab.gui.sequence_authoring import SequenceAuthoringModel
from qulab.gui.sequence_sweep_model import SequenceSweepEditorModel
from qulab.instruments import DEFAULT_ACTION_REGISTRY


def _config():
    return {
        "name": "composer",
        "resources": {"mw": {"adapter": "mock_microwave"}, "daq": {"adapter": "mock_daq"}},
        "procedure": [], "cleanup": [],
    }


def test_palette_is_resource_schema_filtered_and_searchable() -> None:
    model = WorkflowComposerModel(_config())
    methods = {item.action.method for item in model.list_palette(search="frequency") if item.action}
    assert methods == {"set_frequency"}
    assert all(item.resource == "mw" for item in model.list_palette(search="frequency"))


def test_schema_form_insert_wrap_move_delete_and_undo_redo() -> None:
    model = WorkflowComposerModel(_config())
    frequency = DEFAULT_ACTION_REGISTRY.resolve_action("mock_microwave", "set_frequency")
    assert frequency is not None
    values = convert_form_values(frequency, {"freq_hz": "2870000000"})
    first = model.insert_action("mw", frequency, values, ("procedure",))
    second = model.insert_structural_step("wait", ("procedure",))
    wrapped = model.wrap_steps((first, second), "measurement")
    assert len(model.config["procedure"]) == 1
    duplicate = model.duplicate(wrapped)
    model.delete(duplicate)
    assert model.undo() and len(model.config["procedure"]) == 2
    assert model.redo() and len(model.config["procedure"]) == 1


def test_schema_form_converts_list_and_null_arguments() -> None:
    action = DEFAULT_ACTION_REGISTRY.resolve_action("pycontrol_ni", "configure_ai_external_trigger")
    assert action is not None
    values = convert_form_values(action, {"channels": "ai2, ai3", "sample_clock": "null"})
    assert values == {"channels": ["ai2", "ai3"], "sample_clock": None}


def test_scope_rename_updates_references_and_invalidates_prepare() -> None:
    config = _config()
    config["procedure"] = [{"scan": {"name": "x", "values": [1], "body": [{"call": "mw.set_frequency", "args": {"freq_hz": "${x}"}}]}}]
    model = WorkflowComposerModel(config); model.mark_prepared("abc")
    preview = model.rename_scan(("procedure", 0), "frequency")
    assert preview.references
    assert config["procedure"][0]["scan"]["body"][0]["args"]["freq_hz"] == "${frequency}"
    assert model.prepared_hash is None


def test_completeness_uses_action_states_safety_returns_and_cleanup() -> None:
    config = _config()
    config["procedure"] = [
        {"call": "daq.read_counts", "args": {}},
        {"call": "mw.output_on", "args": {}},
    ]
    codes = {item.code for item in WorkflowComposerModel(config).validate_complete()}
    assert {"workflow_lifecycle_missing", "action_result_unsaved", "unsafe_action_not_authorized", "cleanup_missing"} <= codes


def test_recipe_is_canonical_and_safety_closed() -> None:
    model = WorkflowComposerModel(_config())
    model.apply_recipe("generated_rabi")
    assert model.config["procedure"]
    assert model.config["safety"]["allow_output"] is False


def test_scan_targets_bind_action_argument_without_manual_reference_editing() -> None:
    config = _config()
    config["procedure"] = [{"call": "mw.set_frequency", "args": {"freq_hz": 2.87e9}}]
    model = WorkflowComposerModel(config)
    target = next(item for item in model.list_scan_targets() if item.label.endswith("freq_hz"))
    model.configure_scan_target(target.id, "mw_freq_hz", {"start": 2.8e9, "stop": 2.9e9, "points": 11})
    scan = config["procedure"][0]["scan"]
    assert scan["name"] == "mw_freq_hz"
    assert scan["body"][0]["args"]["freq_hz"] == "${mw_freq_hz}"


def test_sequence_scan_target_updates_plan_without_creating_parallel_scan() -> None:
    config = _config()
    config["sequence_plans"] = {"rabi": {"parameters": {"tau_s": {"mode": "fixed", "value": 1e-6, "unit": "s"}}}}
    model = WorkflowComposerModel(config)
    target = model.list_scan_targets()[0]
    changed = model.configure_scan_target(target.id, "tau_s", {"start": 0.0, "stop": 2e-6, "points": 21})
    assert changed.kind == "sequence"
    assert config["sequence_plans"]["rabi"]["parameters"]["tau_s"]["mode"] == "linspace"
    assert config["procedure"] == []


def test_sequence_sweep_compiler_load_is_not_reported_as_missing_lifecycle() -> None:
    config = {
        "resources": {"asg": {"adapter": "mock_asg"}},
        "procedure": [{"sequence_sweep": {"plan": "rabi", "body": [
            {"call": "asg.compile_sequence"}, {"call": "asg.arm"}, {"call": "asg.start"}
        ]}}],
        "cleanup": [{"call": "asg.stop"}],
    }
    issues = WorkflowComposerModel(config).validate_complete()
    assert not any(item.code == "workflow_lifecycle_missing" for item in issues)


def test_existing_sequence_macro_is_not_replaced_when_link_is_refreshed() -> None:
    config = _config()
    config["resources"]["asg"] = {"adapter": "mock_asg"}
    config["sequence_plans"] = {"rabi": {"resource": "asg", "provider": "rabi", "parameters": {}}}
    custom_body = [{"call": "daq.configure_ai_external_trigger", "args": {"trigger_count": 2}}]
    config["procedure"] = [{"sequence_sweep": {"plan": "rabi", "body": custom_body.copy()}}]
    sweep = SequenceSweepEditorModel.load(config)
    model = SequenceAuthoringModel(config, sweep)
    model.insert_or_update_macro("rabi")
    assert config["procedure"][0]["sequence_sweep"]["body"] == custom_body
