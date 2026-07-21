from qulab.core import (
    ActionStep,
    EventBus,
    ExperimentContext,
    ExperimentExecutor,
    MeasurementStep,
    P,
    Procedure,
    ScanStep,
    ScanValues,
    WaitStep,
)


def test_nested_scan_order_is_outer_then_inner() -> None:
    seen = []

    def record(x, y):
        seen.append((x, y))

    procedure = Procedure(
        name="nested",
        body=[
            ScanStep(
                name="x",
                values=ScanValues.explicit([1, 2]),
                body=[
                    ScanStep(
                        name="y",
                        values=ScanValues.explicit([10, 20]),
                        body=[
                            ActionStep(
                                name="record",
                                action=record,
                                kwargs={"x": P("x"), "y": P("y")},
                            )
                        ],
                    )
                ],
            )
        ],
    )

    ExperimentExecutor(procedure).run()

    assert seen == [(1, 10), (1, 20), (2, 10), (2, 20)]


def test_disabled_step_does_not_execute() -> None:
    calls = []

    procedure = Procedure(
        name="disabled",
        body=[ActionStep(name="skip", action=lambda: calls.append("ran"), enabled=False)],
    )

    ExperimentExecutor(procedure).run()

    assert calls == []


def test_multiple_actions_in_measurement_share_point_id() -> None:
    procedure = Procedure(
        name="point_outputs",
        body=[
            MeasurementStep(
                name="point",
                body=[
                    ActionStep(name="a", action=lambda: 1, save_as="a"),
                    ActionStep(name="b", action=lambda: {"value": 2}, save_as="b"),
                ],
            )
        ],
    )
    bus = EventBus()

    ExperimentExecutor(procedure, event_bus=bus).run()

    data_events = [event for event in bus.events if event.type == "DataPoint"]
    assert len(data_events) == 2
    assert {event.point_id for event in data_events} == {"p000001"}
    assert [event.data for event in data_events] == [{"a": 1}, {"b": {"value": 2}}]


def test_wait_step_emits_events_without_sleeping_in_dry_run() -> None:
    procedure = Procedure(name="wait", body=[WaitStep(name="settle", duration_s=0.01)])
    bus = EventBus()

    ExperimentExecutor(procedure, event_bus=bus, dry_run=True).run()

    started = [event for event in bus.events if event.type == "StepStarted"]
    completed = [event for event in bus.events if event.type == "StepCompleted"]
    assert started[0].step_kind == "wait"
    assert completed[0].step_name == "settle"
