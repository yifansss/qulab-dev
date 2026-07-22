from qulab.gui.workflow_composer import WorkflowComposerModel, convert_form_values
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
