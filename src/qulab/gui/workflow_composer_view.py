"""Qt factory for the schema-driven guided workflow composer."""

from __future__ import annotations

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
            review_layout.addWidget(self.outline, 1)
            review_layout.addWidget(QtWidgets.QLabel("Continuity checks / 连贯性检查"))
            self.issues = QtWidgets.QTableWidget(0, 3)
            self.issues.setHorizontalHeaderLabels(["Severity", "Code", "Message"])
            self.issues.horizontalHeader().setStretchLastSection(True)
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
            self._refresh_destinations()
            self._refresh_palette()
            self._refresh_outline()
            self._refresh_issues()

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
                editor = QtWidgets.QLineEdit()
                if argument.default is not MISSING and argument.default is not None:
                    editor.setText(str(argument.default))
                label = argument.name + (" *" if argument.required else "")
                if argument.unit:
                    label += f" [{argument.unit}]"
                editor.setToolTip(argument.description or argument.dtype)
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
            raw = {name: editor.text().strip() for name, editor in self._fields.items() if editor.text().strip()}
            try:
                values = convert_form_values(item.action, raw)
                controller.insert_guided_action(item.resource, item.action, values, self.action_parent.currentData(), self.save_as.text().strip() or None)
                self.save_as.clear()
                self._changed()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Action insertion failed", str(exc))

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
            self.outline.clear()
            for node in controller.workflow_tree().children:
                self.outline.addTopLevelItem(self._outline_item(node))
            self.outline.expandAll()

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
            for combo in (self.structure_parent, self.action_parent):
                selected = combo.currentData() if combo.count() else None
                combo.blockSignals(True)
                combo.clear()
                for label, path in destinations:
                    combo.addItem(label, path)
                if selected:
                    index = combo.findData(selected)
                    if index >= 0:
                        combo.setCurrentIndex(index)
                combo.blockSignals(False)

        def _outline_item(self, node: Any) -> Any:
            item = QtWidgets.QTreeWidgetItem([node.label, node.kind])
            for child in node.children:
                item.addChild(self._outline_item(child))
            return item

        def _refresh_issues(self) -> None:
            diagnostics = controller.workflow_composer().validate_complete()
            self.issues.setRowCount(0)
            for diagnostic in diagnostics:
                row = self.issues.rowCount()
                self.issues.insertRow(row)
                for column, value in enumerate((diagnostic.severity, diagnostic.code, diagnostic.message)):
                    self.issues.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))

    return GuidedWorkflowWidget()
