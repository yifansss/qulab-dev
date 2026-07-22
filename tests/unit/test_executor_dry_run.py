import pytest

from qulab.core import (
    ActionStep,
    AverageStep,
    CleanupStep,
    EventBus,
    ExperimentContext,
    ExperimentExecutor,
    MeasurementStep,
    P,
    Procedure,
    RunStep,
    ScanStep,
    ScanValues,
)


def test_dry_run_one_dimensional_scan_emits_data_points() -> None:
    procedure = Procedure(
        name="one_d",
        body=[
            ScanStep(
                name="freq",
                values=ScanValues.explicit([1.0, 2.0, 3.0]),
                body=[
                    MeasurementStep(
                        name="point",
                        body=[
                            ActionStep(
                                name="read",
                                action=lambda freq: freq * 10,
                                kwargs={"freq": P("freq")},
                                save_as="counts",
                            )
                        ],
                    )
                ],
            )
        ],
    )
    bus = EventBus()
    executor = ExperimentExecutor(procedure, event_bus=bus, dry_run=True)

    executor.run()

    assert executor.state == "completed"
    data_events = [event for event in bus.events if event.type == "DataPoint"]
    assert [event.point_id for event in data_events] == ["p000001", "p000002", "p000003"]
    assert [event.coords["freq"] for event in data_events] == [1.0, 2.0, 3.0]
    assert [event.data["counts"] for event in data_events] == [10.0, 20.0, 30.0]


def test_dry_run_two_dimensional_scan_with_average_and_run_step() -> None:
    calls = []

    def read_counts(freq_hz, tau_s, avg):
        calls.append((freq_hz, tau_s, avg))
        return {"counts_mean": 1000.0, "raw_bins": [1, 2, 3]}

    procedure = Procedure(
        name="dry_run_rabi_2d",
        body=[
            ScanStep(
                name="mw_freq_hz",
                values=ScanValues.linspace(2.86e9, 2.88e9, 3),
                body=[
                    ScanStep(
                        name="tau_s",
                        values=ScanValues.linspace(20e-9, 100e-9, 5),
                        body=[
                            MeasurementStep(
                                name="point",
                                body=[
                                    AverageStep(
                                        name="avg",
                                        count=2,
                                        body=[
                                            RunStep(
                                                name="readout",
                                                body=[
                                                    ActionStep(
                                                        name="read_counts",
                                                        action=read_counts,
                                                        kwargs={
                                                            "freq_hz": P("mw_freq_hz"),
                                                            "tau_s": P("tau_s"),
                                                            "avg": P("avg"),
                                                        },
                                                        save_as="counts",
                                                    )
                                                ],
                                            )
                                        ],
                                    )
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
    )
    bus = EventBus()

    ExperimentExecutor(procedure, event_bus=bus, dry_run=True).run()

    measurement_started = [event for event in bus.events if event.type == "MeasurementStarted"]
    data_points = [event for event in bus.events if event.type == "DataPoint"]
    assert len(measurement_started) == 15
    assert len(data_points) == 30
    assert len(calls) == 30
    assert data_points[0].point_id == "p000001"
    assert data_points[1].point_id == "p000001"
    assert data_points[-1].point_id == "p000015"
    assert [point.coords["avg"] for point in data_points[:2]] == [0, 1]


def test_resource_method_action_string_is_supported() -> None:
    class MockCounter:
        def read(self, scale):
            return 5 * scale

    ctx = ExperimentContext(resources={"counter": MockCounter()})
    procedure = Procedure(
        name="resource_action",
        body=[
            MeasurementStep(
                name="point",
                body=[
                    ActionStep(
                        name="read",
                        action="counter.read",
                        kwargs={"scale": 2},
                        save_as="counts",
                    )
                ],
            )
        ],
    )
    bus = EventBus()

    ExperimentExecutor(procedure, context=ctx, event_bus=bus).run()

    data_event = next(event for event in bus.events if event.type == "DataPoint")
    assert data_event.data == {"counts": 10}


def test_hardware_like_resource_can_run_after_explicit_connection() -> None:
    class HardwareLikeResource:
        simulation = False
        connected = False

        def connect(self):
            self.connected = True

        def disconnect(self):
            self.connected = False

        def run(self):
            if not self.connected:
                raise RuntimeError("not connected")
            return "ok"

    resource = HardwareLikeResource()
    ctx = ExperimentContext(resources={"asg": resource})
    procedure = Procedure(name="hardware_like", body=[ActionStep(name="run", action="asg.run", save_as="result")])
    bus = EventBus()

    resource.connect()
    try:
        ExperimentExecutor(procedure, context=ctx, event_bus=bus).run()
    finally:
        resource.disconnect()

    data_event = next(event for event in bus.events if event.type == "DataPoint")
    assert data_event.data == {"result": "ok"}
    assert resource.connected is False


def test_error_event_is_emitted_and_cleanup_still_runs() -> None:
    cleanup_calls = []

    def fail():
        raise RuntimeError("boom")

    procedure = Procedure(
        name="failure",
        body=[ActionStep(name="fail", action=fail)],
        cleanup=[
            CleanupStep(
                name="cleanup",
                body=[ActionStep(name="cleanup_action", action=lambda: cleanup_calls.append("done"))],
            )
        ],
    )
    bus = EventBus()
    executor = ExperimentExecutor(procedure, event_bus=bus)

    with pytest.raises(RuntimeError, match="boom"):
        executor.run()

    assert executor.state == "failed"
    assert cleanup_calls == ["done"]
    assert any(event.type == "ErrorRaised" and event.message == "boom" for event in bus.events)
    assert bus.events[-1].type == "RunCompleted"
    assert bus.events[-1].status == "failed"


def test_stop_request_cancels_scan_and_still_runs_cleanup() -> None:
    calls = []
    cleanup_calls = []
    executor = None

    def read(value):
        calls.append(value)
        if value == 1:
            executor.request_stop()
        return value

    procedure = Procedure(
        name="cancel_scan",
        body=[ScanStep(name="index", values=ScanValues.explicit([1, 2, 3]), body=[
            ActionStep(name="read", action=read, kwargs={"value": P("index")}, save_as="value")
        ])],
        cleanup=[ActionStep(name="cleanup", action=lambda: cleanup_calls.append("done"))],
    )
    bus = EventBus()
    executor = ExperimentExecutor(procedure, event_bus=bus)

    executor.run()

    assert executor.state == "cancelled"
    assert calls == [1]
    assert cleanup_calls == ["done"]
    assert bus.events[-1].type == "RunCompleted"
    assert bus.events[-1].status == "cancelled"
    assert not [event for event in bus.events if event.type == "ErrorRaised"]
