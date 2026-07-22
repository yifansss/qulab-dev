import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qulab.gui.qt_compat import QT_AVAILABLE, QtCore, QtWidgets


@pytest.mark.skipif(not QT_AVAILABLE, reason="optional Qt binding is not installed")
def test_live_widget_checkbox_refresh_and_rendered_canvas_state(tmp_path):
    from qulab.core import DataPoint, DerivedData
    from qulab.gui.controller import OperatorController
    from qulab.gui.pyqt_views import PyQtOperatorWindow

    assert QtWidgets is not None and QtCore is not None
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    config = Path(__file__).parents[2] / "configs" / "experiments" / "live_view_showcase.yaml"
    window = PyQtOperatorWindow(OperatorController(tmp_path), config)
    assert window._prepare()
    assert window.thread() == app.thread()
    rows = {window.live_source_table.item(row, 1).text(): row for row in range(window.live_source_table.rowCount())}
    raw_row = rows["source_value"]
    window.live_source_table.item(raw_row, 0).setCheckState(QtCore.Qt.CheckState.Checked)
    window.live_plot_type.setCurrentText("Line")
    window.controller.handle_live_event(DataPoint(point_id="p1", coords={"frequency_hz": 1, "power_dbm": -1}, data={"source_value": 2}))
    window.controller.handle_live_event(DerivedData(point_id="p1", coords={"frequency_hz": 1, "power_dbm": -1},
                                                    data={"saved_scale": 4}, source_module="saved_scale", show=True))
    window._refresh_live_models()
    assert window.plot.mode == "line" and window.plot.line_series
    checked = window.live_source_table.item(raw_row, 0).checkState()
    window._refresh_live_models()
    assert window.live_source_table.item(raw_row, 0).checkState() == checked
    saved_row = rows["saved_scale"]
    window.live_source_table.item(saved_row, 0).setCheckState(QtCore.Qt.CheckState.Unchecked)
    window.live_plot_type.setCurrentText("Heatmap")
    window._render_live_plot()
    assert window.plot.mode == "heatmap" and window.plot.heatmap_values.size
    window.close()


def test_qt_import_contract_is_explicit():
    assert isinstance(QT_AVAILABLE, bool)
