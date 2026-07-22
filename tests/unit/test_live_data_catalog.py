from qulab.analysis import AnalysisExecutionPlan, AnalysisLiveConfig, AnalysisSourceIdentity, ComputeModulePlan
from qulab.core import DataPoint, DerivedData
from qulab.gui import LiveDataCatalog, LivePointBuffer


def plan(show=True, save=False):
    module = ComputeModulePlan("m", "x", "M", "class", True, True, False, show, save, "warn", ("raw",),
                               ("out",), ("analysis.out",), {}, AnalysisSourceIdentity("x", None, None, "1"), "analysis")
    return AnalysisExecutionPlan(AnalysisLiveConfig(enabled=True), (module,))


def test_declared_waiting_to_active_and_badges():
    catalog = LiveDataCatalog(); catalog.declare_from_config(["raw"], plan(), ["tau"])
    assert catalog.get("analysis.out").status == "waiting"
    assert not catalog.get("analysis.out").saved and catalog.get("analysis.out").visible_default
    catalog.handle_event(DerivedData(point_id="p1", coords={"tau": 1}, data={"analysis.out": 2},
                                     source_module="m", save=False, show=True))
    assert catalog.get("analysis.out").status == "active"
    assert catalog.get("analysis.out").data_kind == "scalar"


def test_raw_derived_point_merge_and_bounded_history():
    buffer = LivePointBuffer(max_points=2)
    buffer.handle_event(DerivedData(point_id="p1", coords={"x": 1}, data={"d": 2}))
    buffer.handle_event(DataPoint(point_id="p1", coords={"x": 1}, data={"r": 1}))
    assert buffer.points()[0]["data"] == {"d": 2, "r": 1}
    buffer.handle_event(DataPoint(point_id="p2", coords={"x": 2}, data={"r": 2}))
    buffer.handle_event(DataPoint(point_id="p3", coords={"x": 3}, data={"r": 3}))
    assert [row["point_id"] for row in buffer.points()] == ["p2", "p3"]


def test_collision_marks_raw_error_without_reclassification():
    catalog = LiveDataCatalog(); catalog.declare_from_config(["same"])
    catalog.handle_event(DerivedData(point_id="p", data={"same": 1}))
    assert catalog.get("same").source_kind == "raw"
    assert catalog.get("same").status == "error"


def test_numeric_arrays_are_plot_data_but_text_is_diagnostic_only():
    catalog = LiveDataCatalog()
    catalog.handle_event(DataPoint(point_id="p", data={"trace": [1, 2], "matrix": [[1, 2]], "label": "ok"}))
    assert catalog.get("trace").dims == ("sample_index",)
    assert catalog.get("matrix").dims == ("channel", "sample_index")
    assert catalog.get("label").status == "error"
    catalog.handle_event(DataPoint(point_id="bad", data={"ragged": [[1], [2, 3]]}))
    assert catalog.get("ragged").status == "error"


def test_buffer_selectors_sorting_and_clear_are_view_only_contracts():
    buffer = LivePointBuffer()
    for point_id, x, group in [("a", 2, "keep"), ("b", 1, "keep"), ("c", 0, "skip")]:
        buffer.handle_event(DataPoint(point_id=point_id, coords={"x": x, "group": group}, data={"v": x}))
    line = buffer.line("v", "x", {"group": "keep"})
    assert line.x.tolist() == [1, 2]
    buffer.clear()
    assert buffer.points() == ()
