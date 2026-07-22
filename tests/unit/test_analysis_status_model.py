from qulab.core import AnalysisStatus
from qulab.gui import AnalysisStatusModel


def test_status_tracks_latency_error_and_queue_placeholder():
    model = AnalysisStatusModel()
    model.handle_event(AnalysisStatus(module="m", state="success", point_id="p1", latency_s=.02, queue_depth=3))
    status = model.list()[0]
    assert status.last_point == "p1" and status.last_latency_s == .02 and status.queue_depth == 3
    model.handle_event(AnalysisStatus(module="m", state="warning", message="bad", error_type="ValueError"))
    assert model.list()[0].error_type == "ValueError"
