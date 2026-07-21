import json

import pytest

from qulab.core import (
    ActionStep,
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
from qulab.storage import RunStore


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_dry_run_executor_writes_storage_run(tmp_path) -> None:
    def read_counts(freq_hz):
        return {"counts_mean": 1000.0, "photon_bins": [1, 2, 3], "freq_seen": freq_hz}

    procedure = Procedure(
        name="storage_dry_run",
        body=[
            ScanStep(
                name="mw_freq_hz",
                values=ScanValues.linspace(2.86e9, 2.88e9, 3),
                body=[
                    MeasurementStep(
                        name="point",
                        body=[
                            RunStep(
                                name="readout",
                                body=[
                                    ActionStep(
                                        name="read_counts",
                                        action=read_counts,
                                        kwargs={"freq_hz": P("mw_freq_hz")},
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
    bus = EventBus()
    store = RunStore(root=tmp_path, experiment_name="storage_dry_run", run_id="dry_run")
    store.open()
    bus.subscribe(store.handle_event)

    ctx = ExperimentContext()
    executor = ExperimentExecutor(procedure, ctx, bus, dry_run=True)
    executor.run()
    store.close(status=executor.state)

    assert (store.run_path / "metadata.json").exists()
    assert (store.run_path / "events.jsonl").exists()
    assert (store.run_path / "data.jsonl").exists()
    metadata = json.loads((store.run_path / "metadata.json").read_text(encoding="utf-8"))
    data = _read_jsonl(store.run_path / "data.jsonl")
    points = _read_jsonl(store.run_path / "points.jsonl")

    assert metadata["status"] == "completed"
    assert metadata["point_count"] == 3
    assert len(data) == 3
    assert data[0]["point_id"] == "p000001"
    assert data[0]["data"]["counts"]["photon_bins"] == [1, 2, 3]
    assert points[-1]["point_id"] == "p000003"
    assert points[-1]["status"] == "ok"


def test_failed_dry_run_storage_keeps_prior_data(tmp_path) -> None:
    calls = 0

    def read_counts(freq_hz):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("read failed")
        return freq_hz

    procedure = Procedure(
        name="storage_failure",
        body=[
            ScanStep(
                name="mw_freq_hz",
                values=ScanValues.explicit([1.0, 2.0]),
                body=[
                    MeasurementStep(
                        name="point",
                        body=[ActionStep(name="read_counts", action=read_counts, kwargs={"freq_hz": P("mw_freq_hz")}, save_as="counts")],
                    )
                ],
            )
        ],
    )
    bus = EventBus()
    store = RunStore(root=tmp_path, experiment_name="storage_failure", run_id="failure")
    store.open()
    bus.subscribe(store.handle_event)
    executor = ExperimentExecutor(procedure, event_bus=bus)

    with pytest.raises(RuntimeError, match="read failed"):
        executor.run()
    store.close(status=executor.state)

    metadata = json.loads((store.run_path / "metadata.json").read_text(encoding="utf-8"))
    events = _read_jsonl(store.run_path / "events.jsonl")
    data = _read_jsonl(store.run_path / "data.jsonl")
    points = _read_jsonl(store.run_path / "points.jsonl")

    assert metadata["status"] == "failed"
    assert any(event["type"] == "ErrorRaised" for event in events)
    assert data == [
        {
            "coords": {"mw_freq_hz": 1.0},
            "data": {"counts": 1.0},
            "data_specs": {"counts": {"kind": "scalar", "shape": [], "unit": None}},
            "kind": "data_point",
            "metadata": {"step_id": "read_counts", "step_name": "read_counts"},
            "point_id": "p000001",
            "time": data[0]["time"],
        }
    ]
    assert points[-1]["point_id"] == "p000002"
    assert points[-1]["status"] in {"failed", "partial"}
