"""Optional Qt guided sequence authoring widget and timeline renderer."""
from __future__ import annotations
import threading
from pathlib import Path
from typing import Any, Callable

import yaml

from .sequence_authoring import AUTHORING_STEPS, NormalizedPreview
from .sequence_bridge import default_sequence_editor_path, run_sequence_editor_protocol
from qulab.paths import resolve_project_path

STEP_LABELS = (
    "1 Resource & Mode", "2 Source", "3 Channel & Trigger Roles", "4 Fixed Parameters",
    "5 Sweep Parameters", "6 Targets & Propagation", "7 Preview & Compare",
    "8 Validate & Prepare", "9 Bundle / Workflow / Provenance",
)
GENERIC_STEP_INDICES = (1, 4, 5, 6, 7, 8)

def create_guided_sequence_widget(QtWidgets: Any, QtCore: Any, QtGui: Any, controller: Any,
                                  *, on_config_changed: Callable[[], None] | None = None) -> Any:
    Signal = getattr(QtCore, "Signal", None) or getattr(QtCore, "pyqtSignal")

    class _Bridge(QtCore.QObject):
        editor_finished = Signal(object)
        prepare_finished = Signal(object, object)

    class Timeline(QtWidgets.QWidget):
        pulseSelected = Signal(str, int)
        def __init__(self) -> None:
            super().__init__(); self.preview: NormalizedPreview | None = None; self.comparison: NormalizedPreview | None = None
            self.difference = False; self.selected: tuple[str, int] | None = None; self._pulse_rects: list[tuple[Any, str, int]] = []
            self.setMinimumHeight(220)
        def set_preview(self, preview: NormalizedPreview | None, comparison: NormalizedPreview | None = None,
                        *, difference: bool = False) -> None:
            self.preview = preview; self.comparison = comparison; self.difference = difference
            self.setMinimumHeight(max(180, 76 + 34 * len(preview.channels) if preview else 180)); self.update()
        def paintEvent(self, event: Any) -> None:  # noqa: N802
            painter = QtGui.QPainter(self); painter.fillRect(self.rect(), QtGui.QColor("#ffffff"))
            self._pulse_rects.clear()
            preview = self.preview
            if preview is None or not preview.pulses:
                painter.setPen(QtGui.QColor("#6b7280")); painter.drawText(self.rect(), _align_center(QtCore), "No preview available"); return
            left, right, top, row_h = 110, max(self.width() - 20, 130), 38, 34
            all_pulses = preview.pulses + (self.comparison.pulses if self.comparison else ())
            duration = max(preview.duration_s, max(p.end_s for p in all_pulses), 1e-12)
            baseline = {(p.channel, p.pulse): (p.start_s, p.end_s) for p in self.comparison.pulses} if self.comparison else {}
            painter.setPen(QtGui.QColor("#64748b"))
            axis_bottom = top + len(preview.channels) * row_h
            for tick in range(5):
                ratio = tick / 4; x = left + int(ratio * (right - left)); value = ratio * duration
                painter.drawLine(x, top - 8, x, axis_bottom)
                painter.drawText(max(left, x - 30), top - 14, _format_time(value))
            for row, channel in enumerate(preview.channels):
                y = top + row * row_h; painter.drawText(8, y + 18, channel); painter.drawLine(left, y + 20, right, y + 20)
                if self.comparison:
                    painter.setPen(QtGui.QPen(QtGui.QColor("#94a3b8"), 2))
                    for pulse in (p for p in self.comparison.pulses if p.channel == channel):
                        x = left + int(pulse.start_s / duration * (right - left)); width = max(3, int(pulse.duration_s / duration * (right - left)))
                        painter.drawRect(x, y + 3, width, 26)
                for pulse in (p for p in preview.pulses if p.channel == channel):
                    changed = baseline.get((pulse.channel, pulse.pulse)) != (pulse.start_s, pulse.end_s) if baseline else False
                    if self.difference and not changed: continue
                    x = left + int(pulse.start_s / duration * (right - left)); width = max(3, int(pulse.duration_s / duration * (right - left)))
                    color = "#f59e0b" if self.selected == (pulse.channel, pulse.pulse) else ("#dc2626" if changed else "#2563eb")
                    rect = QtCore.QRect(x, y + 6, width, 20); self._pulse_rects.append((rect, pulse.channel, pulse.pulse))
                    painter.fillRect(rect, QtGui.QColor(color)); painter.setPen(QtGui.QColor("#111827"))
                    painter.drawText(x + 2, y + 20, pulse.label or pulse.alias or str(pulse.pulse))
        def mousePressEvent(self, event: Any) -> None:  # noqa: N802
            position = event.position().toPoint() if hasattr(event, "position") else event.pos()
            for rect, channel, pulse in reversed(self._pulse_rects):
                if rect.contains(position):
                    self.selected = (channel, pulse); self.pulseSelected.emit(channel, pulse); self.update(); break
            super().mousePressEvent(event)

    class GuidedSequenceWidget(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__(); self.selected_plan: str | None = None; self.current_step = 0; self.parameter_widgets: dict[str, dict[str, Any]] = {}
            self._state = None; self._bridge = _Bridge(self); self._bridge.editor_finished.connect(self._editor_done); self._bridge.prepare_finished.connect(self._prepare_done)
            self._watcher = QtCore.QFileSystemWatcher(self); self._watcher.fileChanged.connect(self._template_changed)
            self._build(); self.refresh()

        def _build(self) -> None:
            root = QtWidgets.QVBoxLayout(self); root.setContentsMargins(6, 6, 6, 6)
            toolbar = QtWidgets.QHBoxLayout(); self.plan_combo = QtWidgets.QComboBox(); self.plan_combo.currentTextChanged.connect(self._plan_changed)
            for text, slot in (("New", self._new_plan), ("Duplicate", self._duplicate), ("Delete", self._delete)):
                button = QtWidgets.QPushButton(text); button.clicked.connect(slot); toolbar.addWidget(button)
            self.state_label = QtWidgets.QLabel("No plan"); self.point_label = QtWidgets.QLabel("0 points")
            toolbar.insertWidget(0, self.plan_combo, 1); toolbar.addWidget(self.state_label); toolbar.addWidget(self.point_label); root.addLayout(toolbar)
            split = QtWidgets.QSplitter(_horizontal(QtCore)); self.steps = QtWidgets.QListWidget(); self.steps.setMaximumWidth(210)
            self.steps.currentRowChanged.connect(self._step_changed); split.addWidget(self.steps)
            self.pages = QtWidgets.QStackedWidget(); split.addWidget(self.pages)
            self.issues = QtWidgets.QTableWidget(0, 5); self.issues.setHorizontalHeaderLabels(["Severity", "Code", "Message", "Location", "Hint"])
            self.issues.horizontalHeader().setStretchLastSection(True); self.issues.setMaximumWidth(360); self.issues.cellDoubleClicked.connect(self._issue_clicked); split.addWidget(self.issues)
            split.setSizes([190, 760, 300]); root.addWidget(split, 1)
            self._build_pages()
            footer = QtWidgets.QHBoxLayout(); back = QtWidgets.QPushButton("Back"); nxt = QtWidgets.QPushButton("Next")
            validate = QtWidgets.QPushButton("Validate"); macro = QtWidgets.QPushButton("Insert / Update Macro"); self.prepare_button = QtWidgets.QPushButton("Prepare")
            back.clicked.connect(lambda: self.steps.setCurrentRow(max(0, self.steps.currentRow() - 1))); nxt.clicked.connect(lambda: self.steps.setCurrentRow(min(self.steps.count() - 1, self.steps.currentRow() + 1)))
            validate.clicked.connect(self.refresh); macro.clicked.connect(self._insert_macro); self.prepare_button.clicked.connect(self._prepare)
            for widget in (back, nxt, validate, macro, self.prepare_button): footer.addWidget(widget)
            footer.addStretch(1); root.addLayout(footer)

        def _build_pages(self) -> None:
            self.pages.addWidget(self._mode_page()); self.pages.addWidget(self._source_page()); self.pages.addWidget(self._roles_page())
            self.pages.addWidget(self._parameter_page(False)); self.pages.addWidget(self._parameter_page(True)); self.pages.addWidget(self._targets_page())
            self.pages.addWidget(self._preview_page()); self.pages.addWidget(self._validation_page()); self.pages.addWidget(self._provenance_page())

        def _mode_page(self) -> Any:
            page = QtWidgets.QWidget(); form = QtWidgets.QFormLayout(page); self.resource_combo = QtWidgets.QComboBox(); self.mode_combo = QtWidgets.QComboBox(); self.mode_combo.addItems(["generic"])
            self.mode_apply = QtWidgets.QPushButton("Apply mode / resource"); self.mode_apply.clicked.connect(self._apply_mode)
            form.addRow("Pulse resource", self.resource_combo); form.addRow("Authoring mode", self.mode_combo); form.addRow(self.mode_apply); return page

        def _source_page(self) -> Any:
            page = QtWidgets.QWidget(); form = QtWidgets.QFormLayout(page); self.provider_combo = QtWidgets.QComboBox(); self.template_line = QtWidgets.QLineEdit()
            browse = QtWidgets.QPushButton("Browse template"); browse.clicked.connect(self._browse_template); inspect = QtWidgets.QPushButton("Inspect / Apply"); inspect.clicked.connect(self._apply_source)
            self.editor_button = QtWidgets.QPushButton("Open Standalone Editor"); self.editor_button.clicked.connect(self._open_editor); self.source_status = QtWidgets.QLabel()
            form.addRow("Pulse resource", self.resource_combo); form.addRow("Base sequence template", self.template_line); form.addRow(browse, inspect); form.addRow(self.source_status); return page

        def _roles_page(self) -> Any:
            page = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(page); self.roles_table = QtWidgets.QTableWidget(0, 2); self.roles_table.setHorizontalHeaderLabels(["Role", "Confirmed channel"])
            apply = QtWidgets.QPushButton("Confirm roles"); apply.clicked.connect(self._apply_roles); layout.addWidget(self.roles_table); layout.addWidget(apply); return page

        def _parameter_page(self, swept: bool) -> Any:
            page = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(page); table = QtWidgets.QTableWidget(0, 8)
            table.setHorizontalHeaderLabels(["Parameter", "Mode", "Value", "Start", "Stop", "Points / Step", "Explicit values", "Unit"]); table.horizontalHeader().setStretchLastSection(True)
            apply = QtWidgets.QPushButton("Apply parameter edits"); apply.clicked.connect(self._apply_parameters)
            if swept:
                self.sweep_parameter_table = table; order_row = QtWidgets.QHBoxLayout(); self.sampling_order = QtWidgets.QListWidget(); self.sampling_order.setMaximumHeight(92)
                up = QtWidgets.QPushButton("Up"); down = QtWidgets.QPushButton("Down"); up.clicked.connect(lambda: self._move_sampling(-1)); down.clicked.connect(lambda: self._move_sampling(1))
                order_row.addWidget(QtWidgets.QLabel("Sampling order")); order_row.addWidget(self.sampling_order, 1); order_row.addWidget(up); order_row.addWidget(down); layout.addLayout(order_row)
            else: self.fixed_parameter_table = table
            layout.addWidget(table); layout.addWidget(apply); return page

        def _targets_page(self) -> Any:
            page = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(page); self.pulse_search = QtWidgets.QLineEdit(); self.pulse_search.setPlaceholderText("Filter channel / pulse")
            self.pulse_table = QtWidgets.QTableWidget(0, 7); self.pulse_table.setHorizontalHeaderLabels(["Channel", "Pulse", "Label", "Start", "Duration", "End", "Fingerprint"])
            self.pulse_table.itemSelectionChanged.connect(self._pulse_selected); self.pulse_search.textChanged.connect(self._filter_pulses); layout.addWidget(self.pulse_search); layout.addWidget(self.pulse_table)
            form = QtWidgets.QFormLayout(); self.target_alias = QtWidgets.QLineEdit("target"); self.target_parameter = QtWidgets.QLineEdit("duration_s")
            self.property_combo = QtWidgets.QComboBox(); self.propagation_combo = QtWidgets.QComboBox(); self.target_group = QtWidgets.QLineEdit()
            add = QtWidgets.QPushButton("Add / Update target binding"); add.clicked.connect(self._apply_target)
            for label, widget in (("Alias", self.target_alias), ("Bound parameter", self.target_parameter), ("Property", self.property_combo), ("Propagation", self.propagation_combo), ("Group", self.target_group)): form.addRow(label, widget)
            form.addRow(add); layout.addLayout(form)
            constraint = QtWidgets.QHBoxLayout(); self.constraint_target = QtWidgets.QLineEdit(); self.constraint_reference = QtWidgets.QLineEdit(); self.constraint_offset = QtWidgets.QDoubleSpinBox(); self.constraint_offset.setDecimals(12)
            add_constraint = QtWidgets.QPushButton("Add anchor"); add_constraint.clicked.connect(self._add_anchor)
            for widget in (QtWidgets.QLabel("Target edge"), self.constraint_target, QtWidgets.QLabel("Reference edge"), self.constraint_reference, self.constraint_offset, add_constraint): constraint.addWidget(widget)
            layout.addLayout(constraint); return page

        def _preview_page(self) -> Any:
            page = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(page); controls = QtWidgets.QHBoxLayout(); self.preview_choice = QtWidgets.QComboBox(); self.preview_choice.addItems(["First", "Current", "Last", "Overlay first/last", "Difference first/last"])
            self.preview_index = QtWidgets.QSpinBox(); self.preview_index.setMinimum(0); refresh = QtWidgets.QPushButton("Refresh preview"); refresh.clicked.connect(self._refresh_preview)
            self.preview_coords = QtWidgets.QLabel(); controls.addWidget(self.preview_choice); controls.addWidget(self.preview_index); controls.addWidget(refresh); controls.addWidget(self.preview_coords); controls.addStretch(1)
            self.timeline = Timeline(); self.timeline.pulseSelected.connect(self._timeline_pulse_selected); layout.addLayout(controls); layout.addWidget(self.timeline, 1); return page

        def _validation_page(self) -> Any:
            page = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(page); self.validation_summary = QtWidgets.QLabel("Select Validate to refresh issues."); layout.addWidget(self.validation_summary); layout.addStretch(1); return page

        def _provenance_page(self) -> Any:
            page = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(page); self.provenance = QtWidgets.QPlainTextEdit(); self.provenance.setReadOnly(True); layout.addWidget(self.provenance); return page

        def refresh(self) -> None:
            try:
                all_state = controller.get_guided_sequence_state(self.selected_plan)
                generic_ids = [item.id for item in all_state.plans if item.mode in {"generic", "standalone"}]
                if not generic_ids:
                    self.selected_plan = None; self.plan_combo.clear(); self.steps.clear(); self.state_label.setText("No generic sweep"); self.point_label.setText("0 points"); return
                if self.selected_plan not in generic_ids: self.selected_plan = generic_ids[0]
                state = controller.get_guided_sequence_state(self.selected_plan)
            except Exception as exc: self.validation_summary.setText(str(exc)); return
            self._state = state; self.selected_plan = state.selected_plan
            self.plan_combo.blockSignals(True); self.plan_combo.clear(); self.plan_combo.addItems(generic_ids)
            if state.selected_plan: self.plan_combo.setCurrentText(state.selected_plan)
            self.plan_combo.blockSignals(False); self.state_label.setText(state.prepared_state); self.point_label.setText(f"{state.point_count or 0} points")
            self.steps.clear()
            for index in GENERIC_STEP_INDICES:
                status = state.steps[index]
                item = QtWidgets.QListWidgetItem(STEP_LABELS[index]); item.setFlags(item.flags() | _enabled_flag(QtCore) if status.enabled else item.flags() & ~_enabled_flag(QtCore)); item.setToolTip(status.message)
                item.setData(_user_role(QtCore), index)
                if status.complete: item.setForeground(QtGui.QBrush(QtGui.QColor("#15803d")))
                self.steps.addItem(item)
            if state.steps: self.steps.setCurrentRow(min(self.steps.currentRow() if self.steps.currentRow() >= 0 else 0, self.steps.count() - 1))
            self._fill_mode_source(); self._fill_parameters(); self._fill_roles_targets(); self._fill_issues(); self._fill_provenance()

        def _fill_mode_source(self) -> None:
            if not self.selected_plan: return
            resources = controller.sequence_resource_names(); self.resource_combo.clear(); self.resource_combo.addItems(resources)
            plan = next(item for item in self._state.plans if item.id == self.selected_plan); self.resource_combo.setCurrentText(plan.resource); self.mode_combo.setCurrentText("generic")
            providers = [p for p in controller.list_sequence_providers() if "error" not in p and p["id"] != "asg_template"]
            self.provider_combo.clear()
            for item in providers: self.provider_combo.addItem(f"{item['label']} v{item['version']}", item["id"])
            raw = controller.current_config["sequence_plans"][self.selected_plan]; family = raw.get("family", {})
            index = self.provider_combo.findData(family.get("provider")); self.provider_combo.setCurrentIndex(max(0, index)); self.template_line.setText(str(raw.get("template") or ""))
            watched = self._watcher.files()
            if watched: self._watcher.removePaths(watched)
            resolved = resolve_project_path(raw.get("template"))
            if resolved is not None and resolved.is_file(): self._watcher.addPath(str(resolved))

        def _fill_parameters(self) -> None:
            if not self.selected_plan: return
            raw = controller.current_config["sequence_plans"][self.selected_plan].get("parameters", {})
            for table, swept in ((self.fixed_parameter_table, False), (self.sweep_parameter_table, True)):
                table.setRowCount(0)
                for field in self._state.parameter_fields:
                    current = raw.get(field.name, {"mode": "fixed", "value": field.default}); mode = str(current.get("mode", "fixed"))
                    if (mode != "fixed") != swept: continue
                    row = table.rowCount(); table.insertRow(row); mode_combo = QtWidgets.QComboBox(); modes = ["fixed"] + (["linspace", "range", "explicit"] if field.sweepable else []); mode_combo.addItems(modes); mode_combo.setCurrentText(mode); table.setCellWidget(row, 1, mode_combo)
                    values = (field.name, None, current.get("value", ""), current.get("start", ""), current.get("stop", ""), current.get("points", current.get("step", "")), ", ".join(map(str, current.get("values", ()))), field.unit or "")
                    for column, value in enumerate(values):
                        if column == 1: continue
                        item = QtWidgets.QTableWidgetItem(str(value)); item.setData(_user_role(QtCore), field); table.setItem(row, column, item)
            order = controller.current_config["sequence_plans"][self.selected_plan].get("sampling", {}).get("order", [])
            if not order:
                order = [name for name, value in raw.items() if isinstance(value, dict) and value.get("mode", "fixed") != "fixed"]
            self.sampling_order.clear(); self.sampling_order.addItems([str(name) for name in order])

        def _fill_roles_targets(self) -> None:
            self.property_combo.clear(); self.propagation_combo.clear()
            catalog = controller.sequence_authoring().generic_operation_catalog(); self.property_combo.addItems(catalog["Basic Timing"]); self.propagation_combo.addItems(catalog["Propagation"])
            if not self.selected_plan: return
            raw = controller.current_config["sequence_plans"][self.selected_plan]; roles = raw.get("options", {}).get("channels", {})
            self.roles_table.setRowCount(0)
            for role, channel in roles.items():
                row = self.roles_table.rowCount(); self.roles_table.insertRow(row); self.roles_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(role))); self.roles_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(channel)))
            self.pulse_table.setRowCount(0)
            if self._state.mode in {"generic", "standalone"} and raw.get("template"):
                try: inspection = controller.sequence_authoring().inspect_generic_template(self.selected_plan)
                except Exception as exc: self.source_status.setText(str(exc)); return
                self.source_status.setText(f"SHA256 {inspection.template_sha256[:12]} · {len(inspection.channels)} channel(s)")
                for channel in inspection.channels:
                    for pulse in channel.get("pulses", ()):
                        row = self.pulse_table.rowCount(); self.pulse_table.insertRow(row)
                        values = (channel.get("name"), pulse.get("pulse_index"), pulse.get("label", ""), pulse.get("start_s"), pulse.get("duration_s"), pulse.get("end_s"), pulse.get("fingerprint"))
                        for column, value in enumerate(values): self.pulse_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))

        def _fill_issues(self) -> None:
            self.issues.setRowCount(0)
            for issue in self._state.issues:
                row = self.issues.rowCount(); self.issues.insertRow(row)
                location = ".".join(item for item in (issue.step, issue.field) if item)
                for column, value in enumerate((issue.severity, issue.code, issue.message, location, issue.hint or "")):
                    item = QtWidgets.QTableWidgetItem(str(value)); item.setData(_user_role(QtCore), issue.step); self.issues.setItem(row, column, item)
            errors = sum(issue.severity == "error" for issue in self._state.issues); warnings = sum(issue.severity == "warning" for issue in self._state.issues)
            self.validation_summary.setText(f"{errors} error(s), {warnings} warning(s); point count {self._state.point_count or 0}")

        def _fill_provenance(self) -> None:
            if not self.selected_plan: self.provenance.clear(); return
            plan = next(item for item in self._state.plans if item.id == self.selected_plan); provenance = controller.get_sequence_provenance(self.selected_plan)
            lines = [f"plan: {plan.id}", f"state: {plan.state}", f"plan hash: {plan.plan_hash or '(not prepared)'}", f"provider: {plan.provider}", f"revision: {self._state.revision}"]
            if provenance is not None: lines.extend(("", yaml.safe_dump(provenance, sort_keys=False)))
            else: lines.extend(("", "No current prepared provenance. Validate and Prepare this revision."))
            self.provenance.setPlainText("\n".join(lines))

        def _plan_changed(self, value: str) -> None: self.selected_plan = value or None; self.refresh()
        def _step_changed(self, row: int) -> None:
            if row >= 0:
                item = self.steps.item(row); index = item.data(_user_role(QtCore)) if item else row
                self.current_step = int(index); self.pages.setCurrentIndex(int(index))
        def _issue_clicked(self, row: int, column: int) -> None:
            item = self.issues.item(row, column) or self.issues.item(row, 0); step = item.data(_user_role(QtCore)) if item else None
            if step in AUTHORING_STEPS: self.steps.setCurrentRow(AUTHORING_STEPS.index(step))

        def _new_plan(self) -> None:
            resources = controller.sequence_resource_names()
            if not resources: return
            dialog = QtWidgets.QDialog(self); form = QtWidgets.QFormLayout(dialog); pid = QtWidgets.QLineEdit("sequence_main"); resource = QtWidgets.QComboBox(); resource.addItems(resources)
            template = QtWidgets.QLineEdit(); buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
            for label, widget in (("Plan id", pid), ("Resource", resource), ("Base sequence template", template)): form.addRow(label, widget)
            form.addRow(buttons)
            if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted: return
            try: controller.create_guided_sequence_plan(pid.text().strip(), resource.currentText(), "generic", template=template.text().strip() or None); self.selected_plan = pid.text().strip(); self._changed()
            except Exception as exc: QtWidgets.QMessageBox.critical(self, "Create plan failed", str(exc))

        def _duplicate(self) -> None:
            if not self.selected_plan: return
            name, ok = QtWidgets.QInputDialog.getText(self, "Duplicate plan", "New id", text=f"{self.selected_plan}_copy")
            if ok and name.strip(): controller.duplicate_sequence_plan(self.selected_plan, name.strip()); self.selected_plan = name.strip(); self._changed()
        def _delete(self) -> None:
            if self.selected_plan: controller.delete_sequence_plan(self.selected_plan); self.selected_plan = None; self._changed()
        def _apply_mode(self) -> None:
            if not self.selected_plan: return
            new_mode = self.mode_combo.currentText(); preview = controller.preview_sequence_mode_change(self.selected_plan, new_mode)
            if preview.old_mode != new_mode:
                text = f"Retain: {', '.join(preview.retained_paths) or '(none)'}\nRemove: {', '.join(preview.removed_paths) or '(none)'}"
                if QtWidgets.QMessageBox.question(self, "Confirm mode migration", text) != QtWidgets.QMessageBox.StandardButton.Yes: return
                controller.change_sequence_mode(self.selected_plan, new_mode, provider=self.provider_combo.currentData(), template=self.template_line.text().strip() or None)
            if self.resource_combo.currentText(): controller.change_sequence_resource(self.selected_plan, self.resource_combo.currentText())
            self._changed()
        def _browse_template(self) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select sequence template", "", "Sequence JSON (*.json);;All files (*)")
            if path: self.template_line.setText(path)
        def _apply_source(self) -> None:
            if not self.selected_plan: return
            controller.change_sequence_mode(self.selected_plan, "generic", template=self.template_line.text().strip() or None)
            if self.resource_combo.currentText(): controller.change_sequence_resource(self.selected_plan, self.resource_combo.currentText())
            self._changed()
        def _apply_roles(self) -> None:
            roles = {self.roles_table.item(r, 0).text(): self.roles_table.item(r, 1).text() for r in range(self.roles_table.rowCount()) if self.roles_table.item(r, 0) and self.roles_table.item(r, 1)}
            if self.selected_plan: controller.update_sequence_roles(self.selected_plan, roles, confirmed=True); self._changed()
        def _apply_parameters(self) -> None:
            if not self.selected_plan: return
            for table in (self.fixed_parameter_table, self.sweep_parameter_table):
                for row in range(table.rowCount()):
                    name = table.item(row, 0).text(); mode = table.cellWidget(row, 1).currentText(); patch: dict[str, Any] = {"mode": mode}
                    if mode == "fixed": patch["value"] = _scalar(table.item(row, 2).text())
                    elif mode == "linspace": patch.update(start=_scalar(table.item(row, 3).text()), stop=_scalar(table.item(row, 4).text()), points=int(table.item(row, 5).text()))
                    elif mode == "range": patch.update(start=_scalar(table.item(row, 3).text()), stop=_scalar(table.item(row, 4).text()), step=_scalar(table.item(row, 5).text()))
                    else: patch["values"] = _list_value(table.item(row, 6).text())
                    unit = table.item(row, 7).text().strip()
                    if unit: patch["unit"] = unit
                    controller.update_sequence_plan_parameter(self.selected_plan, name, patch)
            order = [self.sampling_order.item(index).text() for index in range(self.sampling_order.count())]
            controller.set_sequence_plan_sampling_order(self.selected_plan, order)
            self._changed()
        def _move_sampling(self, delta: int) -> None:
            row = self.sampling_order.currentRow(); target = row + delta
            if row < 0 or target < 0 or target >= self.sampling_order.count(): return
            item = self.sampling_order.takeItem(row); self.sampling_order.insertItem(target, item); self.sampling_order.setCurrentRow(target)
            if self.selected_plan:
                controller.set_sequence_plan_sampling_order(self.selected_plan, [self.sampling_order.item(i).text() for i in range(self.sampling_order.count())]); self._changed()
        def _filter_pulses(self, text: str) -> None:
            needle = text.strip().casefold()
            for row in range(self.pulse_table.rowCount()):
                haystack = " ".join(self.pulse_table.item(row, col).text() for col in range(min(3, self.pulse_table.columnCount())) if self.pulse_table.item(row, col)).casefold()
                self.pulse_table.setRowHidden(row, bool(needle and needle not in haystack))
        def _pulse_selected(self) -> None:
            row = self.pulse_table.currentRow()
            if row < 0: return
            channel = self.pulse_table.item(row, 0).text(); pulse = int(self.pulse_table.item(row, 1).text()); self.timeline.selected = (channel, pulse); self.timeline.update()
        def _timeline_pulse_selected(self, channel: str, pulse: int) -> None:
            for row in range(self.pulse_table.rowCount()):
                if self.pulse_table.item(row, 0).text() == channel and int(self.pulse_table.item(row, 1).text()) == pulse:
                    self.pulse_table.selectRow(row); break
        def _apply_target(self) -> None:
            row = self.pulse_table.currentRow()
            if not self.selected_plan or row < 0: return
            controller.update_sequence_target_transform(self.selected_plan, self.target_alias.text().strip(), self.pulse_table.item(row, 0).text(), int(self.pulse_table.item(row, 1).text()), parameter=self.target_parameter.text().strip(), property_name=self.property_combo.currentText(), propagation=self.propagation_combo.currentText(), group=self.target_group.text().strip() or None); self._changed()
        def _add_anchor(self) -> None:
            if self.selected_plan: controller.add_sequence_anchor(self.selected_plan, self.constraint_target.text().strip(), self.constraint_reference.text().strip(), self.constraint_offset.value()); self._changed()
        def _refresh_preview(self) -> None:
            if not self.selected_plan: return
            try:
                previews = controller.get_sequence_previews(self.selected_plan, self.preview_index.value()); index = self.preview_choice.currentIndex(); state = controller.get_guided_sequence_state(self.selected_plan)
                if index < 3:
                    self.timeline.set_preview(previews[index]); coords = (state.first_coordinates, {}, state.last_coordinates)[index]
                else:
                    self.timeline.set_preview(previews[2], previews[0], difference=index == 4); coords = {"first": state.first_coordinates, "last": state.last_coordinates}
                self.preview_coords.setText(f"{coords} · duration {self.timeline.preview.duration_s:.6g} s")
            except Exception as exc: self.preview_coords.setText(str(exc)); self.timeline.set_preview(None)
        def _insert_macro(self) -> None:
            if self.selected_plan: controller.insert_sequence_macro(self.selected_plan); self._changed()
        def _prepare(self) -> None:
            self.prepare_button.setEnabled(False)
            revision = self._state.revision if self._state is not None else None
            def work():
                try: self._bridge.prepare_finished.emit(controller.prepare_sequence_plan(self.selected_plan, expected_revision=revision), None)
                except Exception as exc: self._bridge.prepare_finished.emit(None, exc)
            threading.Thread(target=work, daemon=True).start()
        def _prepare_done(self, result: Any, error: Any) -> None:
            self.prepare_button.setEnabled(True)
            if error is not None: QtWidgets.QMessageBox.critical(self, "Prepare failed", str(error))
            if on_config_changed: on_config_changed()
            self.refresh()
        def _open_editor(self) -> None:
            if not self.selected_plan: return
            self.editor_button.setEnabled(False); editor = default_sequence_editor_path(); sequence = self.template_line.text().strip() or None
            def work(): self._bridge.editor_finished.emit(run_sequence_editor_protocol(editor, sequence))
            threading.Thread(target=work, daemon=True).start()
        def _editor_done(self, result: Any) -> None:
            self.editor_button.setEnabled(True); self.source_status.setText(result.message or ("Saved" if result.ok else "Failed"))
            if result.ok and result.saved_artifact:
                try: controller.accept_sequence_editor_result(self.selected_plan, result.saved_artifact); self._changed()
                except Exception as exc: self.source_status.setText(str(exc))
        def _template_changed(self, path: str) -> None:
            if self.selected_plan:
                controller.mark_sequence_template_stale(self.selected_plan)
                self.source_status.setText(f"Template changed externally: {path}. Re-inspect and Prepare again.")
                self.refresh()
        def _changed(self) -> None:
            if on_config_changed: on_config_changed()
            self.refresh()

    class BundleBrowserWidget(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__(); self._entries: list[dict[str, Any]] = []; self._build(); self.refresh()

        def _build(self) -> None:
            layout = QtWidgets.QVBoxLayout(self); controls = QtWidgets.QHBoxLayout()
            self.bundle_combo = QtWidgets.QComboBox(); self.bundle_combo.currentTextChanged.connect(self._bundle_changed)
            self.compare_combo = QtWidgets.QComboBox(); self.compare_combo.addItems(["Selected entry", "Overlay first / last", "Difference first / last"]); self.compare_combo.currentIndexChanged.connect(self._show_preview)
            self.bundle_summary = QtWidgets.QLabel("No bundle")
            controls.addWidget(QtWidgets.QLabel("Bundle")); controls.addWidget(self.bundle_combo, 1); controls.addWidget(self.compare_combo); controls.addWidget(self.bundle_summary); layout.addLayout(controls)
            split = QtWidgets.QSplitter(_horizontal(QtCore)); self.entry_table = QtWidgets.QTableWidget(0, 6)
            self.entry_table.setHorizontalHeaderLabels(["Entry", "Coordinates", "Duration", "Triggers", "Sequence file", "SHA256"]); self.entry_table.horizontalHeader().setStretchLastSection(True); self.entry_table.itemSelectionChanged.connect(self._entry_changed); split.addWidget(self.entry_table)
            detail = QtWidgets.QWidget(); detail_layout = QtWidgets.QVBoxLayout(detail); self.pulse_table = QtWidgets.QTableWidget(0, 6)
            self.pulse_table.setHorizontalHeaderLabels(["Channel", "Pulse", "Start", "Duration", "End", "Label"]); self.pulse_table.horizontalHeader().setStretchLastSection(True)
            self.timeline = Timeline(); self.timeline.pulseSelected.connect(self._timeline_selected); self.coordinates = QtWidgets.QLabel()
            detail_layout.addWidget(self.coordinates); detail_layout.addWidget(self.timeline, 1); detail_layout.addWidget(self.pulse_table); split.addWidget(detail); split.setSizes([500, 760]); layout.addWidget(split, 1)

        def refresh(self) -> None:
            current = self.bundle_combo.currentText(); summaries = controller.list_sequence_bundle_summaries()
            self.bundle_combo.blockSignals(True); self.bundle_combo.clear(); self.bundle_combo.addItems([item["id"] for item in summaries])
            if current and self.bundle_combo.findText(current) >= 0: self.bundle_combo.setCurrentText(current)
            self.bundle_combo.blockSignals(False); self._bundle_changed(self.bundle_combo.currentText())

        def _bundle_changed(self, bundle_id: str) -> None:
            self._entries = list(controller.list_sequence_bundle_entries(bundle_id)) if bundle_id else []
            self.entry_table.setRowCount(0)
            for entry in self._entries:
                row = self.entry_table.rowCount(); self.entry_table.insertRow(row); metadata = entry.get("metadata", {})
                values = (entry["id"], yaml.safe_dump(entry.get("coordinates", {}), default_flow_style=True).strip(), metadata.get("duration_s", ""), ", ".join(map(str, metadata.get("trigger_channels", ()))), entry.get("sequence_file", ""), str(entry.get("sha256", ""))[:12])
                for column, value in enumerate(values): self.entry_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
            summary = next((item for item in controller.list_sequence_bundle_summaries() if item["id"] == bundle_id), None)
            self.bundle_summary.setText("No bundle" if summary is None else f"{summary['entry_count']} entries · {', '.join(summary['coordinates']) or 'no coordinates'}")
            if self._entries: self.entry_table.selectRow(0)
            else: self.timeline.set_preview(None); self.pulse_table.setRowCount(0)

        def _entry_changed(self) -> None: self._show_preview()

        def _show_preview(self) -> None:
            if not self._entries: return
            row = max(0, self.entry_table.currentRow()); selected = self._entries[row]
            try:
                preview = controller.preview_sequence_bundle_entry(self.bundle_combo.currentText(), selected["id"])
                comparison = None; difference = False
                if self.compare_combo.currentIndex() > 0 and len(self._entries) > 1:
                    preview = controller.preview_sequence_bundle_entry(self.bundle_combo.currentText(), self._entries[-1]["id"])
                    comparison = controller.preview_sequence_bundle_entry(self.bundle_combo.currentText(), self._entries[0]["id"])
                    difference = self.compare_combo.currentIndex() == 2
                self.timeline.set_preview(preview, comparison, difference=difference); self.coordinates.setText(yaml.safe_dump(selected.get("coordinates", {}), default_flow_style=True).strip())
                self._fill_pulses(preview)
            except Exception as exc:
                self.coordinates.setText(str(exc)); self.timeline.set_preview(None); self.pulse_table.setRowCount(0)

        def _fill_pulses(self, preview: NormalizedPreview) -> None:
            self.pulse_table.setRowCount(0)
            for pulse in preview.pulses:
                row = self.pulse_table.rowCount(); self.pulse_table.insertRow(row)
                for column, value in enumerate((pulse.channel, pulse.pulse, _format_time(pulse.start_s), _format_time(pulse.duration_s), _format_time(pulse.end_s), pulse.label or pulse.alias or "")):
                    self.pulse_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))

        def _timeline_selected(self, channel: str, pulse: int) -> None:
            for row in range(self.pulse_table.rowCount()):
                if self.pulse_table.item(row, 0).text() == channel and int(self.pulse_table.item(row, 1).text()) == pulse:
                    self.pulse_table.selectRow(row); break

    class SequenceWorkspaceWidget(QtWidgets.QTabWidget):
        def __init__(self) -> None:
            super().__init__(); self.bundle_browser = BundleBrowserWidget(); self.generic_sweep = GuidedSequenceWidget()
            self.addTab(self.bundle_browser, "Bundle Browser"); self.addTab(self.generic_sweep, "Generic Sweep")
            for name in (
                "steps", "pages", "plan_combo", "timeline", "pulse_table", "sweep_parameter_table",
                "fixed_parameter_table", "sampling_order", "resource_combo", "mode_combo", "editor_button",
                "template_line", "property_combo", "propagation_combo", "target_alias", "target_parameter",
                "issues", "preview_choice",
                "_apply_mode", "_apply_parameters", "_refresh_preview", "_insert_macro", "_apply_target",
                "_issue_clicked", "_move_sampling", "_editor_done",
            ):
                if hasattr(self.generic_sweep, name): setattr(self, name, getattr(self.generic_sweep, name))
        def refresh(self) -> None:
            self.bundle_browser.refresh(); self.generic_sweep.refresh()

    return SequenceWorkspaceWidget()

def _scalar(text: str) -> Any:
    value = yaml.safe_load(text)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)): raise ValueError(f"Invalid scalar: {text}")
    return value
def _list_value(text: str) -> list[Any]:
    value = yaml.safe_load(text if text.strip().startswith("[") else f"[{text}]")
    if not isinstance(value, list) or not value: raise ValueError("Explicit values require a non-empty list")
    return value
def _format_time(value: float) -> str:
    absolute = abs(value)
    if absolute < 1e-6: return f"{value * 1e9:.3g} ns"
    if absolute < 1e-3: return f"{value * 1e6:.3g} us"
    if absolute < 1: return f"{value * 1e3:.3g} ms"
    return f"{value:.3g} s"
def _horizontal(QtCore: Any) -> Any:
    return getattr(getattr(QtCore.Qt, "Orientation", QtCore.Qt), "Horizontal")
def _align_center(QtCore: Any) -> Any:
    return getattr(getattr(QtCore.Qt, "AlignmentFlag", QtCore.Qt), "AlignCenter")
def _enabled_flag(QtCore: Any) -> Any:
    return getattr(getattr(QtCore.Qt, "ItemFlag", QtCore.Qt), "ItemIsEnabled")
def _user_role(QtCore: Any) -> Any:
    return getattr(getattr(QtCore.Qt, "ItemDataRole", QtCore.Qt), "UserRole")
