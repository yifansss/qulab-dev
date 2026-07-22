import numpy as np
import pytest

from qulab.core import DataPoint
from qulab.gui import LiveDataCatalog, LiveDataKeySpec, LivePlotModel, LivePointBuffer


def test_line_heatmap_and_trace_extraction():
    catalog = LiveDataCatalog(); buffer = LivePointBuffer()
    for x, y, value in [(0, 0, 1), (1, 0, 2), (0, 1, 3), (1, 1, 4)]:
        event = DataPoint(point_id=f"{x}{y}", coords={"x": x, "y": y}, data={"z": value, "trace": [value, value + 1]})
        catalog.handle_event(event); buffer.handle_event(event)
    model = LivePlotModel(catalog, buffer)
    heat = model.get_plot_data(model.select(("z",), plot_type="heatmap", x_dim="x", y_dim="y"))
    assert heat.values.tolist() == [[1, 2], [3, 4]]
    line = buffer.line("z", "x"); assert len(line.x) == 4
    trace = model.get_plot_data(model.select(("trace",), point_id="11"))
    assert trace.values.tolist() == [4, 5]
    assert trace.time_dim == "sample_index"


def test_overlay_requires_compatible_dims_and_units():
    catalog = LiveDataCatalog(); buffer = LivePointBuffer()
    catalog.declare(LiveDataKeySpec("a", "raw", "scalar", "V", ("x",), status="active"))
    catalog.declare(LiveDataKeySpec("b", "derived", "scalar", "Hz", ("x",), status="active"))
    with pytest.raises(ValueError):
        LivePlotModel(catalog, buffer).select(("a", "b"))


def test_empty_selection_remains_empty_and_zero_dim_scalar_uses_point_index():
    catalog = LiveDataCatalog(); buffer = LivePointBuffer()
    catalog.declare(LiveDataKeySpec("visible", "derived", "scalar", visible_default=True, status="waiting"))
    model = LivePlotModel(catalog, buffer)
    model.initialize_defaults()
    assert model.selection.keys == ("visible",)
    model.select(())
    model.initialize_defaults()
    assert model.selection.keys == ()
    buffer.handle_event(DataPoint(point_id="p", data={"visible": 2}))
    line, = model.get_plot_data(model.select(("visible",), plot_type="line"))
    assert line.x_dim == "point_index" and line.y.tolist() == [2]
