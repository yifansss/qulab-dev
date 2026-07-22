"""Optional read-only PyQt/PySide data viewer entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

from qulab.storage import DatasetModel, RunReader, SliceController
from qulab.storage.array_backend import DataArray
from qulab.gui.plot_canvas import scientific_plot_canvas_class


def main(argv: list[str] | None = None) -> int:
    """Open a run folder in a small read-only advanced data viewer."""

    argv = list(sys.argv[1:] if argv is None else argv)
    run_path = Path(argv[0]) if argv else Path("runs")
    backend = argv[1] if len(argv) > 1 else "auto"
    try:
        from qulab.gui.qt_compat import QT_API, QtCore, QtGui, QtWidgets
    except Exception:
        QT_API = None
        QtCore = None
        QtGui = None
        QtWidgets = None
    if QtWidgets is None or QtCore is None or QtGui is None:
        if not argv:
            print("Qt is not available; pass a run folder to use headless RunReader output.")
            return 2
        print("Qt is not available; use RunReader/SliceController for headless data access.")
        reader = RunReader(run_path, backend=backend)  # type: ignore[arg-type]
        print(f"Opened {run_path} with backend={reader.backend_name or 'jsonl'} keys={reader.list_data_keys()}")
        return 0

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = create_data_viewer_panel(QtWidgets, QtCore, QtGui, run_path, backend, QT_API)
    from qulab.gui.theme import classic_qt_stylesheet

    window.setStyleSheet(classic_qt_stylesheet())
    window.show()
    return int(app.exec())


def create_data_viewer_panel(
    QtWidgets: Any,
    QtCore: Any,
    QtGui: Any,
    run_path: Path,
    backend: str = "auto",
    qt_api: str | None = None,
) -> Any:
    """Create the reusable read-only data viewer panel.

    This is used both by the standalone viewer app and by the Operator Console.
    """

    PyqtgraphCanvas = _pyqtgraph_canvas_class(QtWidgets)
    MatplotlibCanvas = None if PyqtgraphCanvas is not None else _matplotlib_canvas_class(QtWidgets)

    class PlotCanvas(MatplotlibCanvas or QtWidgets.QWidget):  # type: ignore[misc, valid-type]
        if MatplotlibCanvas is not None:

            def __init__(self) -> None:
                super().__init__()
                self.figure = self.figure
                self.axes = self.figure.add_subplot(111)
                self.setMinimumSize(520, 340)

            def set_line(self, title: str, x: np.ndarray, y: np.ndarray) -> None:
                self.axes.clear()
                self.axes.plot(np.asarray(x, dtype=float), np.asarray(y, dtype=float), color="#2563eb", linewidth=1.6)
                self.axes.scatter(np.asarray(x, dtype=float), np.asarray(y, dtype=float), color="#2563eb", s=18)
                self.axes.set_title(title)
                self.axes.grid(True, color="#e5e7eb")
                self.figure.tight_layout()
                self.draw_idle()

            def set_heatmap(self, title: str, x: np.ndarray, y: np.ndarray, values: np.ndarray) -> None:
                self.axes.clear()
                image = self.axes.imshow(np.asarray(values, dtype=float), aspect="auto", origin="lower", interpolation="nearest")
                self.axes.set_title(title)
                self.axes.set_xlabel("x index" if len(x) == 0 else f"x: {x[0]:.4g} .. {x[-1]:.4g}")
                self.axes.set_ylabel("y index" if len(y) == 0 else f"y: {y[0]:.4g} .. {y[-1]:.4g}")
                if not hasattr(self, "_colorbar") or self._colorbar is None:
                    self._colorbar = self.figure.colorbar(image, ax=self.axes)
                else:
                    self._colorbar.update_normal(image)
                self.figure.tight_layout()
                self.draw_idle()

            def set_message(self, title: str) -> None:
                self.axes.clear()
                self.axes.text(0.5, 0.5, title, ha="center", va="center", transform=self.axes.transAxes)
                self.axes.set_axis_off()
                self.figure.tight_layout()
                self.draw_idle()

        else:

            def __init__(self) -> None:
                super().__init__()
                self.mode = "empty"
                self.title = ""
                self.x = np.array([])
                self.y = np.array([])
                self.values = np.empty((0, 0))
                self.setMinimumSize(520, 340)

            def set_line(self, title: str, x: np.ndarray, y: np.ndarray) -> None:
                self.mode = "line"
                self.title = title
                self.x = np.asarray(x, dtype=float)
                self.y = np.asarray(y, dtype=float)
                self.update()

            def set_heatmap(self, title: str, x: np.ndarray, y: np.ndarray, values: np.ndarray) -> None:
                self.mode = "heatmap"
                self.title = title
                self.x = np.asarray(x, dtype=float)
                self.y = np.asarray(y, dtype=float)
                self.values = np.asarray(values, dtype=float)
                self.update()

            def set_message(self, title: str) -> None:
                self.mode = "message"
                self.title = title
                self.update()

            def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
                painter = QtGui.QPainter(self)
                painter.fillRect(self.rect(), QtGui.QColor("#ffffff"))
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
                painter.setPen(QtGui.QColor("#202124"))
                painter.drawText(16, 24, self.title)
                plot = self.rect().adjusted(48, 44, -22, -38)
                painter.setPen(QtGui.QColor("#d0d5dd"))
                painter.drawRect(plot)
                if self.mode == "line":
                    self._paint_line(painter, plot)
                elif self.mode == "heatmap":
                    self._paint_heatmap(painter, plot)
                elif self.mode == "message":
                    painter.setPen(QtGui.QColor("#667085"))
                    painter.drawText(plot, QtCore.Qt.AlignmentFlag.AlignCenter, self.title)

            def _paint_line(self, painter: Any, plot: Any) -> None:
                if len(self.x) == 0 or len(self.y) == 0:
                    return
                x_min, x_max = _range(self.x)
                y_min, y_max = _range(self.y)
                points = []
                for x_value, y_value in zip(self.x, self.y):
                    px = plot.left() + (x_value - x_min) / (x_max - x_min) * plot.width()
                    py = plot.bottom() - (y_value - y_min) / (y_max - y_min) * plot.height()
                    points.append(QtCore.QPointF(float(px), float(py)))
                painter.setPen(QtGui.QPen(QtGui.QColor("#2563eb"), 2))
                for left, right in zip(points, points[1:]):
                    painter.drawLine(left, right)
                painter.setBrush(QtGui.QColor("#2563eb"))
                for point in points:
                    painter.drawEllipse(point, 3, 3)
                self._paint_axis_labels(painter, plot, x_min, x_max, y_min, y_max)

            def _paint_heatmap(self, painter: Any, plot: Any) -> None:
                if self.values.size == 0:
                    return
                values = np.asarray(self.values, dtype=float)
                finite = values[np.isfinite(values)]
                if finite.size == 0:
                    return
                v_min = float(np.min(finite))
                v_max = float(np.max(finite))
                if v_min == v_max:
                    v_max = v_min + 1.0
                rows, cols = values.shape
                cell_w = plot.width() / max(cols, 1)
                cell_h = plot.height() / max(rows, 1)
                for row in range(rows):
                    for col in range(cols):
                        value = values[row, col]
                        ratio = 0.0 if not np.isfinite(value) else float((value - v_min) / (v_max - v_min))
                        painter.fillRect(
                            QtCore.QRectF(
                                plot.left() + col * cell_w, plot.top() + row * cell_h, cell_w + 0.5, cell_h + 0.5
                            ),
                            _color_ramp(QtGui, ratio),
                        )
                painter.setPen(QtGui.QColor("#344054"))
                painter.drawText(plot.left(), plot.bottom() + 22, f"min {v_min:.4g}   max {v_max:.4g}")

            def _paint_axis_labels(
                self, painter: Any, plot: Any, x_min: float, x_max: float, y_min: float, y_max: float
            ) -> None:
                painter.setPen(QtGui.QColor("#344054"))
                painter.drawText(plot.left(), plot.bottom() + 22, f"{x_min:.4g}")
                painter.drawText(plot.right() - 72, plot.bottom() + 22, f"{x_max:.4g}")
                painter.drawText(6, plot.top() + 8, f"{y_max:.4g}")
                painter.drawText(6, plot.bottom(), f"{y_min:.4g}")

    if PyqtgraphCanvas is not None:
        PlotCanvas = PyqtgraphCanvas
    PlotCanvas = scientific_plot_canvas_class(QtWidgets, QtCore, QtGui)

    class ViewerWindow(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.run_path = _initial_run_path(run_path)
            self.run_root = self.run_path.parent if self.run_path.joinpath("dataset_manifest.json").exists() else run_path
            self.run_paths: list[Path] = []
            self.run_combo = QtWidgets.QComboBox()
            self.backend_combo = QtWidgets.QComboBox()
            self.plot_type_combo = QtWidgets.QComboBox()
            self.key_combo = QtWidgets.QComboBox()
            self.x_combo = QtWidgets.QComboBox()
            self.y_combo = QtWidgets.QComboBox()
            self.selector_form = QtWidgets.QFormLayout()
            self.selector_widgets: dict[str, Any] = {}
            self.canvas = PlotCanvas()
            self.table = QtWidgets.QTableWidget()
            self.status = QtWidgets.QLabel()
            self.reader: RunReader | None = None
            self.model: DatasetModel | None = None
            self.controller: SliceController | None = None
            self.current_data: DataArray | None = None
            self._build()
            self._refresh_run_choices()
            self._open_reader(backend)

        def _build(self) -> None:
            self.setWindowTitle(f"Qulab Data Viewer ({qt_api})")
            root = QtWidgets.QHBoxLayout(self)
            controls = QtWidgets.QWidget()
            controls.setMaximumWidth(330)
            control_layout = QtWidgets.QVBoxLayout(controls)
            control_layout.addWidget(QtWidgets.QLabel("Run folder / 运行目录"))
            self.run_combo.currentIndexChanged.connect(self._run_choice_changed)
            control_layout.addWidget(self.run_combo)
            browse_button = QtWidgets.QPushButton("Browse... / 浏览")
            browse_button.clicked.connect(self._browse_run_folder)
            control_layout.addWidget(browse_button)

            self.backend_combo.addItems(["auto", "csv", "zarr"])
            self.backend_combo.setCurrentText(backend)
            self.backend_combo.currentTextChanged.connect(self._open_reader)
            control_layout.addWidget(QtWidgets.QLabel("Backend / 后端"))
            control_layout.addWidget(self.backend_combo)

            self.plot_type_combo.currentTextChanged.connect(self._plot_type_changed)
            control_layout.addWidget(QtWidgets.QLabel("Plot type / 图类型"))
            control_layout.addWidget(self.plot_type_combo)

            self.key_combo.currentTextChanged.connect(self._load_key)
            control_layout.addWidget(QtWidgets.QLabel("Data key / 数据键"))
            control_layout.addWidget(self.key_combo)

            self.x_combo.currentTextChanged.connect(lambda _value: self._axes_changed())
            self.y_combo.currentTextChanged.connect(lambda _value: self._axes_changed())
            control_layout.addWidget(QtWidgets.QLabel("X dimension / X 维度"))
            control_layout.addWidget(self.x_combo)
            control_layout.addWidget(QtWidgets.QLabel("Y dimension / Y 维度"))
            control_layout.addWidget(self.y_combo)
            control_layout.addLayout(self.selector_form)

            render_button = QtWidgets.QPushButton("Render / 绘制")
            render_button.clicked.connect(self._render)
            control_layout.addWidget(render_button)
            control_layout.addStretch(1)
            control_layout.addWidget(self.status)

            tabs = QtWidgets.QTabWidget()
            tabs.addTab(self.canvas, "Plot / 图")
            tabs.addTab(self.table, "Table / 表")
            root.addWidget(controls)
            root.addWidget(tabs, 1)
            self.resize(1040, 620)

        def open_run(self, run_path: Path | str, backend: str | None = None) -> None:
            """Load a run folder into this panel without creating a new window."""

            self.run_path = Path(run_path)
            self.run_root = self.run_path.parent if self.run_path.joinpath("dataset_manifest.json").exists() else self.run_path
            self._refresh_run_choices()
            if backend is not None:
                self.backend_combo.setCurrentText(backend)
            self._open_reader(self.backend_combo.currentText())

        def _open_reader(self, selected_backend: str) -> None:
            try:
                self.reader = RunReader(self.run_path, backend=selected_backend)  # type: ignore[arg-type]
                self.model = DatasetModel(self.reader)
                self.controller = SliceController(self.model)
                self.key_combo.blockSignals(True)
                self.key_combo.clear()
                self.key_combo.addItems(self.reader.list_data_keys())
                self.key_combo.blockSignals(False)
                self.status.setText(f"Opened with backend={self.reader.backend_name or 'jsonl'}")
                self._load_key(self.key_combo.currentText())
            except Exception as exc:  # pragma: no cover - user-facing GUI path
                self.status.setText(str(exc))
                self.canvas.set_message(str(exc))

        def _refresh_run_choices(self) -> None:
            self.run_paths = _discover_run_folders(self.run_root)
            if self.run_path not in self.run_paths and self.run_path.joinpath("dataset_manifest.json").exists():
                self.run_paths.insert(0, self.run_path)
            self.run_combo.blockSignals(True)
            self.run_combo.clear()
            for path in self.run_paths:
                self.run_combo.addItem(_run_label(path, self.run_root), str(path))
            if self.run_path in self.run_paths:
                self.run_combo.setCurrentIndex(self.run_paths.index(self.run_path))
            self.run_combo.blockSignals(False)

        def _run_choice_changed(self, index: int) -> None:
            if index < 0 or index >= len(self.run_paths):
                return
            self.run_path = self.run_paths[index]
            self._open_reader(self.backend_combo.currentText())

        def _browse_run_folder(self) -> None:
            selected = QtWidgets.QFileDialog.getExistingDirectory(self, "Open Qulab run folder", str(self.run_root))
            if not selected:
                return
            path = Path(selected)
            if path.joinpath("dataset_manifest.json").exists():
                self.run_path = path
                self.run_root = path.parent
            else:
                self.run_root = path
                discovered = _discover_run_folders(path)
                if discovered:
                    self.run_path = discovered[0]
            self._refresh_run_choices()
            self._open_reader(self.backend_combo.currentText())

        def _load_key(self, key: str) -> None:
            if not key or self.model is None:
                return
            try:
                self.current_data = self.model.get_data_var_metadata(key)
            except Exception as exc:  # pragma: no cover - user-facing GUI path
                self.status.setText(str(exc))
                return
            self.x_combo.blockSignals(True)
            self.y_combo.blockSignals(True)
            self.x_combo.clear()
            self.y_combo.clear()
            self._set_plot_type_options()
            self.x_combo.blockSignals(False)
            self.y_combo.blockSignals(False)
            self._axes_changed()
            self._render()

        def _set_plot_type_options(self) -> None:
            assert self.current_data is not None
            self.plot_type_combo.blockSignals(True)
            self.plot_type_combo.clear()
            self.plot_type_combo.addItems(list(_plot_modes_for(self.current_data)))
            self.plot_type_combo.blockSignals(False)

        def _plot_type_changed(self, _value: str) -> None:
            self._axes_changed()
            self._render()

        def _axes_changed(self) -> None:
            self._update_axis_controls()
            self._rebuild_selectors()
            self._render()

        def _update_axis_controls(self) -> None:
            if self.current_data is None:
                return
            plot_type = self.plot_type_combo.currentText()
            x_dims, y_dims = _axis_options_for(self.current_data, plot_type)
            current_x = self.x_combo.currentText()
            current_y = self.y_combo.currentText()
            self.x_combo.blockSignals(True)
            self.y_combo.blockSignals(True)
            self.x_combo.clear()
            self.y_combo.clear()
            self.x_combo.addItems(list(x_dims))
            self.y_combo.addItems(list(y_dims))
            if current_x in x_dims:
                self.x_combo.setCurrentText(current_x)
            if current_y in y_dims:
                self.y_combo.setCurrentText(current_y)
            elif y_dims:
                self.y_combo.setCurrentText(y_dims[0])
            self.x_combo.setEnabled(plot_type != "Trace")
            self.y_combo.setEnabled(plot_type in {"Heatmap", "Trace Mean Heatmap"})
            self.x_combo.blockSignals(False)
            self.y_combo.blockSignals(False)

        def _rebuild_selectors(self) -> None:
            while self.selector_form.rowCount():
                self.selector_form.removeRow(0)
            self.selector_widgets.clear()
            if self.current_data is None:
                return
            hidden_dims = self._hidden_selector_dims()
            for dim in self.current_data.dims:
                if dim not in hidden_dims:
                    continue
                combo = QtWidgets.QComboBox()
                for value in self.current_data.coords[dim].tolist():
                    combo.addItem(str(value), value)
                combo.currentIndexChanged.connect(lambda _index: self._render())
                self.selector_widgets[dim] = combo
                self.selector_form.addRow(f"{dim} selector", combo)

        def _render(self) -> None:
            if self.current_data is None or self.controller is None:
                return
            key = self.key_combo.currentText()
            dims = self.current_data.dims
            selectors = self._selectors()
            try:
                plot_type = self.plot_type_combo.currentText()
                if plot_type == "Trace":
                    point_selectors = {dim: value for dim, value in selectors.items() if dim not in {"time_s", "channel"}}
                    channel = selectors.get("channel")
                    trace = self.controller.get_point_trace(key, point_selectors, channel=channel)
                    self.canvas.set_line(f"{key} trace", trace.time, trace.values)
                    self._fill_vector_table(trace.time_dim, trace.time, key, trace.values)
                    self.status.setText(f"Rendered {key}; point={trace.point_coords}; status={trace.point_status or 'unknown'}")
                elif plot_type == "Line Slice":
                    x_dim = self.x_combo.currentText()
                    hidden = {dim: value for dim, value in selectors.items() if dim != x_dim}
                    line = self.controller.slice_1d(key, x_dim, hidden)
                    self.canvas.set_line(key, line.x, line.y)
                    self._fill_vector_table(line.x_dim, line.x, key, line.y)
                    self.status.setText(f"Rendered {key}")
                elif plot_type == "Trace Mean Line":
                    x_dim = self.x_combo.currentText()
                    hidden = {dim: value for dim, value in selectors.items() if dim != x_dim}
                    x_values, y_values = _reduced_line(self.model, key, x_dim, hidden)
                    self.canvas.set_line(f"{key} mean", x_values, y_values)
                    self._fill_vector_table(x_dim, x_values, f"{key}_mean", y_values)
                    self.status.setText(f"Rendered mean line for {key}")
                elif plot_type == "Trace Mean Heatmap":
                    x_dim = self.x_combo.currentText()
                    y_dim = self.y_combo.currentText()
                    hidden = {dim: value for dim, value in selectors.items() if dim not in {x_dim, y_dim}}
                    x_values, y_values, values = _reduced_heatmap(self.model, key, x_dim, y_dim, hidden)
                    self.canvas.set_heatmap(f"{key} mean", x_values, y_values, values)
                    self._fill_matrix_table(x_values, y_values, values)
                    self.status.setText(f"Rendered mean heatmap for {key}")
                else:
                    x_dim = self.x_combo.currentText()
                    y_dim = self.y_combo.currentText()
                    hidden = {dim: value for dim, value in selectors.items() if dim not in {x_dim, y_dim}}
                    heatmap = self.controller.slice_2d(key, x_dim, y_dim, hidden)
                    self.canvas.set_heatmap(key, heatmap.x, heatmap.y, heatmap.values)
                    self._fill_matrix_table(heatmap.x, heatmap.y, heatmap.values)
                    self.status.setText(f"Rendered {key}")
            except Exception as exc:  # pragma: no cover - user-facing GUI path
                self.status.setText(str(exc))
                self.canvas.set_message(str(exc))

        def _selectors(self) -> dict[str, Any]:
            selectors: dict[str, Any] = {}
            for dim, widget in self.selector_widgets.items():
                selectors[dim] = widget.currentData()
            return selectors

        def _hidden_selector_dims(self) -> set[str]:
            if self.current_data is None:
                return set()
            plot_type = self.plot_type_combo.currentText()
            if plot_type == "Trace":
                return {dim for dim in self.current_data.dims if dim != "time_s"}
            if plot_type == "Trace Mean Line":
                return {dim for dim in self.current_data.dims if dim not in {self.x_combo.currentText(), "time_s"}}
            if plot_type == "Line Slice":
                return {dim for dim in self.current_data.dims if dim != self.x_combo.currentText()}
            if plot_type == "Trace Mean Heatmap":
                return {
                    dim
                    for dim in self.current_data.dims
                    if dim not in {self.x_combo.currentText(), self.y_combo.currentText(), "time_s"}
                }
            return {dim for dim in self.current_data.dims if dim not in {self.x_combo.currentText(), self.y_combo.currentText()}}

        def _fill_vector_table(self, x_name: str, x: np.ndarray, y_name: str, y: np.ndarray) -> None:
            self.table.clear()
            self.table.setRowCount(len(x))
            self.table.setColumnCount(2)
            self.table.setHorizontalHeaderLabels([x_name, y_name])
            for row, (x_value, y_value) in enumerate(zip(x, y)):
                self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(x_value)))
                self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(y_value)))

        def _fill_matrix_table(self, x: np.ndarray, y: np.ndarray, values: np.ndarray) -> None:
            self.table.clear()
            self.table.setRowCount(len(y))
            self.table.setColumnCount(len(x))
            self.table.setHorizontalHeaderLabels([str(value) for value in x])
            self.table.setVerticalHeaderLabels([str(value) for value in y])
            for row in range(values.shape[0]):
                for col in range(values.shape[1]):
                    self.table.setItem(row, col, QtWidgets.QTableWidgetItem(f"{values[row, col]:.6g}"))

    return ViewerWindow()


def _range(values: np.ndarray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0, 1.0
    low = float(np.min(finite))
    high = float(np.max(finite))
    if low == high:
        high = low + 1.0
    return low, high


def _initial_run_path(path: Path) -> Path:
    if path.joinpath("dataset_manifest.json").exists():
        return path
    runs = _discover_run_folders(path)
    return runs[0] if runs else path


def _discover_run_folders(root: Path) -> list[Path]:
    if root.joinpath("dataset_manifest.json").exists():
        return [root]
    if not root.exists():
        return []
    manifests = sorted(root.glob("**/dataset_manifest.json"))
    return [manifest.parent for manifest in manifests]


def _run_label(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _plot_modes_for(data: DataArray) -> tuple[str, ...]:
    kind = data.kind
    dims = data.dims
    slow_dims = _slow_scan_dims(data)
    if kind == "trace_grid":
        modes = ["Trace"]
        if len(slow_dims) >= 2:
            modes.append("Trace Mean Heatmap")
        if len(slow_dims) >= 1:
            modes.append("Trace Mean Line")
        return tuple(modes)
    if kind == "scalar_grid":
        if len(dims) >= 2:
            return ("Heatmap", "Line Slice")
        return ("Line Slice",)
    if "time_s" in dims:
        return ("Trace",)
    if len(dims) >= 2:
        return ("Heatmap", "Line Slice")
    return ("Line Slice",)


def _axis_options_for(data: DataArray, plot_type: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    slow_dims = _slow_scan_dims(data)
    if plot_type == "Trace":
        time_dim = "time_s" if "time_s" in data.dims else data.dims[-1]
        return (time_dim,), ()
    if plot_type in {"Trace Mean Line", "Trace Mean Heatmap"}:
        x_dims = slow_dims or tuple(dim for dim in data.dims if dim != "time_s")
        y_dims = tuple(dim for dim in x_dims if dim != x_dims[0])
        return x_dims, y_dims
    if plot_type == "Line Slice":
        return data.dims, ()
    y_dims = tuple(dim for dim in data.dims if dim != data.dims[0])
    return data.dims, y_dims


def _slow_scan_dims(data: DataArray) -> tuple[str, ...]:
    return tuple(dim for dim in data.dims if dim not in {"time_s", "channel"})


def _reduced_line(model: DatasetModel, key: str, x_dim: str, selectors: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    data = model.get_data_var(key, selection=selectors)
    values = np.asarray(data.values, dtype=float)
    axis = data.dims.index(x_dim)
    if axis != 0:
        values = np.moveaxis(values, axis, 0)
    if values.ndim > 1:
        values = np.nanmean(values, axis=tuple(range(1, values.ndim)))
    return data.coords[x_dim], np.asarray(values).reshape(len(data.coords[x_dim]))


def _reduced_heatmap(
    model: DatasetModel, key: str, x_dim: str, y_dim: str, selectors: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    data = model.get_data_var(key, selection=selectors)
    values = np.asarray(data.values, dtype=float)
    x_axis = data.dims.index(x_dim)
    y_axis = data.dims.index(y_dim)
    values = np.moveaxis(values, (x_axis, y_axis), (1, 0))
    if values.ndim > 2:
        values = np.nanmean(values, axis=tuple(range(2, values.ndim)))
    values = values.reshape(len(data.coords[y_dim]), len(data.coords[x_dim]))
    return data.coords[x_dim], data.coords[y_dim], values


def _color_ramp(QtGui: Any, ratio: float) -> Any:
    ratio = max(0.0, min(1.0, ratio))
    red = int(42 + 210 * ratio)
    green = int(88 + 88 * (1.0 - abs(ratio - 0.5) * 2.0))
    blue = int(164 + 70 * (1.0 - ratio))
    return QtGui.QColor(red, green, blue)


def _matplotlib_canvas_class(QtWidgets: Any) -> Any | None:
    try:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
    except Exception:
        return None

    class MatplotlibCanvas(FigureCanvasQTAgg):
        def __init__(self) -> None:
            self.figure = Figure(figsize=(6.2, 4.2), dpi=100)
            self._colorbar = None
            super().__init__(self.figure)
            self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

    return MatplotlibCanvas


def _pyqtgraph_canvas_class(QtWidgets: Any) -> Any | None:
    try:
        import pyqtgraph as pg
    except Exception:
        return None

    class PyqtgraphCanvas(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.plot = pg.PlotWidget()
            self.image_item = None
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.plot)
            self.plot.showGrid(x=True, y=True, alpha=0.25)

        def set_line(self, title: str, x: np.ndarray, y: np.ndarray) -> None:
            self.plot.clear()
            self.image_item = None
            self.plot.setTitle(title)
            self.plot.showGrid(x=True, y=True, alpha=0.25)
            self.plot.plot(np.asarray(x, dtype=float), np.asarray(y, dtype=float), pen=pg.mkPen("#2563eb", width=2), symbol="o")

        def set_heatmap(self, title: str, x: np.ndarray, y: np.ndarray, values: np.ndarray) -> None:
            self.plot.clear()
            self.plot.setTitle(title)
            self.plot.showGrid(x=False, y=False)
            self.image_item = pg.ImageItem(np.asarray(values, dtype=float).T)
            self.plot.addItem(self.image_item)
            self.plot.autoRange()

        def set_message(self, title: str) -> None:
            self.plot.clear()
            self.plot.setTitle(title)
            label = pg.TextItem(title, anchor=(0.5, 0.5), color="#667085")
            self.plot.addItem(label)
            label.setPos(0, 0)

    return PyqtgraphCanvas


if __name__ == "__main__":
    raise SystemExit(main())
