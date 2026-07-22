"""Qt factory for the schema-driven guided workflow composer."""

from __future__ import annotations

import json
from typing import Any, Callable

from qulab.instruments.action_specs import MISSING

from .workflow_composer import RECIPE_FILES, convert_form_values


def create_guided_workflow_widget(
    QtWidgets: Any,
    controller: Any,
    *,
    on_config_changed: Callable[[], None] | None = None,
) -> Any:
    class GuidedWorkflowWidget(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self._fields: dict[str, Any] = {}
            self._palette: list[Any] = []
            self._targets: list[Any] = []
            self.selected_path: tuple[str | int, ...] | None = None
            self._edit_fields: dict[str, Any] = {}
            self._build()
            if controller.has_active_config:
                self.refresh()

        def _build(self) -> None:
            page = QtWidgets.QVBoxLayout(self)
            page.setContentsMargins(8, 8, 8, 8)

            recipe_row = QtWidgets.QHBoxLayout()
            recipe_row.addWidget(QtWidgets.QLabel("Start from recipe / 从实验模板开始"))
            self.recipe = QtWidgets.QComboBox()
            for name in RECIPE_FILES:
                self.recipe.addItem(name.replace("_", " ").title(), name)
            apply_recipe = QtWidgets.QPushButton("Apply Recipe / 应用模板")
            apply_recipe.clicked.connect(self._apply_recipe)
            refresh = QtWidgets.QPushButton("Refresh / 刷新")
            refresh.clicked.connect(self.refresh)
            recipe_row.addWidget(self.recipe, 1)
            recipe_row.addWidget(apply_recipe)
            recipe_row.addWidget(refresh)
            page.addLayout(recipe_row)

            body = QtWidgets.QSplitter()
            authoring = QtWidgets.QWidget()
            authoring_layout = QtWidgets.QVBoxLayout(authoring)
            authoring_layout.setContentsMargins(0, 0, 4, 0)
            authoring_layout.addWidget(self._scan_group())
            authoring_layout.addWidget(self._structure_group())
            authoring_layout.addWidget(self._action_group(), 1)
            body.addWidget(authoring)

            review = QtWidgets.QWidget()
            review_layout = QtWidgets.QVBoxLayout(review)
            review_layout.setContentsMargins(4, 0, 0, 0)
            review_layout.addWidget(QtWidgets.QLabel("Canonical workflow / 当前完整流程"))
            self.outline = QtWidgets.QTreeWidget()
            self.outline.setHeaderLabels(["Step", "Kind"])
            self.outline.itemSelectionChanged.connect(self._outline_selected)
            review_layout.addWidget(self.outline, 1)
            manage = QtWidgets.QHBoxLayout()
            self.undo_button = QtWidgets.QPushButton("Undo"); self.redo_button = QtWidgets.QPushButton("Redo")
            duplicate = QtWidgets.QPushButton("Duplicate"); delete = QtWidgets.QPushButton("Delete"); delete.setObjectName("dangerButton")
            up = QtWidgets.QPushButton("Up"); down = QtWidgets.QPushButton("Down")
            self.undo_button.clicked.connect(self._undo); self.redo_button.clicked.connect(self._redo)
            duplicate.clicked.connect(self._duplicate_selected); delete.clicked.connect(self._delete_selected)
            up.clicked.connect(lambda: self._move_sibling(-1)); down.clicked.connect(lambda: self._move_sibling(1))
            for button in (self.undo_button, self.redo_button, duplicate, delete, up, down): manage.addWidget(button)
            review_layout.addLayout(manage)
            relocate = QtWidgets.QHBoxLayout(); self.move_parent = QtWidgets.QComboBox(); move = QtWidgets.QPushButton("Move inside")
            move.clicked.connect(self._move_selected_to); relocate.addWidget(QtWidgets.QLabel("Destination")); relocate.addWidget(self.move_parent, 1); relocate.addWidget(move)
            review_layout.addLayout(relocate)
            self.selected_title = QtWidgets.QLabel("Select a workflow step to edit")
            review_layout.addWidget(self.selected_title)
            self.edit_widget = QtWidgets.QWidget(); self.edit_form = QtWidgets.QFormLayout(self.edit_widget)
            review_layout.addWidget(self.edit_widget)
            self.apply_edit_button = QtWidgets.QPushButton("Apply Selected Step")
            self.apply_edit_button.setObjectName("primaryButton"); self.apply_edit_button.clicked.connect(self._apply_selected_edit)
            review_layout.addWidget(self.apply_edit_button)
            review_layout.addWidget(QtWidgets.QLabel("Continuity checks / 连贯性检查"))
            self.issues = QtWidgets.QTableWidget(0, 3)
            self.issues.setHorizontalHeaderLabels(["Severity", "Code", "Message"])
            self.issues.horizontalHeader().setStretchLastSection(True)
            self.issues.cellDoubleClicked.connect(self._focus_issue)
            review_layout.addWidget(self.issues, 1)
            body.addWidget(review)
            body.setSizes([520, 520])
            page.addWidget(body, 1)

        def _scan_group(self) -> Any:
            group = QtWidgets.QGroupBox("Add Scan / 添加扫描")
            form = QtWidgets.QFormLayout(group)
            self.scan_target = QtWidgets.QComboBox()
            self.scan_target.currentIndexChanged.connect(self._show_target)
            self.scan_description = QtWidgets.QLabel()
            self.scan_description.setWordWrap(True)
            self.scan_name = QtWidgets.QLineEdit("scan_axis")
            self.scan_start = QtWidgets.QLineEdit("0")
            self.scan_stop = QtWidgets.QLineEdit("1")
            self.scan_points = QtWidgets.QSpinBox()
            self.scan_points.setRange(2, 1000000)
            self.scan_points.setValue(21)
            add = QtWidgets.QPushButton("Create Connected Scan / 创建并连接扫描")
            add.setObjectName("primaryButton")
            add.clicked.connect(self._add_scan)
            form.addRow("Target / 扫描对象", self.scan_target)
            form.addRow("Effect / 作用", self.scan_description)
            form.addRow("Axis name / 轴名称", self.scan_name)
            form.addRow("Start / 起点", self.scan_start)
            form.addRow("Stop / 终点", self.scan_stop)
            form.addRow("Points / 点数", self.scan_points)
            form.addRow("", add)
            return group

        def _clear_edit_form(self) -> None:
            while self.edit_form.rowCount(): self.edit_form.removeRow(0)
            self._edit_fields = {}

        def _edit_line(self, name: str, value: Any, label: str | None = None) -> Any:
            line = QtWidgets.QLineEdit(_display_value(value)); self._edit_fields[name] = line
            self.edit_form.addRow(label or name, line); return line

        def _argument_editor(self, argument: Any, value: Any) -> Any:
            if argument.choices:
                editor = QtWidgets.QComboBox(); editor.setEditable(bool(argument.allow_reference)); editor.addItems([str(item) for item in argument.choices]); editor.setCurrentText(str(value))
            elif argument.dtype == "boolean":
                editor = QtWidgets.QCheckBox(); editor.setChecked(bool(value))
            else:
                editor = QtWidgets.QLineEdit(_display_value(value))
            editor.setToolTip(argument.description or argument.dtype)
            return editor

        def _rebuild_selected_editor(self) -> None:
            self._clear_edit_form(); path = self.selected_path
            if path is None or not path or not isinstance(path[-1], int):
                self.selected_title.setText("Select a workflow step to edit"); self.apply_edit_button.setEnabled(False); return
            try: step = controller.workflow_composer().step(path)
            except Exception:
                self.selected_path = None; self.apply_edit_button.setEnabled(False); return
            kind = next((name for name in ("call", "scan", "average", "measurement", "run", "wait", "cleanup", "sequence_sweep") if name in step), "unknown")
            self.selected_title.setText(f"Edit {kind} · {'/'.join(map(str, path))}")
            enabled = QtWidgets.QCheckBox(); enabled.setChecked(bool(step.get("enabled", True))); self._edit_fields["enabled"] = enabled; self.edit_form.addRow("Enabled", enabled)
            if kind == "call":
                call = str(step.get("call") or ""); call_label = QtWidgets.QLabel(call); self.edit_form.addRow("Action", call_label)
                resolved = controller.workflow_composer().action_spec(path); args = step.get("args", {}) if isinstance(step.get("args"), dict) else {}
                if resolved is None:
                    self._edit_fields["raw_action"] = True; self._edit_line("args_json", args, "Arguments JSON")
                else:
                    _resource, action = resolved; self._edit_fields["action_spec"] = action
                    if action.allow_unknown_arguments:
                        self._edit_fields["raw_action"] = True; self._edit_line("args_json", args, "Arguments JSON")
                    else:
                        for argument in action.arguments:
                            value = args.get(argument.name, "" if argument.default is MISSING else argument.default)
                            editor = self._argument_editor(argument, value); self._edit_fields[f"arg:{argument.name}"] = editor
                            self.edit_form.addRow(argument.name + (f" [{argument.unit}]" if argument.unit else ""), editor)
                self._edit_line("save_as", step.get("save_as", ""), "Save as")
            elif kind == "scan":
                payload = step[kind]; self._edit_line("name", payload.get("name", "scan"))
                mode = QtWidgets.QComboBox(); mode.addItems(["linspace", "range", "explicit"]); values = payload.get("values", [])
                mode.setCurrentText("explicit" if isinstance(values, list) else "range" if isinstance(values, dict) and "step" in values else "linspace")
                self._edit_fields["values_mode"] = mode; self.edit_form.addRow("Values mode", mode)
                self._edit_line("start", values.get("start", "") if isinstance(values, dict) else "")
                self._edit_line("stop", values.get("stop", "") if isinstance(values, dict) else "")
                self._edit_line("points", values.get("points", "") if isinstance(values, dict) else "")
                self._edit_line("step", values.get("step", "") if isinstance(values, dict) else "")
                self._edit_line("values", values if isinstance(values, list) else [], "Explicit values")
            elif kind == "average":
                self._edit_line("name", step[kind].get("name", "average")); self._edit_line("count", step[kind].get("count", 1))
            elif kind in {"measurement", "cleanup"}:
                self._edit_line("name", step[kind].get("name", kind))
            elif kind == "run":
                self._edit_line("name", step[kind].get("name", "run")); self._edit_line("timeout_s", step[kind].get("timeout_s", 10.0))
            elif kind == "wait":
                self._edit_line("name", step[kind].get("name", "wait")); self._edit_line("duration_s", step[kind].get("duration_s", 0.1))
            elif kind == "sequence_sweep":
                plans = QtWidgets.QComboBox(); plans.addItems(list((controller.current_config.get("sequence_plans") or {}).keys())); plans.setCurrentText(str(step[kind].get("plan") or ""))
                self._edit_fields["plan"] = plans; self.edit_form.addRow("Sequence plan", plans)
            else:
                self.edit_form.addRow(QtWidgets.QLabel("Unsupported node; use Advanced Tree for raw inspection."))
            self._edit_fields["kind"] = kind; self.apply_edit_button.setEnabled(kind != "unknown")

        def _structure_group(self) -> Any:
            group = QtWidgets.QGroupBox("Add Workflow Block / 添加流程块")
            row = QtWidgets.QHBoxLayout(group)
            self.structure_kind = QtWidgets.QComboBox()
            for label, kind in (
                ("Measurement / 单点测量", "measurement"),
                ("Average / 重复平均", "average"),
                ("Run / 同步运行", "run"),
                ("Wait / 等待", "wait"),
            ):
                self.structure_kind.addItem(label, kind)
            self.structure_parent = QtWidgets.QComboBox()
            add = QtWidgets.QPushButton("Add Block / 添加")
            add.clicked.connect(self._add_structure)
            row.addWidget(self.structure_kind)
            row.addWidget(QtWidgets.QLabel("inside"))
            row.addWidget(self.structure_parent, 1)
            row.addWidget(add)
            return group

        def _action_group(self) -> Any:
            group = QtWidgets.QGroupBox("Add Instrument Action / 添加仪器步骤")
            layout = QtWidgets.QVBoxLayout(group)
            row = QtWidgets.QHBoxLayout()
            self.action_search = QtWidgets.QLineEdit()
            self.action_search.setPlaceholderText("Search action, resource or capability")
            self.action_search.textChanged.connect(self._refresh_palette)
            self.action_combo = QtWidgets.QComboBox()
            self.action_combo.currentIndexChanged.connect(self._rebuild_action_form)
            row.addWidget(self.action_search)
            row.addWidget(self.action_combo, 1)
            layout.addLayout(row)
            self.action_description = QtWidgets.QLabel()
            self.action_description.setWordWrap(True)
            layout.addWidget(self.action_description)
            self.action_form_widget = QtWidgets.QWidget()
            self.action_form = QtWidgets.QFormLayout(self.action_form_widget)
            layout.addWidget(self.action_form_widget)
            footer = QtWidgets.QHBoxLayout()
            self.action_parent = QtWidgets.QComboBox()
            self.action_parent.currentIndexChanged.connect(self._refresh_palette)
            self.save_as = QtWidgets.QLineEdit()
            self.save_as.setPlaceholderText("optional data key")
            add = QtWidgets.QPushButton("Add Action / 添加步骤")
            add.clicked.connect(self._add_action)
            footer.addWidget(QtWidgets.QLabel("Inside"))
            footer.addWidget(self.action_parent)
            footer.addWidget(QtWidgets.QLabel("Save as"))
            footer.addWidget(self.save_as)
            footer.addWidget(add)
            layout.addLayout(footer)
            return group

        def refresh(self) -> None:
            model = controller.workflow_composer()
            selected = self.scan_target.currentData() if self.scan_target.count() else None
            self._targets = list(model.list_scan_targets())
            self.scan_target.blockSignals(True)
            self.scan_target.clear()
            for target in self._targets:
                unit = f" [{target.unit}]" if target.unit else ""
                self.scan_target.addItem(f"{target.group}: {target.label}{unit}", target.id)
            if selected:
                index = self.scan_target.findData(selected)
                if index >= 0:
                    self.scan_target.setCurrentIndex(index)
            self.scan_target.blockSignals(False)
            self._show_target()
            self._refresh_outline()
            self._refresh_destinations()
            self._refresh_palette()
            self._rebuild_selected_editor()
            self._refresh_issues()
            self.undo_button.setEnabled(model.can_undo); self.redo_button.setEnabled(model.can_redo)

        def _show_target(self) -> None:
            index = self.scan_target.currentIndex()
            target = self._targets[index] if 0 <= index < len(self._targets) else None
            self.scan_description.setText(target.description if target else "No numeric scan target is available yet. Add a schema-defined action or sequence plan first.")
            if target:
                suggested = target.path[-1] if target.kind == "action" else target.path[-1]
                self.scan_name.setText(str(suggested))

        def _refresh_palette(self) -> None:
            current = self.action_combo.currentData() if self.action_combo.count() else None
            parent = self.action_parent.currentData() if hasattr(self, "action_parent") else ("procedure",)
            section = str(parent[0]) if parent else "procedure"
            self._palette = [
                item for item in controller.workflow_composer().list_palette((section,), self.action_search.text())
                if item.action and item.available
            ]
            self.action_combo.blockSignals(True)
            self.action_combo.clear()
            for index, item in enumerate(self._palette):
                self.action_combo.addItem(f"{item.group}: {item.label}", index)
            if current is not None:
                found = self.action_combo.findData(current)
                if found >= 0:
                    self.action_combo.setCurrentIndex(found)
            self.action_combo.blockSignals(False)
            self._rebuild_action_form()

        def _rebuild_action_form(self) -> None:
            while self.action_form.rowCount():
                self.action_form.removeRow(0)
            self._fields = {}
            index = self.action_combo.currentIndex()
            item = self._palette[index] if 0 <= index < len(self._palette) else None
            action = item.action if item else None
            self.action_description.setText((action.description or f"{action.phase.title()} action for {action.capability}.") if action else "No matching action.")
            if action is None:
                return
            for argument in action.arguments:
                value = "" if argument.default is MISSING else argument.default
                editor = self._argument_editor(argument, value)
                label = argument.name + (" *" if argument.required else "")
                if argument.unit:
                    label += f" [{argument.unit}]"
                self._fields[argument.name] = editor
                self.action_form.addRow(label, editor)

        def _add_scan(self) -> None:
            target_id = self.scan_target.currentData()
            if not target_id:
                return
            try:
                values = {
                    "start": float(self.scan_start.text()),
                    "stop": float(self.scan_stop.text()),
                    "points": int(self.scan_points.value()),
                }
                controller.configure_guided_scan(target_id, self.scan_name.text().strip(), values)
                self._changed()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Scan creation failed", str(exc))

        def _add_structure(self) -> None:
            try:
                controller.insert_guided_structure(self.structure_kind.currentData(), self.structure_parent.currentData())
                self._changed()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Block insertion failed", str(exc))

        def _add_action(self) -> None:
            index = self.action_combo.currentIndex()
            if not 0 <= index < len(self._palette):
                return
            item = self._palette[index]
            raw = {name: _widget_value(editor) for name, editor in self._fields.items() if _widget_has_value(editor)}
            try:
                values = convert_form_values(item.action, raw)
                controller.insert_guided_action(item.resource, item.action, values, self.action_parent.currentData(), self.save_as.text().strip() or None)
                self.save_as.clear()
                self._changed()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Action insertion failed", str(exc))

        def _apply_selected_edit(self) -> None:
            if self.selected_path is None: return
            fields = self._edit_fields; kind = fields.get("kind"); enabled = fields["enabled"].isChecked()
            try:
                if kind == "call":
                    if fields.get("raw_action"):
                        values = json.loads(fields["args_json"].text() or "{}")
                        if not isinstance(values, dict): raise ValueError("Arguments JSON must be an object")
                    else:
                        action = fields["action_spec"]
                        raw = {argument.name: _widget_value(fields[f"arg:{argument.name}"])
                               for argument in action.arguments if _widget_has_value(fields[f"arg:{argument.name}"])}
                        values = convert_form_values(action, raw)
                    controller.update_guided_action(self.selected_path, values, fields["save_as"].text().strip() or None, enabled=enabled)
                else:
                    values: dict[str, Any] = {}
                    if kind == "scan":
                        mode = fields["values_mode"].currentText(); values["name"] = fields["name"].text().strip()
                        if mode == "explicit": values["values"] = _parse_list(fields["values"].text())
                        elif mode == "range": values["values"] = {"start": _parse_scalar(fields["start"].text()), "stop": _parse_scalar(fields["stop"].text()), "step": _parse_scalar(fields["step"].text())}
                        else: values["values"] = {"start": _parse_scalar(fields["start"].text()), "stop": _parse_scalar(fields["stop"].text()), "points": int(fields["points"].text())}
                    elif kind == "average": values = {"name": fields["name"].text().strip(), "count": int(fields["count"].text())}
                    elif kind in {"measurement", "cleanup"}: values = {"name": fields["name"].text().strip()}
                    elif kind == "run": values = {"name": fields["name"].text().strip(), "timeout_s": float(fields["timeout_s"].text())}
                    elif kind == "wait": values = {"name": fields["name"].text().strip(), "duration_s": float(fields["duration_s"].text())}
                    elif kind == "sequence_sweep": values = {"plan": fields["plan"].currentText()}
                    controller.update_guided_structure(self.selected_path, values, enabled=enabled)
                self._changed()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Step update failed", str(exc))

        def _delete_selected(self) -> None:
            if self.selected_path is None or not isinstance(self.selected_path[-1], int): return
            answer = QtWidgets.QMessageBox.question(self, "Delete workflow step?", "Delete the selected step and every child inside it?")
            if answer != QtWidgets.QMessageBox.StandardButton.Yes: return
            try: controller.delete_guided_step(self.selected_path); self.selected_path = None; self._changed()
            except Exception as exc: QtWidgets.QMessageBox.critical(self, "Delete failed", str(exc))

        def _duplicate_selected(self) -> None:
            if self.selected_path is None or not isinstance(self.selected_path[-1], int): return
            try: self.selected_path = controller.duplicate_guided_step(self.selected_path); self._changed()
            except Exception as exc: QtWidgets.QMessageBox.critical(self, "Duplicate failed", str(exc))

        def _move_sibling(self, delta: int) -> None:
            if self.selected_path is None or not isinstance(self.selected_path[-1], int): return
            try: self.selected_path = controller.move_guided_step(self.selected_path, delta=delta); self._changed()
            except Exception as exc: QtWidgets.QMessageBox.critical(self, "Move failed", str(exc))

        def _move_selected_to(self) -> None:
            if self.selected_path is None or not isinstance(self.selected_path[-1], int): return
            try: self.selected_path = controller.move_guided_step(self.selected_path, self.move_parent.currentData()); self._changed()
            except Exception as exc: QtWidgets.QMessageBox.critical(self, "Move failed", str(exc))

        def _undo(self) -> None:
            if controller.undo_guided_workflow(): self.selected_path = None; self._changed()

        def _redo(self) -> None:
            if controller.redo_guided_workflow(): self.selected_path = None; self._changed()

        def _apply_recipe(self) -> None:
            name = self.recipe.currentData()
            answer = QtWidgets.QMessageBox.question(
                self, "Replace current draft?", "Applying a recipe replaces the current unsaved experiment draft. Continue?"
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            try:
                controller.apply_workflow_recipe(name)
                self._changed()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Recipe failed", str(exc))

        def _changed(self) -> None:
            self.refresh()
            if on_config_changed is not None:
                on_config_changed()

        def _refresh_outline(self) -> None:
            wanted = self.selected_path; self.outline.blockSignals(True)
            self.outline.clear()
            for node in controller.workflow_tree().children:
                self.outline.addTopLevelItem(self._outline_item(node))
            self.outline.expandAll()
            self.outline.blockSignals(False); self.selected_path = wanted
            if wanted is not None: self._select_outline_path(wanted)

        def _outline_selected(self) -> None:
            items = self.outline.selectedItems(); self.selected_path = tuple(items[0].data(0, 256)) if items and items[0].data(0, 256) is not None else None
            self._refresh_destinations(); self._rebuild_selected_editor()

        def _refresh_destinations(self) -> None:
            destinations = [("Setup", ("setup",)), ("Procedure", ("procedure",)), ("Cleanup", ("cleanup",))]

            def collect(node: Any) -> None:
                if node.kind in {"scan", "average", "measurement", "sequence_sweep"}:
                    destinations.append((node.label, (*node.path, node.kind, "body")))
                elif node.kind == "run":
                    destinations.append((node.label, (*node.path, "run", "steps")))
                elif node.kind == "cleanup":
                    destinations.append((node.label, (*node.path, "cleanup", "steps")))
                for child in node.children:
                    collect(child)

            for root in controller.workflow_tree().children:
                collect(root)
            for combo in (self.structure_parent, self.action_parent, self.move_parent):
                selected = combo.currentData() if combo.count() else None
                combo.blockSignals(True)
                combo.clear()
                for label, path in destinations:
                    if combo is self.move_parent and self.selected_path is not None and tuple(path[:len(self.selected_path)]) == tuple(self.selected_path): continue
                    combo.addItem(label, path)
                if selected:
                    index = combo.findData(selected)
                    if index >= 0:
                        combo.setCurrentIndex(index)
                combo.blockSignals(False)

        def _outline_item(self, node: Any) -> Any:
            item = QtWidgets.QTreeWidgetItem([node.label, node.kind])
            item.setData(0, 256, tuple(node.path))
            for child in node.children:
                item.addChild(self._outline_item(child))
            return item

        def _select_outline_path(self, path: tuple[str | int, ...]) -> bool:
            def visit(item: Any) -> bool:
                if tuple(item.data(0, 256) or ()) == tuple(path): self.outline.setCurrentItem(item); self.outline.scrollToItem(item); return True
                return any(visit(item.child(index)) for index in range(item.childCount()))
            return any(visit(self.outline.topLevelItem(index)) for index in range(self.outline.topLevelItemCount()))

        def _refresh_issues(self) -> None:
            diagnostics = controller.workflow_composer().validate_complete()
            self.issues.setRowCount(0)
            for diagnostic in diagnostics:
                row = self.issues.rowCount()
                self.issues.insertRow(row)
                for column, value in enumerate((diagnostic.severity, diagnostic.code, diagnostic.message)):
                    item = QtWidgets.QTableWidgetItem(str(value)); item.setData(256, tuple(diagnostic.workflow_path or diagnostic.config_path)); self.issues.setItem(row, column, item)

        def _focus_issue(self, row: int, column: int) -> None:
            item = self.issues.item(row, column) or self.issues.item(row, 0); path = tuple(item.data(256) or ()) if item else ()
            if path and self._select_outline_path(path): self.selected_path = path; self._rebuild_selected_editor()

    return GuidedWorkflowWidget()

def _display_value(value: Any) -> str:
    if value is None: return "null"
    if isinstance(value, (list, dict)): return json.dumps(value)
    return str(value)

def _parse_scalar(text: str) -> int | float:
    value = json.loads(text)
    if isinstance(value, bool) or not isinstance(value, (int, float)): raise ValueError(f"Expected a number, got {text!r}")
    return value

def _parse_list(text: str) -> list[Any]:
    raw = text.strip(); value = json.loads(raw if raw.startswith("[") else f"[{raw}]")
    if not isinstance(value, list) or not value: raise ValueError("Explicit values require a non-empty list")
    return value

def _widget_value(widget: Any) -> Any:
    if hasattr(widget, "isChecked"): return bool(widget.isChecked())
    if hasattr(widget, "currentText"): return widget.currentText()
    return widget.text().strip()

def _widget_has_value(widget: Any) -> bool:
    value = _widget_value(widget)
    return not isinstance(value, str) or bool(value)
