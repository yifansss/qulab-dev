import json

from qulab.core import AnalysisStatus, DerivedData


def test_analysis_events_are_public_and_json_safe():
    derived = DerivedData(point_id="p1", data={"y": 2}, source_module="m", output_keys=["y"])
    status = AnalysisStatus(module="m", state="success", point_id="p1", latency_s=.01)
    json.dumps(derived.to_dict())
    json.dumps(status.to_dict())
    assert derived.type == "DerivedData"
    assert status.type == "AnalysisStatus"
