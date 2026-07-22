"""Optional PySide6/PyQt6 widgets for the operator console."""

from __future__ import annotations

import queue
import threading
import json
from pathlib import Path
from typing import Any

from qulab.core import DataPoint, Event
from qulab.paths import resolve_project_path

from .controller import OperatorController
from .models import format_parameter_value, parse_parameter_value
from .plot_model import PlotSeries
from .plot_canvas import LineSeriesView, scientific_plot_canvas_class
from .qt_compat import QT_AVAILABLE, QtCore, QtGui, QtWidgets, missing_qt_message
from .sequence_bridge import default_sequence_editor_path, open_sequence_editor
from .theme import classic_qt_stylesheet
from .workflow_model import WorkflowNode, make_default_step


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "experiments" / "dry_run_rabi.yaml"
ODMR_CONFIG = PROJECT_ROOT / "configs" / "experiments" / "dry_run_odmr.yaml"
TWO_MW_CONFIG = PROJECT_ROOT / "configs" / "experiments" / "dry_run_two_mw_scan.yaml"


if QT_AVAILABLE:

    class LinePlotWidget(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.series = PlotSeries()
            self.setMinimumHeight(170)

        def clear(self) -> None:
            self.series.clear()
            self.update()

        def handle_event(self, event: Event) -> None:
            self.series.handle_event(event)
            self.update()

        def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
            painter = QtGui.QPainter(self)
            painter.fillRect(self.rect(), QtGui.QColor("#ffffff"))
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

            margin_left, margin_top, margin_right, margin_bottom = 48, 18, 18, 34
            width = max(self.width(), 220)
            height = max(self.height(), 140)
            left = margin_left
            right = width - margin_right
            top = margin_top
            bottom = height - margin_bottom

            axis_pen = QtGui.QPen(QtGui.QColor("#6b7280"))
            painter.setPen(axis_pen)
            painter.drawLine(left, bottom, right, bottom)
            painter.drawLine(left, bottom, left, top)

            points = self.series.points
            painter.setPen(QtGui.QColor("#374151"))
            painter.drawText(left + 8, top + 16, f"points: {len(points)}")
            if points:
                latest_x, latest_y = points[-1]
                painter.drawText(left + 8, top + 34, f"latest: x={latest_x:.6g}, y={latest_y:.6g}")
            else:
                painter.setPen(QtGui.QColor("#9ca3af"))
                painter.drawText(self.rect(), _align_center(), "Waiting for DataPoint events")
                return

            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            span_x = max(max_x - min_x, 1.0)
            span_y = max(max_y - min_y, 1.0)
            scaled = [
                QtCore.QPointF(
                    left + (x - min_x) / span_x * (right - left),
                    bottom - (y - min_y) / span_y * (bottom - top),
                )
                for x, y in points
            ]
            pen = QtGui.QPen(QtGui.QColor("#2563eb"))
            pen.setWidth(2)
            painter.setPen(pen)
            if len(scaled) > 1:
                for start, end in zip(scaled, scaled[1:]):
                    painter.drawLine(start, end)
            painter.setBrush(QtGui.QColor("#2563eb"))
            painter.setPen(QtGui.QColor("#2563eb"))
            for point in scaled[-12:]:
                painter.drawEllipse(point, 3, 3)


    class PyQtOperatorWindow(QtWidgets.QMainWindow):
        def __init__(self, controller: OperatorController | None = None, config_path: Path | str | None = None) -> None:
            super().__init__()
            self.controller = controller or OperatorController(PROJECT_ROOT / "runs")
            self.event_queue: queue.Queue[Any] = queue.Queue()
            self.running = False
            self.selected_node: WorkflowNode | None = None
            self.inspector_widgets: dict[str, Any] = {}
            self.operator_parameter_widgets: dict[str, Any] = {}
            self.sequence_metadata: Any | None = None
            self.setWindowTitle("Qulab Operator Console")
            self.resize(1260, 860)
            self._build_ui()
            self.sequence_watcher = QtCore.QFileSystemWatcher(self)
            self.sequence_watcher.fileChanged.connect(self._on_sequence_file_changed)
            self._apply_style()
            self._load_config(Path(config_path) if config_path else DEFAULT_CONFIG)
            self._live_signature: tuple[Any, ...] | None = None
            self.timer = QtCore.QTimer(self)
            self.timer.timeout.connect(self._drain_events)
            self.timer.start(80)

        def _build_ui(self) -> None:
            toolbar = self.addToolBar("Operator")
            toolbar.setMovable(False)
            self.load_action = QtWidgets.QPushButton("Load / 载入")
            self.save_action = QtWidgets.QPushButton("Save / 保存")
            toolbar.addWidget(self.load_action)
            toolbar.addWidget(self.save_action)
            toolbar.addSeparator()
            self.prepare_action = QtWidgets.QPushButton("Prepare / 预检查")
            self.start_action = QtWidgets.QPushButton("Start / 开始")
            self.stop_action = QtWidgets.QPushButton("Stop / 停止")
            self.start_action.setObjectName("primaryButton")
            self.stop_action.setObjectName("dangerButton")
            for button in (self.prepare_action, self.start_action, self.stop_action):
                toolbar.addWidget(button)
            self.load_action.clicked.connect(self._choose_yaml)
            self.save_action.clicked.connect(self._save_yaml)
            self.prepare_action.clicked.connect(self._prepare)
            self.start_action.clicked.connect(self._start)
            self.stop_action.clicked.connect(self._stop)

            central = QtWidgets.QWidget()
            central_layout = QtWidgets.QVBoxLayout(central)
            central_layout.setContentsMargins(10, 8, 10, 10)
            central_layout.setSpacing(8)
            self.setCentralWidget(central)

            self.main_pages = QtWidgets.QTabWidget()
            central_layout.addWidget(self.main_pages, 1)
            self.main_pages.addTab(self._build_control_page(), "Control / 控制")
            self.main_pages.addTab(self._build_live_run_page(), "Live Run / 运行")
            self.viewer_panel = self._build_run_data_panel()
            self.main_pages.addTab(self.viewer_panel, "Data Viewer / 数据查看")

        def _build_control_page(self) -> QtWidgets.QWidget:
            page = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            main_splitter = QtWidgets.QSplitter(_horizontal())
            layout.addWidget(main_splitter, 1)

            left = self._build_left_panel()
            submodes = self._build_submode_tabs()
            main_splitter.addWidget(left)
            main_splitter.addWidget(submodes)
            main_splitter.setSizes([300, 900])
            return page

        def _build_live_run_page(self) -> QtWidgets.QWidget:
            page = QtWidgets.QSplitter(_vertical())
            live_tab = self._panel("Live Plot / Event Preview / 实时预览")
            plot_layout = QtWidgets.QVBoxLayout(live_tab)
            plot_layout.setContentsMargins(10, 24, 10, 10)
            live_splitter = QtWidgets.QSplitter(_horizontal())
            sources = QtWidgets.QWidget()
            source_layout = QtWidgets.QVBoxLayout(sources)
            source_layout.setContentsMargins(0, 0, 0, 0)
            source_layout.addWidget(QtWidgets.QLabel("Raw / Derived Sources"))
            self.live_source_filter = QtWidgets.QLineEdit(); self.live_source_filter.setPlaceholderText("Filter sources…")
            source_layout.addWidget(self.live_source_filter)
            self.live_source_table = QtWidgets.QTableWidget(0, 7)
            self.live_source_table.setHorizontalHeaderLabels(["Show", "Key", "Source", "Kind", "Unit", "State", "Storage"])
            self.live_source_table.horizontalHeader().setStretchLastSection(True)
            source_layout.addWidget(self.live_source_table)
            controls = QtWidgets.QHBoxLayout()
            self.live_plot_type = QtWidgets.QComboBox(); self.live_plot_type.addItems(["Auto", "Line", "Heatmap", "Trace", "Table"])
            self.live_x_dim = QtWidgets.QComboBox(); self.live_y_dim = QtWidgets.QComboBox()
            controls.addWidget(self.live_plot_type); controls.addWidget(self.live_x_dim); controls.addWidget(self.live_y_dim)
            source_layout.addLayout(controls)
            self.live_selector_form = QtWidgets.QFormLayout(); self.live_selector_widgets: dict[str, Any] = {}
            source_layout.addLayout(self.live_selector_form)
            live_splitter.addWidget(sources)

            center = QtWidgets.QWidget(); center_layout = QtWidgets.QVBoxLayout(center); center_layout.setContentsMargins(0, 0, 0, 0)
            Canvas = scientific_plot_canvas_class(QtWidgets, QtCore, QtGui)
            self.plot = Canvas()
            display_controls = QtWidgets.QHBoxLayout()
            self.live_point = QtWidgets.QComboBox(); self.live_channel = QtWidgets.QComboBox()
            self.live_pause = QtWidgets.QCheckBox("Pause display"); self.live_auto_follow = QtWidgets.QCheckBox("Auto-follow"); self.live_auto_follow.setChecked(True)
            clear = QtWidgets.QPushButton("Clear display"); reset = QtWidgets.QPushButton("Reset view")
            for widget in (QtWidgets.QLabel("Point"), self.live_point, QtWidgets.QLabel("Channel"), self.live_channel,
                           self.live_pause, self.live_auto_follow, clear, reset): display_controls.addWidget(widget)
            center_layout.addLayout(display_controls)
            self.live_plot_status = QtWidgets.QLabel("No live data selected")
            self.preview_table = QtWidgets.QTableWidget(0, 3)
            self.preview_table.setHorizontalHeaderLabels(["point_id", "coords", "values"])
            self.preview_table.horizontalHeader().setStretchLastSection(True)
            center_layout.addWidget(self.live_plot_status); center_layout.addWidget(self.plot, 2); center_layout.addWidget(self.preview_table, 1)
            for combo in (self.live_plot_type, self.live_x_dim, self.live_y_dim, self.live_point, self.live_channel):
                combo.currentTextChanged.connect(self._live_controls_changed)
            self.live_source_table.itemChanged.connect(self._live_source_changed)
            self.live_source_filter.textChanged.connect(self._apply_live_filter)
            self.live_pause.toggled.connect(lambda paused: None if paused else self._render_live_plot())
            self.live_auto_follow.toggled.connect(self._live_controls_changed)
            clear.clicked.connect(self._clear_live_display); reset.clicked.connect(self.plot.reset_view)
            live_splitter.addWidget(center)

            context = QtWidgets.QWidget(); context_layout = QtWidgets.QVBoxLayout(context); context_layout.setContentsMargins(0, 0, 0, 0)
            context_layout.addWidget(QtWidgets.QLabel("Compute Modules"))
            self.analysis_status_table = QtWidgets.QTableWidget(0, 4)
            self.analysis_status_table.setHorizontalHeaderLabels(["Module", "State", "Latency", "Queue"])
            context_layout.addWidget(self.analysis_status_table)
            context_layout.addWidget(QtWidgets.QLabel("Sequence Context"))
            self.live_sequence_context = QtWidgets.QPlainTextEdit(); self.live_sequence_context.setReadOnly(True)
            context_layout.addWidget(self.live_sequence_context)
            live_splitter.addWidget(context)
            live_splitter.setSizes([260, 600, 300])
            plot_layout.addWidget(live_splitter)
            page.addWidget(live_tab)

            log_box = self._panel("Run Log / 运行日志")
            log_layout = QtWidgets.QVBoxLayout(log_box)
            log_layout.setContentsMargins(10, 24, 10, 10)
            self.log = QtWidgets.QPlainTextEdit()
            self.log.setReadOnly(True)
            log_layout.addWidget(self.log)
            page.addWidget(log_box)
            page.setSizes([480, 260])
            return page

        def _build_submode_tabs(self) -> QtWidgets.QWidget:
            tabs = QtWidgets.QTabWidget()
            tabs.addTab(self._build_operator_parameters_panel(), "Operator Parameters / 操作参数")
            tabs.addTab(self._build_sequence_sweep_panel(), "Sequence Sweep / 序列扫描")
            builder = QtWidgets.QSplitter(_horizontal())
            builder.addWidget(self._build_workflow_panel())
            builder.addWidget(self._build_inspector_panel())
            builder.setSizes([470, 450])
            tabs.addTab(builder, "Builder Workflow / 流程编辑")
            direct = self._panel("Direct Control / 直接控制")
            layout = QtWidgets.QVBoxLayout(direct)
            layout.setContentsMargins(10, 24, 10, 10)
            label = QtWidgets.QLabel("Direct Control is planned for P8.3. No hardware actions are available here.")
            label.setWordWrap(True)
            label.setEnabled(False)
            layout.addWidget(label)
            layout.addStretch(1)
            tabs.addTab(direct, "Direct Control / 直接控制")
            tabs.setTabEnabled(3, False)
            self.submode_tabs = tabs
            return tabs

        def _build_sequence_sweep_panel(self) -> QtWidgets.QWidget:
            panel = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(panel)
            controls = QtWidgets.QHBoxLayout()
            refresh = QtWidgets.QPushButton("Refresh / 刷新")
            add_plan = QtWidgets.QPushButton("Add / 新建")
            duplicate_plan = QtWidgets.QPushButton("Duplicate / 复制")
            delete_plan = QtWidgets.QPushButton("Delete / 删除")
            preview = QtWidgets.QPushButton("Preview first / 预览首点")
            apply = QtWidgets.QPushButton("Apply edits / 应用编辑")
            prepare = QtWidgets.QPushButton("Prepare bundle / 生成")
            refresh.clicked.connect(self._refresh_sequence_sweep)
            add_plan.clicked.connect(self._add_sequence_plan)
            duplicate_plan.clicked.connect(self._duplicate_sequence_plan)
            delete_plan.clicked.connect(self._delete_sequence_plan)
            preview.clicked.connect(self._preview_selected_sequence_plan)
            apply.clicked.connect(self._apply_sequence_plan_edits)
            prepare.clicked.connect(self._prepare_sequence_sweep)
            for button in (refresh, add_plan, duplicate_plan, delete_plan, apply, preview, prepare): controls.addWidget(button)
            controls.addStretch(1); layout.addLayout(controls)
            splitter = QtWidgets.QSplitter(_vertical())
            self.sequence_plan_table = QtWidgets.QTableWidget(0, 8)
            self.sequence_plan_table.setHorizontalHeaderLabels(
                ["Plan", "Resource", "Provider", "Template", "Axes", "Points", "State", "Hash"]
            )
            self.sequence_plan_table.horizontalHeader().setStretchLastSection(True)
            self.sequence_plan_table.itemSelectionChanged.connect(self._show_selected_sequence_plan)
            splitter.addWidget(self.sequence_plan_table)
            editors = QtWidgets.QTabWidget()
            self.sequence_parameter_table = QtWidgets.QTableWidget(0, 4)
            self.sequence_parameter_table.setHorizontalHeaderLabels(["Parameter", "Mode", "Mode fields (JSON)", "Unit"])
            self.sequence_parameter_table.horizontalHeader().setStretchLastSection(True)
            editors.addTab(self.sequence_parameter_table, "Parameters")
            self.sequence_target_table = QtWidgets.QTableWidget(0, 4)
            self.sequence_target_table.setHorizontalHeaderLabels(["Alias", "Channel", "Pulse", "Fingerprint"])
            self.sequence_target_table.horizontalHeader().setStretchLastSection(True)
            editors.addTab(self.sequence_target_table, "Targets")
            self.sequence_constraints_edit = QtWidgets.QPlainTextEdit("[]")
            editors.addTab(self.sequence_constraints_edit, "Constraints JSON")
            self.sequence_plan_details = QtWidgets.QPlainTextEdit()
            self.sequence_plan_details.setPlaceholderText(
                "Select a plan. Parameter modes, targets, constraints, preview and compiled workflow appear here."
            )
            self.sequence_plan_details.setReadOnly(True)
            editors.addTab(self.sequence_plan_details, "Preview / compiled")
            splitter.addWidget(editors); splitter.setSizes([220, 420])
            layout.addWidget(splitter, 1)
            return panel

        def _refresh_sequence_sweep(self) -> None:
            if not hasattr(self, "sequence_plan_table"): return
            self.sequence_plan_table.setRowCount(0)
            try: plans = self.controller.list_sequence_plans()
            except Exception as exc:
                self.sequence_plan_details.setPlainText(f"Sequence plans unavailable: {exc}"); return
            for plan in plans:
                row = self.sequence_plan_table.rowCount(); self.sequence_plan_table.insertRow(row)
                axes = ", ".join(item.name for item in plan.parameters if item.mode != "fixed")
                values = (plan.id, plan.resource, plan.provider, plan.template or "", axes, plan.point_count,
                          plan.state, (plan.plan_hash or "")[:12])
                for column, value in enumerate(values): self.sequence_plan_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
            if plans: self.sequence_plan_table.selectRow(0)
            else: self.sequence_plan_details.setPlainText("No sequence_plans in this config. Add one through the Controller API or YAML.")

        def _selected_sequence_plan_id(self) -> str:
            row = self.sequence_plan_table.currentRow()
            item = self.sequence_plan_table.item(row, 0) if row >= 0 else None
            return item.text() if item else ""

        def _add_sequence_plan(self) -> None:
            resources = self.controller.sequence_resource_names()
            providers = [item for item in self.controller.list_sequence_providers() if "error" not in item]
            if not resources or not providers:
                QtWidgets.QMessageBox.warning(self, "Sequence plan", "A pulse_sequencer resource and provider are required."); return
            dialog = QtWidgets.QDialog(self); dialog.setWindowTitle("Add sequence plan")
            form = QtWidgets.QFormLayout(dialog)
            plan_id = QtWidgets.QLineEdit("sequence_main"); resource = QtWidgets.QComboBox(); resource.addItems(resources)
            provider = QtWidgets.QComboBox()
            for item in providers: provider.addItem(f"{item['label']} (v{item['version']})", item["id"])
            template = QtWidgets.QLineEdit()
            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
            form.addRow("Plan id", plan_id); form.addRow("Resource", resource); form.addRow("Family/provider", provider)
            form.addRow("Template (generic only)", template); form.addRow(buttons)
            if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted: return
            try:
                self.controller.create_sequence_plan(plan_id.text().strip(), resource.currentText(), provider.currentData(), template.text().strip() or None)
                self._refresh_sequence_sweep()
            except Exception as exc: QtWidgets.QMessageBox.critical(self, "Add sequence plan failed", str(exc))

        def _duplicate_sequence_plan(self) -> None:
            selected = self._selected_sequence_plan_id()
            if not selected: return
            new_id, ok = QtWidgets.QInputDialog.getText(self, "Duplicate sequence plan", "New plan id", text=f"{selected}_copy")
            if ok and new_id.strip():
                try: self.controller.duplicate_sequence_plan(selected, new_id.strip()); self._refresh_sequence_sweep()
                except Exception as exc: QtWidgets.QMessageBox.critical(self, "Duplicate failed", str(exc))

        def _delete_sequence_plan(self) -> None:
            selected = self._selected_sequence_plan_id()
            if not selected: return
            self.controller.delete_sequence_plan(selected); self._refresh_sequence_sweep()

        def _show_selected_sequence_plan(self) -> None:
            plan_id = self._selected_sequence_plan_id()
            if not plan_id: return
            plan = next((item for item in self.controller.list_sequence_plans() if item.id == plan_id), None)
            if plan is None: return
            self.sequence_parameter_table.setRowCount(0)
            for parameter in plan.parameters:
                row = self.sequence_parameter_table.rowCount(); self.sequence_parameter_table.insertRow(row)
                fields = dict(parameter.values); fields.pop("mode", None); fields.pop("unit", None)
                for column, value in enumerate((parameter.name, parameter.mode, json.dumps(fields, ensure_ascii=False), parameter.unit or "")):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    if column in {0, 3}: item.setFlags(item.flags() & ~_item_is_editable())
                    self.sequence_parameter_table.setItem(row, column, item)
            self.sequence_target_table.setRowCount(0)
            for target in plan.targets:
                row = self.sequence_target_table.rowCount(); self.sequence_target_table.insertRow(row)
                for column, value in enumerate((target.alias, target.channel, target.pulse, target.fingerprint or "")):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    if column in {0, 3}: item.setFlags(item.flags() & ~_item_is_editable())
                    self.sequence_target_table.setItem(row, column, item)
            self.sequence_constraints_edit.setPlainText(json.dumps([item.__dict__ for item in plan.constraints], ensure_ascii=False, indent=2))
            lines = [f"{plan.id}  [{plan.state}]", f"provider: {plan.provider} v{plan.provider_version}",
                     f"template: {plan.template or '(provider generated)'}", f"point count: {plan.point_count}", "parameters:"]
            lines.extend(f"  {item.name}: {json.dumps(dict(item.values), ensure_ascii=False)}" for item in plan.parameters)
            if plan.targets:
                lines.append("targets:"); lines.extend(f"  {item.alias}: {item.channel}[{item.pulse}] fingerprint={item.fingerprint or '(unsaved)'}" for item in plan.targets)
            if plan.constraints:
                lines.append("constraints:"); lines.extend(f"  {item.target} <- {item.reference} + {item.offset_s}s" for item in plan.constraints)
            if plan.issues:
                lines.append("issues:"); lines.extend(f"  [{item.code}] {item.message}" for item in plan.issues)
            compiled = self.controller.compiled_sequence_workflow_preview()
            if compiled is not None:
                lines.append("compiled workflow preview:"); lines.append(json.dumps(compiled.get("procedure", []), ensure_ascii=False, indent=2))
            self.sequence_plan_details.setPlainText("\n".join(lines))

        def _apply_sequence_plan_edits(self) -> None:
            plan_id = self._selected_sequence_plan_id()
            if not plan_id: return
            try:
                for row in range(self.sequence_parameter_table.rowCount()):
                    name = self.sequence_parameter_table.item(row, 0).text()
                    mode = self.sequence_parameter_table.item(row, 1).text().strip()
                    fields = json.loads(self.sequence_parameter_table.item(row, 2).text() or "{}")
                    if not isinstance(fields, dict): raise ValueError(f"{name} mode fields must be a JSON object")
                    self.controller.update_sequence_plan_parameter(plan_id, name, {"mode": mode, **fields})
                for row in range(self.sequence_target_table.rowCount()):
                    alias = self.sequence_target_table.item(row, 0).text()
                    channel = self.sequence_target_table.item(row, 1).text().strip()
                    pulse = int(self.sequence_target_table.item(row, 2).text())
                    self.controller.select_sequence_plan_target(plan_id, alias, channel, pulse)
                constraints = json.loads(self.sequence_constraints_edit.toPlainText() or "[]")
                if not isinstance(constraints, list): raise ValueError("constraints must be a JSON list")
                self.controller.update_sequence_plan_constraints(plan_id, constraints)
                self._refresh_sequence_sweep(); self._refresh_operator_parameters()
            except Exception as exc: QtWidgets.QMessageBox.critical(self, "Sequence edit failed", str(exc))

        def _preview_selected_sequence_plan(self) -> None:
            plan_id = self._selected_sequence_plan_id()
            if not plan_id: return
            try:
                estimate = self.controller.estimate_sequence_plan(plan_id)
                preview = self.controller.preview_sequence_plan(plan_id, dict(estimate.first))
                text = json.dumps(preview.to_dict() if hasattr(preview, "to_dict") else preview, ensure_ascii=False, indent=2)
                self.sequence_plan_details.setPlainText(f"first point: {dict(estimate.first)}\n{text}")
            except Exception as exc: QtWidgets.QMessageBox.warning(self, "Sequence preview", str(exc))

        def _prepare_sequence_sweep(self) -> None:
            # The controller API is synchronous/headless; run outside the UI thread and return through a queued timer.
            self.prepare_action.setEnabled(False)
            def work():
                try: result = (self.controller.prepare(), None)
                except Exception as exc: result = (None, exc)
                self.event_queue.put(("sequence_prepare", *result))
            threading.Thread(target=work, daemon=True).start()

        def _finish_sequence_prepare(self, view: Any, error: Exception | None) -> None:
            self.prepare_action.setEnabled(True)
            if error is not None: QtWidgets.QMessageBox.critical(self, "Prepare failed", str(error)); return
            self._show_preflight(view); self._refresh_sequence_sweep()

        def _build_operator_parameters_panel(self) -> QtWidgets.QWidget:
            panel = self._panel("Operator Parameters / 操作参数")
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(10, 24, 10, 10)
            header = QtWidgets.QHBoxLayout()
            refresh = QtWidgets.QPushButton("Refresh / 刷新")
            apply = QtWidgets.QPushButton("Apply Parameters / 应用参数")
            apply.setObjectName("primaryButton")
            refresh.clicked.connect(self._refresh_operator_parameters)
            apply.clicked.connect(self._apply_operator_parameters)
            header.addWidget(refresh)
            header.addWidget(apply)
            header.addStretch(1)
            layout.addLayout(header)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            self.operator_parameters_widget = QtWidgets.QWidget()
            self.operator_parameters_form = QtWidgets.QFormLayout(self.operator_parameters_widget)
            scroll.setWidget(self.operator_parameters_widget)
            layout.addWidget(scroll, 1)
            return panel

        def _build_run_data_panel(self) -> QtWidgets.QWidget:
            from qulab.viewer.pyqt_viewer_app import create_data_viewer_panel

            return create_data_viewer_panel(QtWidgets, QtCore, QtGui, PROJECT_ROOT / "runs", "auto", "embedded")

        def _build_left_panel(self) -> QtWidgets.QWidget:
            splitter = QtWidgets.QSplitter(_vertical())
            splitter.addWidget(self._build_experiment_browser())
            resources = self._panel("Resources / 资源")
            layout = QtWidgets.QVBoxLayout(resources)
            layout.setContentsMargins(10, 24, 10, 10)
            self.resource_table = QtWidgets.QTableWidget(0, 4)
            self.resource_table.setHorizontalHeaderLabels(["name", "adapter", "sim", "connected"])
            self.resource_table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.resource_table)
            splitter.addWidget(resources)
            splitter.addWidget(self._build_sequence_panel())
            splitter.setSizes([220, 210, 260])
            return splitter

        def _build_experiment_browser(self) -> QtWidgets.QWidget:
            panel = self._panel("Experiments / 实验")
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(10, 24, 10, 10)
            self.experiment_table = QtWidgets.QTableWidget(0, 2)
            self.experiment_table.setHorizontalHeaderLabels(["Experiment / 实验", "File / 文件"])
            self.experiment_table.verticalHeader().setVisible(False)
            self.experiment_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            self.experiment_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.experiment_table.horizontalHeader().setStretchLastSection(True)
            self.experiment_table.itemDoubleClicked.connect(self._load_selected_experiment)
            for path in _experiment_config_paths():
                row = self.experiment_table.rowCount()
                self.experiment_table.insertRow(row)
                name_item = QtWidgets.QTableWidgetItem(path.stem)
                name_item.setData(_user_role(), path)
                file_item = QtWidgets.QTableWidgetItem(path.name)
                file_item.setData(_user_role(), path)
                self.experiment_table.setItem(row, 0, name_item)
                self.experiment_table.setItem(row, 1, file_item)
            self.experiment_table.resizeColumnsToContents()
            layout.addWidget(self.experiment_table)
            return panel

        def _build_sequence_panel(self) -> QtWidgets.QWidget:
            panel = QtWidgets.QGroupBox("ASG Sequence Preview / 时序预览")
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(8, 18, 8, 8)
            self.sequence_resource_combo = QtWidgets.QComboBox()
            self.sequence_resource_combo.currentTextChanged.connect(lambda _text: self._refresh_sequence_panel())
            layout.addWidget(self.sequence_resource_combo)
            self.sequence_metadata = QtWidgets.QPlainTextEdit()
            self.sequence_metadata.setReadOnly(True)
            self.sequence_metadata.setMaximumHeight(190)
            layout.addWidget(self.sequence_metadata)
            return panel

        def _build_workflow_panel(self) -> QtWidgets.QWidget:
            panel = self._panel("Workflow / Procedure Tree / 流程树")
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(10, 24, 10, 10)
            self.workflow_tree = QtWidgets.QTreeWidget()
            self.workflow_tree.setHeaderLabels(["Step", "Kind", "Enabled"])
            self.workflow_tree.itemSelectionChanged.connect(self._on_tree_selection)
            layout.addWidget(self.workflow_tree, 1)
            buttons = QtWidgets.QHBoxLayout()
            for label, kind in (("+ Scan / 扫描", "scan"), ("+ Average / 平均", "average"), ("+ Call / 调用", "call")):
                button = QtWidgets.QPushButton(label)
                button.clicked.connect(lambda checked=False, k=kind: self._add_step(k))
                buttons.addWidget(button)
            duplicate = QtWidgets.QPushButton("Duplicate / 复制")
            delete = QtWidgets.QPushButton("Delete / 删除")
            delete.setObjectName("dangerButton")
            duplicate.clicked.connect(self._duplicate_step)
            delete.clicked.connect(self._delete_step)
            buttons.addWidget(duplicate)
            buttons.addWidget(delete)
            layout.addLayout(buttons)
            return panel

        def _build_inspector_panel(self) -> QtWidgets.QWidget:
            panel = self._panel("Inspector / Preflight / 检查")
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(10, 24, 10, 10)
            layout.addWidget(self._build_builder_sequence_settings())
            self.inspector = QtWidgets.QWidget()
            self.inspector_form = QtWidgets.QFormLayout(self.inspector)
            layout.addWidget(self.inspector)
            self.apply_button = QtWidgets.QPushButton("Apply Selected Step / 应用步骤")
            self.apply_button.setObjectName("primaryButton")
            self.apply_button.clicked.connect(self._apply_inspector)
            layout.addWidget(self.apply_button)
            layout.addWidget(QtWidgets.QLabel("Preflight Issues / 预检查问题"))
            self.issue_table = QtWidgets.QTableWidget(0, 5)
            self.issue_table.setHorizontalHeaderLabels(["severity", "code", "location", "message", "hint"])
            self.issue_table.horizontalHeader().setStretchLastSection(True)
            self.issue_table.cellDoubleClicked.connect(self._focus_issue)
            layout.addWidget(self.issue_table, 1)
            return panel

        def _build_builder_sequence_settings(self) -> QtWidgets.QWidget:
            panel = QtWidgets.QGroupBox("ASG Sequence Settings / 时序设置")
            self.builder_sequence_box = panel
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(8, 18, 8, 8)
            self.sequence_settings_label = QtWidgets.QLabel("Selected load_sequence file / 已选时序文件")
            layout.addWidget(self.sequence_settings_label)
            self.sequence_path_line = QtWidgets.QLineEdit()
            self.sequence_path_line.editingFinished.connect(self._apply_sequence_file)
            layout.addWidget(self.sequence_path_line)
            buttons = QtWidgets.QHBoxLayout()
            browse = QtWidgets.QPushButton("Browse / 浏览")
            open_editor = QtWidgets.QPushButton("Open Editor / 打开编辑器")
            refresh = QtWidgets.QPushButton("Refresh / 刷新")
            browse.clicked.connect(self._browse_sequence_file)
            open_editor.clicked.connect(self._open_sequence_editor)
            refresh.clicked.connect(self._refresh_sequence_panel)
            buttons.addWidget(browse)
            buttons.addWidget(open_editor)
            buttons.addWidget(refresh)
            layout.addLayout(buttons)
            panel.setVisible(False)
            return panel

        def _panel(self, title: str) -> QtWidgets.QGroupBox:
            box = QtWidgets.QGroupBox(title)
            box.setFlat(False)
            return box

        def _apply_style(self) -> None:
            self.setStyleSheet(classic_qt_stylesheet())

        def _choose_yaml(self) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Load experiment YAML", str(PROJECT_ROOT / "configs" / "experiments"), "YAML (*.yaml *.yml)"
            )
            if path:
                self._load_config(Path(path))

        def _load_selected_experiment(self, item: Any) -> None:
            path = item.data(_user_role())
            if path:
                self._load_config(Path(path))

        def _save_yaml(self) -> None:
            default_path = self.controller.config_path or (PROJECT_ROOT / "configs" / "experiments" / "edited.yaml")
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save experiment YAML", str(default_path), "YAML (*.yaml)")
            if not path:
                return
            try:
                saved = self.controller.save_config(path)
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Save failed", str(exc))
                return
            self._log(f"Saved YAML: {saved}")

        def _load_config(self, path: Path) -> None:
            try:
                result = self.controller.load_config(path)
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Load failed", str(exc))
                return
            self._show_candidate_issues()
            if result.activated:
                self.plot.clear()
                self.preview_table.setRowCount(0)
                self._refresh_tree()
                self._refresh_sequence_resource_choices()
                self._refresh_operator_parameters()
                self._refresh_sequence_sweep()
                self._clear_table(self.resource_table)
                status = "Loaded with warnings" if result.warnings else "Loaded"
                self._log(f"{status}: {path}")
            else:
                active = self.controller.config_path
                retained = f" Previous active config retained: {active}." if active else " No active config is available."
                self._log(f"Load blocked: {path}.{retained}")
                QtWidgets.QMessageBox.critical(
                    self,
                    "Load blocked",
                    f"{len(result.errors)} error(s) blocked activation.{retained}\nSee Preflight Issues for details.",
                )
            self.prepare_action.setEnabled(self.controller.has_active_config)
            self.start_action.setEnabled(self.controller.has_active_config)

        def _show_candidate_issues(self) -> None:
            self.issue_table.setRowCount(0)
            for issue in self.controller.candidate_issues():
                row = self.issue_table.rowCount()
                self.issue_table.insertRow(row)
                values = (issue.severity, issue.code, issue.location, issue.message, issue.hint)
                for column, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    item.setToolTip(f"{issue.location}\n{issue.message}\n{issue.hint}".strip())
                    item.setData(_user_role(), issue.workflow_path)
                    self.issue_table.setItem(row, column, item)

        def _focus_issue(self, row: int, _column: int) -> None:
            item = self.issue_table.item(row, 0)
            path = item.data(_user_role()) if item is not None else None
            if not path:
                return
            iterator = QtWidgets.QTreeWidgetItemIterator(self.workflow_tree)
            while iterator.value():
                tree_item = iterator.value()
                node = tree_item.data(0, _user_role())
                if node is not None and tuple(node.path) == tuple(path):
                    self.workflow_tree.setCurrentItem(tree_item)
                    self.workflow_tree.scrollToItem(tree_item)
                    return
                iterator += 1

        def _refresh_tree(self) -> None:
            self.workflow_tree.clear()
            root = self.controller.workflow_tree()
            for node in root.children:
                self.workflow_tree.addTopLevelItem(self._tree_item(node))
            self.workflow_tree.expandAll()

        def _tree_item(self, node: WorkflowNode) -> Any:
            item = QtWidgets.QTreeWidgetItem([node.label, node.kind, "yes" if node.enabled else "no"])
            item.setData(0, _user_role(), node)
            if not node.enabled:
                item.setForeground(0, QtGui.QBrush(QtGui.QColor("#9ca3af")))
            for child in node.children:
                item.addChild(self._tree_item(child))
            return item

        def _on_tree_selection(self) -> None:
            items = self.workflow_tree.selectedItems()
            self.selected_node = items[0].data(0, _user_role()) if items else None
            self._rebuild_inspector()

        def _rebuild_inspector(self) -> None:
            while self.inspector_form.rowCount():
                self.inspector_form.removeRow(0)
            self.inspector_widgets = {}
            node = self.selected_node
            self._sync_builder_sequence_settings(node)
            if node is None or node.kind in {"root", "setup", "procedure", "cleanup"}:
                self.inspector_form.addRow(QtWidgets.QLabel("Select a workflow step."))
                return

            enabled = QtWidgets.QCheckBox()
            enabled.setChecked(node.enabled)
            self.inspector_widgets["enabled"] = enabled
            self.inspector_form.addRow("enabled", enabled)

            if node.kind == "scan":
                self._add_line("name", str(node.data.get("name", "scan")))
                values = node.data.get("values", {})
                values_type = QtWidgets.QComboBox()
                values_type.addItems(["linspace", "range", "explicit"])
                values_type.setCurrentText("explicit" if isinstance(values, list) else "range" if "step" in values else "linspace")
                self.inspector_widgets["values_type"] = values_type
                self.inspector_form.addRow("values type", values_type)
                if isinstance(values, list):
                    self._add_line("values", format_parameter_value(values))
                else:
                    for key in ("start", "stop", "points", "step"):
                        self._add_line(key, "" if key not in values else str(values[key]))
            elif node.kind == "average":
                self._add_line("name", str(node.data.get("name", "avg")))
                self._add_line("count", str(node.data.get("count", 1)))
            elif node.kind == "call":
                self._add_line("call", str(node.data.get("call") or ""))
                self._add_line("save_as", "" if node.data.get("save_as") is None else str(node.data.get("save_as")))
                table = QtWidgets.QTableWidget(0, 3)
                table.setHorizontalHeaderLabels(["key", "value", "type"])
                for key, value in (node.data.get("args") or {}).items():
                    row = table.rowCount()
                    table.insertRow(row)
                    table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(key)))
                    table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(value)))
                    table.setItem(row, 2, QtWidgets.QTableWidgetItem(_arg_type(value)))
                table.horizontalHeader().setStretchLastSection(True)
                table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
                self.inspector_widgets["args"] = table
                self.inspector_form.addRow("args", table)
                arg_buttons = QtWidgets.QHBoxLayout()
                add_arg = QtWidgets.QPushButton("Add Arg / 添加参数")
                delete_arg = QtWidgets.QPushButton("Delete Selected Arg / 删除参数")
                add_arg.setObjectName("accentButton")
                delete_arg.setObjectName("dangerButton")
                add_arg.clicked.connect(lambda: table.insertRow(table.rowCount()))
                delete_arg.clicked.connect(lambda: self._delete_selected_arg_rows(table))
                arg_buttons.addWidget(add_arg)
                arg_buttons.addWidget(delete_arg)
                arg_buttons.addStretch(1)
                self.inspector_form.addRow("", arg_buttons)
            elif node.kind == "measurement":
                self._add_line("name", str(node.data.get("name", "measurement")))
            elif node.kind == "run":
                self._add_line("name", str(node.data.get("name", "run")))
                self._add_line("timeout_s", "" if node.data.get("timeout_s") is None else str(node.data.get("timeout_s")))

        def _add_line(self, key: str, value: str) -> None:
            line = QtWidgets.QLineEdit(value)
            self.inspector_widgets[key] = line
            self.inspector_form.addRow(key, line)

        def _apply_inspector(self) -> None:
            node = self.selected_node
            if node is None or node.kind in {"root", "setup", "procedure", "cleanup"}:
                return
            try:
                patch = self._inspector_patch(node)
                self.controller.update_workflow_node(node.path, patch)
                self._refresh_tree()
                self._refresh_operator_parameters()
                self._log(f"Updated {node.kind}: {node.label}")
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Update failed", str(exc))

        def _sync_builder_sequence_settings(self, node: WorkflowNode | None) -> None:
            if not hasattr(self, "builder_sequence_box"):
                return
            is_load_sequence = bool(node and node.kind == "call" and _is_asg_load_sequence(node.data.get("call")))
            self.builder_sequence_box.setVisible(is_load_sequence)
            if not is_load_sequence or node is None:
                return
            args = node.data.get("args") if isinstance(node.data.get("args"), dict) else {}
            sequence_file = args.get("sequence_file") or args.get("path") or args.get("sequence_path") or ""
            self.sequence_settings_label.setText(f"{node.data.get('call')} at {'/'.join(str(part) for part in node.path)}")
            self.sequence_path_line.setText(str(sequence_file))

        def _inspector_patch(self, node: WorkflowNode) -> dict[str, Any]:
            enabled = bool(self.inspector_widgets["enabled"].isChecked())
            patch: dict[str, Any] = {"enabled": enabled}
            if node.kind == "scan":
                values_type = self.inspector_widgets["values_type"].currentText()
                if values_type == "explicit":
                    values = parse_parameter_value(self.inspector_widgets.get("values", QtWidgets.QLineEdit("")).text(), "list")
                elif values_type == "range":
                    values = {
                        "start": parse_parameter_value(self.inspector_widgets["start"].text(), "number"),
                        "stop": parse_parameter_value(self.inspector_widgets["stop"].text(), "number"),
                        "step": parse_parameter_value(self.inspector_widgets["step"].text(), "number"),
                    }
                else:
                    values = {
                        "start": parse_parameter_value(self.inspector_widgets["start"].text(), "number"),
                        "stop": parse_parameter_value(self.inspector_widgets["stop"].text(), "number"),
                        "points": parse_parameter_value(self.inspector_widgets["points"].text(), "int"),
                    }
                patch["scan"] = {"name": self.inspector_widgets["name"].text(), "values": values}
            elif node.kind == "average":
                patch["average"] = {
                    "name": self.inspector_widgets["name"].text(),
                    "count": parse_parameter_value(self.inspector_widgets["count"].text(), "int"),
                }
            elif node.kind == "call":
                save_as = self.inspector_widgets["save_as"].text().strip()
                args = self._args_from_table(self.inspector_widgets["args"])
                patch["call"] = self.inspector_widgets["call"].text().strip()
                patch["args"] = args
                if save_as:
                    patch["save_as"] = save_as
                elif "save_as" in node.data:
                    patch["save_as"] = None
            elif node.kind == "measurement":
                patch["measurement"] = {"name": self.inspector_widgets["name"].text().strip()}
            elif node.kind == "run":
                run_patch: dict[str, Any] = {"name": self.inspector_widgets["name"].text().strip()}
                timeout_text = self.inspector_widgets["timeout_s"].text().strip()
                if timeout_text:
                    run_patch["timeout_s"] = parse_parameter_value(timeout_text, "number")
                patch["run"] = run_patch
            return patch

        def _args_from_table(self, table: Any) -> dict[str, Any]:
            args: dict[str, Any] = {}
            for row in range(table.rowCount()):
                key_item = table.item(row, 0)
                value_item = table.item(row, 1)
                type_item = table.item(row, 2)
                if key_item is None or not key_item.text().strip():
                    continue
                value_text = "" if value_item is None else value_item.text().strip()
                value_type = "string" if type_item is None else type_item.text().strip().lower()
                if value_type == "number":
                    value = parse_parameter_value(value_text, "number")
                elif value_type == "ref":
                    name = value_text[2:-1] if value_text.startswith("${") and value_text.endswith("}") else value_text
                    value = f"${{{name}}}"
                else:
                    value = value_text
                args[key_item.text().strip()] = value
            return args

        def _delete_selected_arg_rows(self, table: Any) -> None:
            selected_rows = sorted({index.row() for index in table.selectedIndexes()}, reverse=True)
            if not selected_rows and table.rowCount() > 0:
                selected_rows = [table.rowCount() - 1]
            for row in selected_rows:
                table.removeRow(row)

        def _add_step(self, kind: str) -> None:
            try:
                parent_path = self._selected_parent_path()
                self.controller.add_workflow_step(parent_path, make_default_step(kind))
                self._refresh_tree()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Add failed", str(exc))

        def _duplicate_step(self) -> None:
            if self.selected_node is None or self.selected_node.kind in {"setup", "procedure", "cleanup", "root"}:
                return
            self.controller.duplicate_workflow_step(self.selected_node.path)
            self._refresh_tree()

        def _delete_step(self) -> None:
            if self.selected_node is None or self.selected_node.kind in {"setup", "procedure", "cleanup", "root"}:
                return
            self.controller.delete_workflow_step(self.selected_node.path)
            self._refresh_tree()

        def _selected_parent_path(self) -> tuple[Any, ...]:
            node = self.selected_node
            if node is None:
                return ("procedure",)
            if node.kind in {"setup", "procedure", "cleanup"}:
                return node.path
            if node.kind in {"scan", "average", "measurement"}:
                return (*node.path, node.kind, "body")
            if node.kind == "run":
                return (*node.path, "run", "steps")
            if node.kind == "cleanup":
                return (*node.path, "cleanup", "steps")
            return node.path[:-1]

        def _prepare(self) -> bool:
            try:
                view = self.controller.prepare()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Prepare failed", str(exc))
                return False
            self._show_preflight(view)
            self.controller.reset_live_state()
            self._live_signature = None
            self._refresh_live_models()
            self._refresh_sequence_sweep()
            self._log("Preflight OK" if view.ok else "Preflight has errors")
            return view.ok

        def _show_preflight(self, view: Any) -> None:
            self.resource_table.setRowCount(0)
            for resource in view.resources:
                row = self.resource_table.rowCount()
                self.resource_table.insertRow(row)
                for column, value in enumerate((resource.name, resource.adapter, resource.simulation, resource.connected)):
                    self.resource_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
            self.issue_table.setRowCount(0)
            for issue in view.issues:
                row = self.issue_table.rowCount()
                self.issue_table.insertRow(row)
                for column, value in enumerate((issue.severity, issue.code, issue.location, issue.message, issue.hint)):
                    self.issue_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
            self._show_sequence_snapshot(view.sequence_snapshots)

        def _refresh_sequence_resource_choices(self) -> None:
            names = self.controller.sequence_resource_names()
            self.sequence_resource_combo.blockSignals(True)
            self.sequence_resource_combo.clear()
            self.sequence_resource_combo.addItems(names)
            self.sequence_resource_combo.blockSignals(False)
            self._refresh_sequence_panel()

        def _selected_sequence_resource(self) -> str:
            text = self.sequence_resource_combo.currentText().strip()
            return text

        def _apply_sequence_file(self) -> None:
            resource = self._selected_sequence_resource()
            if not resource and self._selected_load_sequence_node() is None:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Sequence update unavailable",
                    "No ASG/sequence resource exists in the current config.",
                )
                return
            try:
                sequence_file = self.sequence_path_line.text().strip()
                if self._selected_load_sequence_node() is not None:
                    self._update_selected_load_sequence_file(sequence_file)
                else:
                    self.controller.update_sequence_file(resource, sequence_file)
                self._watch_sequence_file(self.sequence_path_line.text().strip())
                self._refresh_tree()
                self._refresh_operator_parameters()
                self._refresh_sequence_panel()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Sequence update failed", str(exc))

        def _browse_sequence_file(self) -> None:
            current = self.sequence_path_line.text().strip() or str(PROJECT_ROOT)
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select ASG sequence file", current, "Sequence files (*.seq *.json *.yaml *.yml *.txt);;All files (*)"
            )
            if path:
                self.sequence_path_line.setText(path)
                self._apply_sequence_file()

        def _open_sequence_editor(self) -> None:
            self._open_sequence_editor_for_path(self.sequence_path_line.text())

        def _open_sequence_editor_for_path(self, sequence_file: str) -> None:
            sequence_path = self._sequence_editor_target_path(sequence_file)
            result = open_sequence_editor(default_sequence_editor_path(PROJECT_ROOT), sequence_path, capture_output=True)
            self._log(f"Sequence editor: {result.message}")
            if not result.ok:
                QtWidgets.QMessageBox.warning(self, "Sequence editor", result.message)
            else:
                self._watch_sequence_file(str(sequence_path))
                self._refresh_sequence_panel()
                self._log(f"Sequence editor pid: {result.pid}")
                if result.process is not None:
                    thread = threading.Thread(
                        target=self._sequence_editor_monitor,
                        args=(result.process, str(sequence_path)),
                        daemon=True,
                    )
                    thread.start()

        def _sequence_editor_target_path(self, sequence_file: str) -> Path:
            raw_path = sequence_file.strip()
            if raw_path:
                path = resolve_project_path(raw_path) or (PROJECT_ROOT / raw_path)
            else:
                path = PROJECT_ROOT / "configs" / "sequences" / "operator_sequence.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(json.dumps(_default_sequence_channels(), indent=2), encoding="utf-8")
            if self._selected_load_sequence_node() is not None:
                self._update_selected_load_sequence_file(str(path))
            else:
                resource = self._selected_sequence_resource()
                if not resource:
                    raise ValueError("No ASG/sequence resource exists in the current config.")
                self.controller.update_sequence_file(resource, str(path))
            if hasattr(self, "sequence_path_line"):
                self.sequence_path_line.setText(str(path))
            self._refresh_tree()
            self._refresh_operator_parameters()
            return path

        def _selected_load_sequence_node(self) -> WorkflowNode | None:
            node = self.selected_node
            if node is not None and node.kind == "call" and _is_asg_load_sequence(node.data.get("call")):
                return node
            return None

        def _update_selected_load_sequence_file(self, sequence_file: str) -> None:
            node = self._selected_load_sequence_node()
            if node is None:
                return
            args = dict(node.data.get("args") or {})
            args["sequence_file"] = sequence_file
            args.pop("path", None)
            args.pop("sequence_path", None)
            self.controller.update_workflow_node(node.path, {"args": args})
            self.selected_node = None

        def _sequence_editor_monitor(self, process: Any, sequence_path: str) -> None:
            try:
                stdout, stderr = process.communicate()
                self.event_queue.put(("sequence_editor_done", sequence_path, stdout, stderr, process.returncode))
            except Exception as exc:
                self.event_queue.put(("sequence_editor_done", sequence_path, "", str(exc), -1))

        def _on_sequence_file_changed(self, path: str) -> None:
            self._watch_sequence_file(path)
            self._refresh_sequence_panel()
            self._refresh_operator_parameters()
            self._log(f"Sequence file updated: {path}")

        def _watch_sequence_file(self, path: str) -> None:
            if not path:
                return
            resolved = resolve_project_path(path)
            if resolved is None:
                return
            path = str(resolved)
            existing = set(self.sequence_watcher.files())
            if path not in existing and Path(path).exists():
                self.sequence_watcher.addPath(path)

        def _refresh_sequence_panel(self) -> None:
            resource = self._selected_sequence_resource()
            if not resource:
                self.sequence_path_line.clear()
                self.sequence_metadata.setPlainText("No ASG/sequence resource is configured for this experiment.")
                return
            try:
                snapshots = self.controller.inspect_sequence_references()
                resource_snapshot = self.controller.inspect_sequence_resource(resource)
            except Exception as exc:
                self.sequence_metadata.setPlainText(f"Sequence status unavailable: {exc}")
                return
            if self._selected_load_sequence_node() is None and self.sequence_path_line.text().strip() != resource_snapshot.sequence_file:
                self.sequence_path_line.setText(resource_snapshot.sequence_file)
            self._show_sequence_snapshot(snapshots)

        def _show_sequence_snapshot(self, snapshots: Any) -> None:
            if self.sequence_metadata is None:
                return
            selected = self._selected_sequence_resource()
            selected_snapshots = [item for item in snapshots if item.resource == selected]
            if not selected_snapshots:
                self.sequence_metadata.setPlainText(
                    "\n".join(
                        [
                            f"resource: {selected}",
                            "No file-backed sequence reference is configured.",
                            "Set resources.<asg>.sequence_file or select an asg.load_sequence step and set args.sequence_file.",
                            "Legacy args.sequence names are workflow labels only and cannot be previewed as files.",
                        ]
                    )
                )
                return
            lines: list[str] = []
            for index, snapshot in enumerate(selected_snapshots, start=1):
                if index > 1:
                    lines.append("")
                lines.extend(
                    [
                        f"[{index}] {snapshot.label or snapshot.reference_id or snapshot.resource}",
                        f"source: {snapshot.source or 'resource'}",
                        f"path: {snapshot.sequence_file or '(not configured)'}",
                        f"exists: {snapshot.exists}",
                        f"size: {snapshot.size_bytes if snapshot.size_bytes is not None else 'unknown'}",
                        f"sha256: {snapshot.sha256 or 'unavailable'}",
                        f"parameters: {', '.join(snapshot.parameters) if snapshot.parameters else '(none detected)'}",
                        f"channels: {', '.join(snapshot.channels) if snapshot.channels else '(none detected)'}",
                    ]
                )
                if snapshot.preview_lines:
                    lines.append("preview:")
                    lines.extend(f"- {line}" for line in snapshot.preview_lines)
                if snapshot.sequence_params:
                    lines.append(f"sequence_params: {snapshot.sequence_params}")
                if snapshot.warnings:
                    lines.append("warnings:")
                    lines.extend(f"- {warning}" for warning in snapshot.warnings)
            self.sequence_metadata.setPlainText("\n".join(lines))

        def _refresh_operator_parameters(self) -> None:
            if not hasattr(self, "operator_parameters_form"):
                return
            while self.operator_parameters_form.rowCount():
                self.operator_parameters_form.removeRow(0)
            self.operator_parameter_widgets = {}
            try:
                specs = self.controller.get_operator_parameters()
            except Exception as exc:
                self.operator_parameters_form.addRow(QtWidgets.QLabel(f"Parameters unavailable: {exc}"))
                return
            if not specs:
                self.operator_parameters_form.addRow(QtWidgets.QLabel("No operator parameters discovered."))
                return
            for spec in specs:
                widget = self._operator_parameter_widget(spec)
                label = spec.label
                if spec.unit:
                    label = f"{label} ({spec.unit})"
                if spec.warning:
                    label = f"{label} !"
                    widget.setToolTip(spec.warning)
                self.operator_parameter_widgets[spec.name] = widget
                self.operator_parameters_form.addRow(label, widget)

        def _operator_parameter_widget(self, spec: Any) -> Any:
            value = spec.value
            if spec.choices:
                combo = QtWidgets.QComboBox()
                for choice in spec.choices:
                    combo.addItem(str(choice), choice)
                combo.setCurrentText(str(value))
                combo.setEnabled(not spec.readonly)
                return combo
            if spec.widget == "bool" or isinstance(value, bool):
                checkbox = QtWidgets.QCheckBox()
                checkbox.setChecked(bool(value))
                checkbox.setEnabled(not spec.readonly)
                return checkbox
            if spec.widget == "file_picker":
                row = QtWidgets.QWidget()
                layout = QtWidgets.QHBoxLayout(row)
                layout.setContentsMargins(0, 0, 0, 0)
                line = QtWidgets.QLineEdit(format_parameter_value(value))
                line.setReadOnly(bool(spec.readonly))
                browse = QtWidgets.QPushButton("Browse / 浏览")
                open_editor = QtWidgets.QPushButton("Open Editor / 打开编辑器")
                browse.setEnabled(not spec.readonly)
                browse.clicked.connect(lambda checked=False, target=line: self._browse_operator_file(target))
                open_editor.clicked.connect(lambda checked=False, target=line: self._open_sequence_editor_for_path(target.text()))
                layout.addWidget(line, 1)
                layout.addWidget(browse)
                layout.addWidget(open_editor)
                row._value_widget = line
                return row
            line = QtWidgets.QLineEdit(format_parameter_value(value))
            if spec.minimum is not None or spec.maximum is not None:
                line.setPlaceholderText(f"{spec.minimum or ''} .. {spec.maximum or ''}")
            line.setReadOnly(bool(spec.readonly))
            return line

        def _apply_operator_parameters(self) -> None:
            try:
                for name, widget in self.operator_parameter_widgets.items():
                    self.controller.apply_operator_parameter(name, self._operator_parameter_value(widget))
                self._refresh_tree()
                self._refresh_sequence_resource_choices()
                self._refresh_operator_parameters()
                self._log("Updated operator parameters.")
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Operator parameter update failed", str(exc))

        def _operator_parameter_value(self, widget: Any) -> Any:
            if isinstance(widget, QtWidgets.QCheckBox):
                return widget.isChecked()
            if isinstance(widget, QtWidgets.QComboBox):
                data = widget.currentData()
                return widget.currentText() if data is None else data
            if hasattr(widget, "_value_widget"):
                return widget._value_widget.text()
            return widget.text()

        def _browse_operator_file(self, line: Any) -> None:
            current = line.text().strip() or str(PROJECT_ROOT)
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select ASG sequence file", current, "Sequence files (*.seq *.json *.yaml *.yml *.txt);;All files (*)"
            )
            if path:
                line.setText(path)

        def _start(self) -> None:
            if self.running:
                self._log("Start ignored: dry-run is already running.")
                return
            if not self._prepare():
                return
            self.running = True
            self.start_action.setEnabled(False)
            self.plot.clear()
            self.preview_table.setRowCount(0)
            hardware_run = bool(
                self.controller.parsed
                and any(not getattr(resource, "simulation", True) for resource in self.controller.parsed.context.resources.values())
            )
            self._active_hardware_run = hardware_run
            self._log("Starting hardware run..." if hardware_run else "Starting dry-run...")
            thread = threading.Thread(target=self._run_worker, daemon=True)
            thread.start()

        def _run_worker(self) -> None:
            try:
                if getattr(self, "_active_hardware_run", False):
                    result = self.controller.start_hardware_run(event_callback=self.event_queue.put)
                else:
                    result = self.controller.start_dry_run(event_callback=self.event_queue.put)
                self.event_queue.put(("run_result", result))
            except Exception as exc:
                self.event_queue.put(("error", exc))

        def _stop(self) -> None:
            if self.running:
                self._log("Stop requested: current dry-run executor does not support reliable mid-run cancellation yet.")
            else:
                self._log("Stop is idle: no dry-run is running.")

        def _drain_events(self) -> None:
            changed = False
            try:
                for _ in range(200):
                    item = self.event_queue.get_nowait()
                    if isinstance(item, Event):
                        changed = True
                        self._log(_event_to_log_line(item))
                    elif isinstance(item, tuple) and item[0] == "run_result":
                        result = item[1]
                        self._log(f"Run path: {result.run_path}")
                        self._log(f"RunCompleted {result.status}")
                        self.viewer_panel.open_run(result.run_path, backend="auto")
                        changed = True
                        self.running = False
                        self.start_action.setEnabled(True)
                    elif isinstance(item, tuple) and item[0] == "sequence_editor_done":
                        self._handle_sequence_editor_done(item)
                    elif isinstance(item, tuple) and item[0] == "sequence_prepare":
                        self._finish_sequence_prepare(item[1], item[2])
                    elif isinstance(item, tuple) and item[0] == "error":
                        self._log(f"ERROR {item[1]}")
                        self.running = False
                        self.start_action.setEnabled(True)
            except queue.Empty:
                pass
            if changed:
                self._refresh_live_models()

        def _handle_sequence_editor_done(self, item: tuple[Any, ...]) -> None:
            _, sequence_path, stdout, stderr, returncode = item
            if stdout and stdout.strip():
                try:
                    params = json.loads(stdout)
                except json.JSONDecodeError:
                    self._log("Sequence editor returned non-JSON output; file watcher refresh was used instead.")
                else:
                    Path(sequence_path).write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
                    self._log(f"Sequence editor output saved: {sequence_path}")
            if stderr and stderr.strip():
                self._log(f"Sequence editor stderr: {stderr.strip()}")
            self._watch_sequence_file(sequence_path)
            self._refresh_sequence_panel()
            self._refresh_operator_parameters()
            self._log(f"Sequence editor exited: {returncode}")

        def _refresh_live_models(self) -> None:
            if not hasattr(self, "live_source_table"):
                return
            specs = self.controller.list_live_data_specs()
            selection = self.controller.get_live_selection()
            signature = tuple((spec.key, spec.source_kind, spec.data_kind, spec.unit, spec.dims, spec.saved, spec.status, spec.error)
                              for spec in specs)
            dims: list[str] = []
            if signature != self._live_signature:
                self.live_source_table.blockSignals(True); self.live_source_table.setRowCount(0)
                for spec in specs:
                    row = self.live_source_table.rowCount(); self.live_source_table.insertRow(row)
                    show = QtWidgets.QTableWidgetItem(); show.setFlags(show.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    show.setCheckState(QtCore.Qt.CheckState.Checked if spec.key in selection.keys else QtCore.Qt.CheckState.Unchecked)
                    show.setData(_user_role(), (spec.source_kind, spec.key)); self.live_source_table.setItem(row, 0, show)
                    values = (spec.key, spec.source_kind, spec.data_kind, spec.unit or "-", spec.status,
                              "saved" if spec.saved else "live-only")
                    for column, value in enumerate(values, start=1):
                        item = QtWidgets.QTableWidgetItem(str(value)); item.setToolTip(spec.error or ""); self.live_source_table.setItem(row, column, item)
                self.live_source_table.blockSignals(False); self._live_signature = signature; self._apply_live_filter()
            for spec in specs:
                for dim in spec.dims:
                    if dim not in {"time_s", "sample_index", "channel"} and dim not in dims: dims.append(dim)
            for combo in (self.live_x_dim, self.live_y_dim):
                current = combo.currentText(); combo.blockSignals(True); combo.clear(); combo.addItems(dims)
                if current in dims: combo.setCurrentText(current)
                elif combo is self.live_y_dim and len(dims) > 1: combo.setCurrentIndex(1)
                combo.blockSignals(False)
            points = self.controller.list_live_points(); point_ids = [str(point["point_id"]) for point in points]
            current_point = self.live_point.currentText(); self.live_point.blockSignals(True); self.live_point.clear(); self.live_point.addItems(point_ids)
            target = point_ids[-1] if self.live_auto_follow.isChecked() and point_ids else current_point
            if target in point_ids: self.live_point.setCurrentText(target)
            self.live_point.blockSignals(False)
            self._refresh_live_selectors(specs, points)
            self._fill_live_table(points)
            statuses = self.controller.get_analysis_statuses(); self.analysis_status_table.setRowCount(0)
            for status in statuses:
                row = self.analysis_status_table.rowCount(); self.analysis_status_table.insertRow(row)
                latency = "" if status.last_latency_s is None else f"{status.last_latency_s * 1000:.2f} ms"
                queue_text = f"{status.queue_depth}/{status.queue_capacity or '-'} drop={status.dropped} {status.worker_state}"
                for column, value in enumerate((status.module, status.state, latency, queue_text)):
                    self.analysis_status_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
            sequence = self.controller.get_current_sequence_context()
            self.live_sequence_context.setPlainText("\n".join([
                f"mode: {sequence.mode}", f"plan: {sequence.plan_id or '-'}", f"bundle: {sequence.bundle_id or '-'}",
                f"entry: {sequence.entry_id or '-'}", f"coords: {sequence.resolved_coordinates or {}}",
                f"sequence sha256: {(sequence.sequence_sha256 or '-')[:16]}", f"status: {sequence.status}",
            ]))
            if not self.live_pause.isChecked(): self._render_live_plot()

        def _selected_live_keys(self) -> tuple[str, ...]:
            return tuple(self.live_source_table.item(row, 1).text() for row in range(self.live_source_table.rowCount())
                         if self.live_source_table.item(row, 0).checkState() == QtCore.Qt.CheckState.Checked)

        def _live_source_changed(self, item: Any) -> None:
            if item.column() != 0: return
            self._live_controls_changed()

        def _live_controls_changed(self, *args: Any) -> None:
            if not hasattr(self, "live_pause"): return
            self._refresh_live_selectors(self.controller.list_live_data_specs(), self.controller.list_live_points())
            if not self.live_pause.isChecked(): self._render_live_plot()
            else:
                try: self.controller.set_live_selection(self._selected_live_keys(), **self._live_selection_kwargs())
                except Exception as exc: self.live_plot_status.setText(str(exc))

        def _live_selection_kwargs(self) -> dict[str, Any]:
            return {
                "plot_type": self.live_plot_type.currentText().lower(),
                "x_dim": self.live_x_dim.currentText() or None,
                "y_dim": self.live_y_dim.currentText() or None,
                "selectors": {dim: widget.currentData() for dim, widget in self.live_selector_widgets.items()
                              if widget.currentIndex() >= 0},
                "point_id": self.live_point.currentText() or None,
                "channel": self.live_channel.currentData() if self.live_channel.currentIndex() >= 0 else None,
            }

        def _render_live_plot(self) -> None:
            keys = self._selected_live_keys()
            if not keys:
                self.controller.set_live_selection((), plot_type="auto"); self.plot.set_message("No live data selected")
                self.live_plot_status.setText("No live data selected"); return
            options = self._live_selection_kwargs(); point = options["point_id"]
            try:
                selected = self.controller.set_live_selection(keys, **options)
                data = self.controller.get_live_plot_data(selected)
                if selected.plot_type == "line":
                    series = [LineSeriesView(item.key, item.x, item.y) for item in data]
                    if not any(len(item.x) for item in data): raise ValueError("Waiting for selected scalar data")
                    self.plot.set_lines(" / ".join(keys), series)
                elif selected.plot_type == "heatmap":
                    if not data.values.size: raise ValueError("Waiting for heatmap points")
                    self.plot.set_heatmap(data.key, data.x, data.y, data.values)
                elif selected.plot_type == "trace":
                    self.plot.set_line(f"{data.key} @ {point}", data.time, data.values)
                else:
                    self.plot.set_message("Table diagnostic view")
                self.live_plot_status.setText(f"{selected.plot_type} · {len(self.controller.list_live_points())} buffered points · {self.plot.backend_name}")
            except Exception as exc:
                self.plot.set_message(str(exc)); self.live_plot_status.setText(str(exc))

        def _refresh_live_selectors(self, specs: tuple[Any, ...], points: tuple[dict[str, Any], ...]) -> None:
            keys = self._selected_live_keys(); selected = next((spec for spec in specs if spec.key in keys), None)
            displayed = {self.live_x_dim.currentText(), "sample_index", "time_s", "channel"}
            if self.live_plot_type.currentText().lower() in {"heatmap", "auto"}: displayed.add(self.live_y_dim.currentText())
            wanted = [dim for dim in (selected.dims if selected else ()) if dim not in displayed]
            if set(wanted) != set(self.live_selector_widgets):
                while self.live_selector_form.rowCount(): self.live_selector_form.removeRow(0)
                self.live_selector_widgets = {}
                for dim in wanted:
                    combo = QtWidgets.QComboBox()
                    for value in dict.fromkeys(point["coords"].get(dim) for point in points if dim in point["coords"]): combo.addItem(str(value), value)
                    combo.currentTextChanged.connect(self._live_controls_changed); self.live_selector_widgets[dim] = combo; self.live_selector_form.addRow(dim, combo)
            channels = []
            if selected and selected.data_kind == "matrix":
                for point in reversed(points):
                    if selected.key in point["data"]:
                        channels = list(range(len(point["data"][selected.key]))); break
            current = self.live_channel.currentData(); self.live_channel.blockSignals(True); self.live_channel.clear()
            for value in channels: self.live_channel.addItem(str(value), value)
            if current in channels: self.live_channel.setCurrentIndex(channels.index(current))
            self.live_channel.blockSignals(False)

        def _fill_live_table(self, points: tuple[dict[str, Any], ...]) -> None:
            self.preview_table.setRowCount(0)
            for point in points[-200:]:
                row = self.preview_table.rowCount(); self.preview_table.insertRow(row)
                summary = {key: _value_summary(value) for key, value in point["data"].items()}
                for column, value in enumerate((point["point_id"], point["coords"], summary)):
                    self.preview_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))

        def _apply_live_filter(self, *args: Any) -> None:
            needle = self.live_source_filter.text().strip().lower()
            for row in range(self.live_source_table.rowCount()):
                text = " ".join(self.live_source_table.item(row, column).text() for column in range(1, 7))
                self.live_source_table.setRowHidden(row, needle not in text.lower())

        def _clear_live_display(self) -> None:
            self.controller.clear_live_display(); self.preview_table.setRowCount(0); self.plot.clear(); self.live_plot_status.setText("Display cleared; run ingestion and storage continue")

        def _log(self, line: str) -> None:
            self.log.appendPlainText(line)

        @staticmethod
        def _clear_table(table: Any) -> None:
            table.setRowCount(0)


else:

    class PyQtOperatorWindow:  # pragma: no cover - exercised through qt_compat fallback
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(missing_qt_message())


def _event_to_log_line(event: Event) -> str:
    if event.type == "RunStarted":
        return f"RunStarted {getattr(event, 'procedure_name', '')}"
    if event.type == "ParameterChanged":
        return f"ParameterChanged {getattr(event, 'name', '')}={getattr(event, 'value', '')}"
    if event.type == "MeasurementStarted":
        return f"MeasurementStarted {getattr(event, 'point_id', '')} coords={getattr(event, 'coords', {})}"
    if event.type == "DataPoint":
        return f"DataPoint {getattr(event, 'point_id', '')} data={getattr(event, 'data', {})}"
    if event.type == "MeasurementCompleted":
        return f"MeasurementCompleted {getattr(event, 'point_id', '')} {getattr(event, 'status', '')}"
    if event.type == "RunCompleted":
        return f"RunCompleted {getattr(event, 'status', '')}"
    if event.type == "ErrorRaised":
        return f"ErrorRaised {getattr(event, 'error_type', '')}: {getattr(event, 'message', '')}"
    return event.type


def _arg_type(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return "ref"
    return "string"


def _value_summary(value: Any) -> str:
    try:
        import numpy as np
        array = np.asarray(value)
        if array.ndim: return f"{array.dtype} {tuple(array.shape)}"
    except Exception:
        pass
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


def _user_role() -> Any:
    return getattr(QtCore.Qt.ItemDataRole, "UserRole", None) or QtCore.Qt.UserRole


def _item_is_editable() -> Any:
    return getattr(QtCore.Qt.ItemFlag, "ItemIsEditable", None) or QtCore.Qt.ItemIsEditable


def _align_center() -> Any:
    return getattr(QtCore.Qt.AlignmentFlag, "AlignCenter", None) or QtCore.Qt.AlignCenter


def _horizontal() -> Any:
    return getattr(QtCore.Qt.Orientation, "Horizontal", None) or QtCore.Qt.Horizontal


def _vertical() -> Any:
    return getattr(QtCore.Qt.Orientation, "Vertical", None) or QtCore.Qt.Vertical


def _experiment_config_paths() -> list[Path]:
    directory = PROJECT_ROOT / "configs" / "experiments"
    paths = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
    return paths or [DEFAULT_CONFIG]


def _is_asg_load_sequence(action: Any) -> bool:
    resource, _, method = str(action or "").partition(".")
    return method == "load_sequence" and "asg" in resource.lower()


def _default_sequence_channels() -> list[dict[str, Any]]:
    return [
        {
            "channel_name": f"Channel {index + 1}",
            "delay_off": 0.0,
            "pulses": [],
            "pbn": index,
        }
        for index in range(4)
    ]
