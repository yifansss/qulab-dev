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


def test_overlay_requires_compatible_dims_and_units():
    catalog = LiveDataCatalog(); buffer = LivePointBuffer()
    catalog.declare(LiveDataKeySpec("a", "raw", "scalar", "V", ("x",), status="active"))
    catalog.declare(LiveDataKeySpec("b", "derived", "scalar", "Hz", ("x",), status="active"))
    with pytest.raises(ValueError):
        LivePlotModel(catalog, buffer).select(("a", "b"))
