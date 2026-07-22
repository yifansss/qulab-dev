import json

from qulab.core import AnalysisStatus, DerivedData, MeasurementStarted
from qulab.storage import RunStore


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_saved_derived_has_provenance_and_live_only_never_persists(tmp_path):
    store = RunStore(tmp_path, "analysis", run_id="r", backends="csv")
    store.open()
    store.handle_event(MeasurementStarted(point_id="p1", coords={"x": 1}))
    store.handle_event(DerivedData(point_id="p1", coords={"x": 1}, data={"saved": 2},
                                   source_module="m", module_version="1", input_keys=["raw"],
                                   output_keys=["saved"], units={"saved": "V"}, save=True))
    store.handle_event(DerivedData(point_id="p1", data={"preview": 3}, source_module="m", save=False, show=True))
    store.handle_event(AnalysisStatus(module="m", state="warning", message="bad"))
    store.close()
    assert [row["kind"] for row in lines(store.run_path / "data.jsonl")] == ["derived_data"]
    assert not any(row.get("data", {}).get("preview") for row in lines(store.run_path / "events.jsonl"))
    manifest = json.loads((store.run_path / "dataset_manifest.json").read_text())
    assert manifest["data_vars"]["saved"]["source_kind"] == "derived"
    assert manifest["data_vars"]["saved"]["source_module"] == "m"
    metadata = json.loads((store.run_path / "metadata.json").read_text())
    assert metadata["analysis_error_count"] == 1
    assert next(x for x in metadata["data_keys"] if x["key"] == "saved")["source_kind"] == "derived"
