from qulab.config import parse_experiment_config
from qulab.core import DataPoint, DerivedData
from qulab.gui import OperatorController


def test_controller_shared_live_handler_without_qt(tmp_path):
    controller = OperatorController(tmp_path)
    controller.config = {"name": "live", "resources": {}, "procedure": [{"call": "x.y", "save_as": "raw"}]}
    controller.parsed = parse_experiment_config(controller.config)
    controller.reset_live_state(max_points=4)
    controller.handle_live_event(DataPoint(point_id="p1", coords={"x": 1}, data={"raw": 2}))
    controller.handle_live_event(DerivedData(point_id="p1", coords={"x": 1}, data={"derived": 4}, source_module="m"))
    assert [item.key for item in controller.get_live_data_catalog().list_raw()] == ["raw"]
    assert controller.live_buffer.points()[0]["data"] == {"raw": 2, "derived": 4}
