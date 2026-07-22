from pathlib import Path

from qulab.core import DataPoint, EventBus, RunCompleted, RunStarted
from qulab.storage import Fidelity, HistoricalRunWorkspace, RunStore


def _run(tmp_path: Path) -> Path:
    config = {"name": "history", "resources": {}, "procedure": [], "safety": {"allow_output": True}}
    store = RunStore(tmp_path / "runs", "history", config=config, resolved_config=config)
    store.open()
    store.handle_event(RunStarted(run_id=store.run_id, procedure_name="history"))
    store.handle_event(DataPoint(point_id="p1", coords={"x": 1}, data={"counts": 2}))
    store.handle_event(RunCompleted(run_id=store.run_id))
    store.close()
    return store.run_path


def test_workspace_fidelity_streaming_and_replay(tmp_path: Path) -> None:
    workspace = HistoricalRunWorkspace.open(_run(tmp_path))
    assert workspace.status("config").fidelity is Fidelity.RECORDED
    assert workspace.status("resources").fidelity is Fidelity.UNAVAILABLE
    assert workspace.timeline_summary() == {"RunStarted": 1, "DataPoint": 1, "RunCompleted": 1}
    received = []
    replay = workspace.replay(received.append)
    assert replay.play("max") == 3
    assert [event.type for event in received] == ["RunStarted", "DataPoint", "RunCompleted"]
    replay.seek(2)
    assert replay.index == 2


def test_malformed_event_is_isolated(tmp_path: Path) -> None:
    run = _run(tmp_path)
    with (run / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("not-json\n")
        handle.write('{"type":"LogMessage","message":"after"}\n')
    workspace = HistoricalRunWorkspace.open(run)
    records = list(workspace.iter_event_records())
    assert records[-2].error is not None
    assert records[-1].event is not None
    assert workspace.timeline_summary()["malformed"] == 1


def test_clone_is_safe_valid_and_does_not_modify_source(tmp_path: Path) -> None:
    run = _run(tmp_path)
    source_before = (run / "config.yaml").read_bytes()
    workspace = HistoricalRunWorkspace.open(run)
    result = workspace.clone_as_draft(tmp_path / "project" / "clone.yaml")
    assert result.ok
    assert result.candidate_config["safety"]["allow_output"] is False
    assert result.candidate_config["provenance"]["source_run_id"] == workspace.run_id
    assert (run / "config.yaml").read_bytes() == source_before


def test_artifact_path_traversal_is_rejected(tmp_path: Path) -> None:
    run = _run(tmp_path)
    workspace = HistoricalRunWorkspace.open(run)
    try:
        workspace.resolve_artifact("../escape")
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal was accepted")
