import json
import sqlite3

from qulab.core import DataPoint, ErrorRaised, LogMessage, MeasurementCompleted, MeasurementStarted
from qulab.storage import RunStore


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_run_store_creates_run_files_and_metadata(tmp_path) -> None:
    store = RunStore(
        root=tmp_path,
        experiment_name="Dry Run Rabi",
        config={"name": "raw"},
        resolved_config={"name": "resolved"},
        run_id="stable run",
    )

    store.open()
    store.close()

    assert store.run_path.name == "stable_run"
    assert (store.run_path / "config.yaml").exists()
    assert (store.run_path / "resolved_config.yaml").exists()
    assert (store.run_path / "events.jsonl").exists()
    assert (store.run_path / "data.jsonl").exists()
    assert (store.run_path / "points.jsonl").exists()
    assert (store.run_path / "logs.txt").exists()
    metadata = json.loads((store.run_path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "completed"
    assert metadata["experiment_name"] == "Dry_Run_Rabi"
    assert metadata["run_id"] == "stable_run"
    assert metadata["ended_at"] is not None


def test_run_store_avoids_overwriting_existing_run_directory(tmp_path) -> None:
    first = RunStore(root=tmp_path, experiment_name="exp", run_id="same")
    second = RunStore(root=tmp_path, experiment_name="exp", run_id="same")

    first.open()
    first.close()
    second.open()
    second.close()

    assert first.run_path.name == "same"
    assert second.run_path.name == "same_01"


def test_data_point_and_complex_specs_are_persisted(tmp_path) -> None:
    store = RunStore(root=tmp_path, experiment_name="storage", run_id="complex")
    store.open()
    store.handle_event(MeasurementStarted(point_id="p000001", coords={"mw_freq_hz": 2.87e9}))
    store.handle_event(
        DataPoint(
            point_id="p000001",
            coords={"mw_freq_hz": 2.87e9},
            data={
                "counts_mean": 1234.5,
                "photon_bins": [1, 2, 3],
                "analog_trace": [[0.1, 0.2], [0.3, 0.4]],
                "snapshot": {"mw": "on"},
            },
            metadata={"average_index": 0},
        )
    )
    store.handle_event(MeasurementCompleted(point_id="p000001", status="ok", coords={"mw_freq_hz": 2.87e9}))
    store.close()

    events = _jsonl(store.run_path / "events.jsonl")
    data = _jsonl(store.run_path / "data.jsonl")
    points = _jsonl(store.run_path / "points.jsonl")
    metadata = json.loads((store.run_path / "metadata.json").read_text(encoding="utf-8"))

    assert [event["type"] for event in events] == ["MeasurementStarted", "DataPoint", "MeasurementCompleted"]
    assert data[0]["data"]["photon_bins"] == [1, 2, 3]
    assert data[0]["data_specs"]["counts_mean"]["kind"] == "scalar"
    assert data[0]["data_specs"]["photon_bins"]["kind"] == "vector"
    assert data[0]["data_specs"]["analog_trace"]["kind"] == "matrix"
    assert points[-1]["status"] == "ok"
    assert points[-1]["data_keys"] == ["analog_trace", "counts_mean", "photon_bins", "snapshot"]
    assert metadata["point_count"] == 1
    assert metadata["completed_point_count"] == 1
    assert sorted(item["key"] for item in metadata["data_keys"]) == [
        "analog_trace",
        "counts_mean",
        "photon_bins",
        "snapshot",
    ]


def test_failure_preserves_events_data_and_partial_point(tmp_path) -> None:
    store = RunStore(root=tmp_path, experiment_name="failure", run_id="failed_run")
    store.open()
    store.handle_event(MeasurementStarted(point_id="p000001", coords={"tau_s": 1e-7}))
    store.handle_event(DataPoint(point_id="p000001", coords={"tau_s": 1e-7}, data={"counts": 9}))
    store.handle_event(ErrorRaised(error_type="RuntimeError", message="boom", step_id="read"))
    store.close(status="failed")

    metadata = json.loads((store.run_path / "metadata.json").read_text(encoding="utf-8"))
    events = _jsonl(store.run_path / "events.jsonl")
    data = _jsonl(store.run_path / "data.jsonl")
    points = _jsonl(store.run_path / "points.jsonl")

    assert metadata["status"] == "failed"
    assert metadata["error_count"] == 1
    assert any(event["type"] == "ErrorRaised" and event["message"] == "boom" for event in events)
    assert data[0]["data"] == {"counts": 9}
    assert points[-1]["status"] == "partial"


def test_log_messages_append_to_logs_txt(tmp_path) -> None:
    store = RunStore(root=tmp_path, experiment_name="logs", run_id="logs")
    store.open()
    store.handle_event(LogMessage(level="warning", message="hello"))
    store.close()

    assert "hello" in (store.run_path / "logs.txt").read_text(encoding="utf-8")


def test_sqlite_index_contains_run_points_and_data_keys(tmp_path) -> None:
    store = RunStore(root=tmp_path, experiment_name="index", run_id="indexed")
    store.open()
    store.handle_event(MeasurementStarted(point_id="p000001", coords={"freq": 1.0}))
    store.handle_event(DataPoint(point_id="p000001", coords={"freq": 1.0}, data={"counts": 1.5, "bins": [1, 2]}))
    store.handle_event(MeasurementCompleted(point_id="p000001", status="ok", coords={"freq": 1.0}))
    store.close()

    with sqlite3.connect(tmp_path / "run_index.sqlite") as conn:
        run = conn.execute("SELECT run_id, status FROM runs WHERE run_id = ?", ("indexed",)).fetchone()
        point = conn.execute("SELECT point_id, status, coords_json FROM points WHERE run_id = ?", ("indexed",)).fetchone()
        data_keys = conn.execute("SELECT key, kind, shape_json FROM data_keys WHERE run_id = ? ORDER BY key", ("indexed",)).fetchall()

    assert run == ("indexed", "completed")
    assert point[0:2] == ("p000001", "ok")
    assert json.loads(point[2]) == {"freq": 1.0}
    assert data_keys == [("bins", "vector", "[2]"), ("counts", "scalar", "[]")]
