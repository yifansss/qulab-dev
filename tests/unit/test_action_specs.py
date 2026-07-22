import json

from qulab.instruments import DEFAULT_ACTION_REGISTRY, InstrumentRegistry
from qulab.instruments.action_specs import ActionSpec, ArgumentSpec, validate_action_call


def test_registry_covers_builtins_and_serializes_deterministically() -> None:
    assert set(InstrumentRegistry().list_adapters()) == set(DEFAULT_ACTION_REGISTRY.list_adapters())
    first = DEFAULT_ACTION_REGISTRY.to_json()
    assert first == DEFAULT_ACTION_REGISTRY.to_json()
    assert json.loads(first)["mock_microwave"]["version"] == 1
    ids = [action.id for adapter in DEFAULT_ACTION_REGISTRY.list_adapters()
           for action in DEFAULT_ACTION_REGISTRY.list_actions(adapter)]
    assert ids


def test_action_validation_required_unknown_type_range_choice_and_reference() -> None:
    spec = ActionSpec(
        "test.configure", "configure", "Configure", "test",
        (ArgumentSpec("count", "integer", required=True, minimum=1),
         ArgumentSpec("mode", "string", choices=("a", "b")),
         ArgumentSpec("literal", "number", allow_reference=False)),
    )
    codes = {item.code for item in validate_action_call(spec, {"mode": "c", "extra": 1})}
    assert {"action_argument_missing", "action_argument_unknown", "action_argument_choice"} <= codes
    codes = {item.code for item in validate_action_call(spec, {"count": 0, "literal": "${x}"}, {"x"})}
    assert {"action_argument_range", "action_argument_type"} <= codes


def test_data_return_lifecycle_and_safety_are_declared() -> None:
    read = DEFAULT_ACTION_REGISTRY.resolve_action("mock_daq", "read_counts")
    output = DEFAULT_ACTION_REGISTRY.resolve_action("mock_microwave", "output_on")
    assert read is not None and read.returns is not None and read.returns.save_recommended
    assert read.phase == "read" and read.safety_class == "read_only"
    assert output is not None and output.safety_class == "output"
    assert "output_enabled" in output.provides_states


def test_descriptor_discovery_does_not_construct_adapters(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("adapter construction during descriptor discovery")
    monkeypatch.setattr(InstrumentRegistry, "create", fail)
    assert DEFAULT_ACTION_REGISTRY.list_actions("pycontrol_ni")
