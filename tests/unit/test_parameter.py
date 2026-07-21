import json

import pytest

from qulab.core import EventBus, ExperimentContext, P, Parameter, RunStarted, ScanValues


def test_parameter_ref_resolves_from_context() -> None:
    ctx = ExperimentContext(parameters={"x": Parameter(name="x", value=42)})

    assert ctx.resolve(P("x")) == 42
    assert ctx.resolve({"outer": [P("x"), "kept"]}) == {"outer": [42, "kept"]}


def test_unknown_parameter_ref_raises_clear_error() -> None:
    ctx = ExperimentContext()

    with pytest.raises(KeyError, match="Unknown parameter reference"):
        ctx.resolve(P("missing"))


def test_scan_values_linspace_generates_requested_points() -> None:
    values = ScanValues.linspace(0.0, 1.0, 5)

    assert len(values) == 5
    assert list(values) == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0])


def test_event_bus_subscriber_and_json_serializable_dict() -> None:
    bus = EventBus()
    received = []
    bus.subscribe(received.append)

    bus.emit(RunStarted(run_id="run_1", procedure_name="demo"))

    assert received == bus.events
    json.dumps(bus.events[0].to_dict())
