"""Shared scientific Qt canvas for live and stored-data views."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
import numpy as np


@dataclass(frozen=True)
class LineSeriesView:
    label: str
    x: np.ndarray
    y: np.ndarray


def _rows(series: Iterable[LineSeriesView | tuple[str, Any, Any]]) -> list[LineSeriesView]:
    return [v if isinstance(v, LineSeriesView) else LineSeriesView(v[0], np.asarray(v[1]), np.asarray(v[2])) for v in series]


def scientific_plot_canvas_class(QtWidgets: Any, QtCore: Any, QtGui: Any) -> type:
    """Select pyqtgraph, then Matplotlib, then a dependency-free Qt painter."""
    return _pyqtgraph_class(QtWidgets) or _matplotlib_class(QtWidgets) or _native_class(QtWidgets, QtCore, QtGui)


def _pyqtgraph_class(QtWidgets: Any) -> type | None:
    try:
        import pyqtgraph as pg
    except Exception:
        return None

    class Canvas(QtWidgets.QWidget):
        backend_name = "pyqtgraph"
        def __init__(self) -> None:
            super().__init__(); self.mode = "message"; self.line_series = []; self.heatmap_values = np.empty((0, 0)); self.plot = pg.PlotWidget(); layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0); layout.addWidget(self.plot); self.plot.showGrid(x=True, y=True, alpha=.25)
        def set_lines(self, title: str, series: Iterable) -> None:
            values = _rows(series); self.mode = "line"; self.line_series = values; self.plot.clear(); self.plot.setTitle(title)
            if len(values) > 1: self.plot.addLegend()
            for i, row in enumerate(values):
                self.plot.plot(np.asarray(row.x, dtype=float), np.asarray(row.y, dtype=float),
                               pen=pg.mkPen(pg.intColor(i), width=2), symbol="o", name=row.label)
        def set_line(self, title: str, x: Any, y: Any) -> None: self.set_lines(title, [(title, x, y)])
        def set_heatmap(self, title: str, x: Any, y: Any, values: Any) -> None:
            self.mode = "heatmap"; self.heatmap_values = np.asarray(values, dtype=float); self.plot.clear(); self.plot.setTitle(title); self.plot.addItem(pg.ImageItem(self.heatmap_values.T)); self.plot.autoRange()
        def set_message(self, title: str) -> None:
            self.mode = "message"; self.plot.clear(); self.plot.setTitle(title); label = pg.TextItem(title, anchor=(.5, .5), color="#667085"); self.plot.addItem(label)
        def clear(self) -> None: self.set_message("No live data selected")
        def reset_view(self) -> None: self.plot.autoRange()
    return Canvas


def _matplotlib_class(QtWidgets: Any) -> type | None:
    try:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
    except Exception:
        return None

    class Canvas(FigureCanvasQTAgg):
        backend_name = "matplotlib"
        def __init__(self) -> None:
            self.mode = "message"; self.line_series = []; self.heatmap_values = np.empty((0, 0)); self.figure = Figure(figsize=(6, 4), dpi=100); self.axes = self.figure.add_subplot(111); self._colorbar = None
            super().__init__(self.figure); self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        def _reset(self) -> None:
            if self._colorbar is not None: self._colorbar.remove(); self._colorbar = None
            self.axes.clear()
        def set_lines(self, title: str, series: Iterable) -> None:
            values = _rows(series); self.mode = "line"; self.line_series = values; self._reset()
            for row in values: self.axes.plot(row.x, row.y, marker="o", linewidth=1.5, label=row.label)
            if len(values) > 1: self.axes.legend()
            self.axes.set_title(title); self.axes.grid(True, color="#e5e7eb"); self.figure.tight_layout(); self.draw_idle()
        def set_line(self, title: str, x: Any, y: Any) -> None: self.set_lines(title, [(title, x, y)])
        def set_heatmap(self, title: str, x: Any, y: Any, values: Any) -> None:
            self.mode = "heatmap"; self.heatmap_values = np.asarray(values, dtype=float); self._reset(); image = self.axes.imshow(self.heatmap_values, aspect="auto", origin="lower", interpolation="nearest")
            self.axes.set_title(title); self._colorbar = self.figure.colorbar(image, ax=self.axes); self.figure.tight_layout(); self.draw_idle()
        def set_message(self, title: str) -> None:
            self.mode = "message"; self._reset(); self.axes.text(.5, .5, title, ha="center", va="center", transform=self.axes.transAxes); self.axes.set_axis_off(); self.draw_idle()
        def clear(self) -> None: self.set_message("No live data selected")
        def reset_view(self) -> None: self.axes.relim(); self.axes.autoscale_view(); self.draw_idle()
    return Canvas


def _native_class(QtWidgets: Any, QtCore: Any, QtGui: Any) -> type:
    colors = ("#2563eb", "#dc2626", "#16a34a", "#9333ea")
    class Canvas(QtWidgets.QWidget):
        backend_name = "native-qt"
        def __init__(self) -> None:
            super().__init__(); self.mode = "message"; self.title = "No live data selected"; self.series = []; self.line_series = self.series; self.values = np.empty((0, 0)); self.heatmap_values = self.values; self.setMinimumSize(420, 280)
        def set_lines(self, title: str, series: Iterable) -> None: self.mode = "line"; self.title = title; self.series = _rows(series); self.line_series = self.series; self.update()
        def set_line(self, title: str, x: Any, y: Any) -> None: self.set_lines(title, [(title, x, y)])
        def set_heatmap(self, title: str, x: Any, y: Any, values: Any) -> None: self.mode = "heatmap"; self.title = title; self.values = np.asarray(values, dtype=float); self.heatmap_values = self.values; self.update()
        def set_message(self, title: str) -> None: self.mode = "message"; self.title = title; self.update()
        def clear(self) -> None: self.set_message("No live data selected")
        def reset_view(self) -> None: self.update()
        def paintEvent(self, event: Any) -> None:  # noqa: N802
            painter = QtGui.QPainter(self); painter.fillRect(self.rect(), QtGui.QColor("white")); painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.setPen(QtGui.QColor("#202124")); painter.drawText(16, 24, self.title); area = self.rect().adjusted(50, 42, -28, -38); painter.drawRect(area)
            if self.mode == "message": painter.drawText(area, QtCore.Qt.AlignmentFlag.AlignCenter, self.title)
            elif self.mode == "line": self._paint_lines(painter, area)
            elif self.mode == "heatmap": self._paint_heatmap(painter, area)
        def _paint_lines(self, painter: Any, area: Any) -> None:
            pairs = [(float(x), float(y)) for row in self.series for x, y in zip(row.x, row.y) if np.isfinite(x) and np.isfinite(y)]
            if not pairs: return
            x0, x1 = _range([p[0] for p in pairs]); y0, y1 = _range([p[1] for p in pairs])
            for index, row in enumerate(self.series):
                points = [QtCore.QPointF(area.left()+(float(x)-x0)/(x1-x0)*area.width(), area.bottom()-(float(y)-y0)/(y1-y0)*area.height()) for x, y in zip(row.x, row.y) if np.isfinite(x) and np.isfinite(y)]
                painter.setPen(QtGui.QPen(QtGui.QColor(colors[index % len(colors)]), 2))
                for left, right in zip(points, points[1:]): painter.drawLine(left, right)
                painter.drawText(area.left()+8, area.top()+18+index*16, row.label)
        def _paint_heatmap(self, painter: Any, area: Any) -> None:
            finite = self.values[np.isfinite(self.values)]
            if not finite.size: return
            low, high = float(finite.min()), float(finite.max()); high = high if high != low else low+1
            rows, cols = self.values.shape; width, height = area.width()/max(cols, 1), area.height()/max(rows, 1)
            for row in range(rows):
                for col in range(cols):
                    value = self.values[row, col]; rect = QtCore.QRectF(area.left()+col*width, area.bottom()-(row+1)*height, width+.5, height+.5)
                    if np.isfinite(value):
                        ratio = float((value-low)/(high-low)); painter.fillRect(rect, QtGui.QColor(int(40+210*ratio), 80, int(230-180*ratio)))
                    else:
                        painter.fillRect(rect, QtGui.QColor("#eeeeee")); painter.setPen(QtGui.QColor("#aaaaaa")); painter.drawLine(rect.topLeft(), rect.bottomRight())
    return Canvas


def _range(values: Any) -> tuple[float, float]:
    array = np.asarray(values, dtype=float); finite = array[np.isfinite(array)]
    if not finite.size: return 0., 1.
    low, high = float(finite.min()), float(finite.max()); return low, high if high != low else low+1
