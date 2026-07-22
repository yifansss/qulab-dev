"""Schema-driven, Qt-free workflow composition over canonical config mappings."""
from __future__ import annotations
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from qulab.instruments.action_specs import ActionSpec, DEFAULT_ACTION_REGISTRY, validate_action_call
from qulab.config.diagnostics import ConfigDiagnostic
from qulab.config.loader import load_experiment_config

PathPart = str | int
WorkflowPath = tuple[PathPart, ...]

@dataclass(frozen=True)
class PaletteAction:
    resource: str | None
    group: str
    label: str
    kind: str
    action: ActionSpec | None = None
    available: bool = True
    reason: str | None = None

@dataclass(frozen=True)
class RenamePreview:
    old_name: str
    new_name: str
    references: tuple[WorkflowPath, ...]

@dataclass(frozen=True)
class ScanTarget:
    id: str
    label: str
    group: str
    description: str
    unit: str | None
    path: WorkflowPath
    kind: str
    plan_id: str | None = None

STRUCTURAL_KINDS = ("scan", "average", "measurement", "run", "wait", "cleanup", "sequence_sweep")
RECIPE_FILES = {
    "mock_dry_run_scalar_scan": "configs/experiments/dry_run_rabi.yaml",
    "ni_manual_slow_ao_ai": "configs/experiments/bench_06_pse_ai1_manual_slow_scan.template.yaml",
    "ni_master_ao_ai": "configs/experiments/hardware_ni_master_ao_ai.template.yaml",
    "asg_ttl_scope_smoke": "configs/experiments/bench_03_asg_ttl_scope_smoke.template.yaml",
    "asg_master_ni_pse_trace": "configs/experiments/bench_05_pse_ai1_asg_triggered_trace.template.yaml",
    "hardware_rabi_builder": "configs/experiments/hardware_rabi_builder.recipe.yaml",
    "generated_rabi": "configs/experiments/dry_run_rabi_sequence_family.yaml",
    "low_power_odmr": "configs/experiments/dry_run_odmr.yaml",
}

class WorkflowComposerModel:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._undo: list[dict[str, Any]] = []
        self._redo: list[dict[str, Any]] = []
        self.prepared_hash: str | None = None

    def snapshot(self) -> dict[str, Any]: return deepcopy(self.config)

    @property
    def can_undo(self) -> bool: return bool(self._undo)

    @property
    def can_redo(self) -> bool: return bool(self._redo)

    def step(self, path: WorkflowPath) -> dict[str, Any]:
        value = _get(self.config, path)
        if not isinstance(value, dict): raise TypeError("workflow path does not identify a step")
        return deepcopy(value)

    def action_spec(self, path: WorkflowPath) -> tuple[str, ActionSpec] | None:
        step = _get(self.config, path); call = step.get("call") if isinstance(step, dict) else None
        if not isinstance(call, str) or "." not in call: return None
        resource, method = call.split(".", 1); raw = self.config.get("resources", {}).get(resource, {})
        adapter = str(raw.get("adapter") or raw.get("adaptor") or "") if isinstance(raw, dict) else ""
        spec = DEFAULT_ACTION_REGISTRY.resolve_action(adapter, method)
        return (resource, spec) if spec is not None else None

    def list_palette(self, context_path: WorkflowPath = ("procedure",), search: str = "") -> tuple[PaletteAction, ...]:
        section = str(context_path[0]) if context_path else "procedure"
        query = search.lower().strip(); result: list[PaletteAction] = []
        for kind in STRUCTURAL_KINDS:
            item = PaletteAction(None, "Structure", kind.replace("_", " ").title(), kind)
            if not query or query in item.label.lower(): result.append(item)
        resources = self.config.get("resources", {})
        if not isinstance(resources, dict): return tuple(result)
        for resource, raw in resources.items():
            if not isinstance(raw, dict): continue
            adapter = str(raw.get("adapter") or raw.get("adaptor") or "")
            capabilities = set(raw.get("capabilities", ())) or None
            for action in DEFAULT_ACTION_REGISTRY.list_actions(adapter, capabilities):
                group = _phase_group(action.phase)
                available = section in action.allowed_sections
                item = PaletteAction(resource, group, f"{resource}: {action.label}", "call", action, available,
                                     None if available else f"Not allowed in {section}")
                haystack = f"{item.label} {action.method} {action.capability}".lower()
                if not query or query in haystack: result.append(item)
        return tuple(result)

    def list_scan_targets(self) -> tuple[ScanTarget, ...]:
        """Return only concrete parameters that this config can safely bind to a scan."""
        targets: list[ScanTarget] = []
        plans = self.config.get("sequence_plans", {})
        if isinstance(plans, dict):
            for plan_id, plan in plans.items():
                parameters = plan.get("parameters", {}) if isinstance(plan, dict) else {}
                if not isinstance(parameters, dict):
                    continue
                for name, parameter in parameters.items():
                    if not isinstance(parameter, dict):
                        continue
                    path = ("sequence_plans", str(plan_id), "parameters", str(name))
                    targets.append(ScanTarget(
                        _target_id("sequence", path), f"{plan_id} / {name}", "Sequence Sweep",
                        "Regenerates one bundle entry per value and loads it at the matching workflow point.",
                        parameter.get("unit"), path, "sequence", str(plan_id),
                    ))
        resources = self.config.get("resources", {})
        if isinstance(resources, dict):
            for path, step in _walk_steps(self.config.get("procedure", []), ("procedure",)):
                call = step.get("call")
                if not isinstance(call, str) or "." not in call:
                    continue
                resource, method = call.split(".", 1)
                raw = resources.get(resource, {})
                adapter = str(raw.get("adapter") or raw.get("adaptor") or "") if isinstance(raw, dict) else ""
                action = DEFAULT_ACTION_REGISTRY.resolve_action(adapter, method)
                if action is None:
                    continue
                args = step.get("args", {}) if isinstance(step.get("args"), dict) else {}
                for argument in action.arguments:
                    if not argument.allow_reference or argument.dtype not in {"number", "float", "integer", "int"}:
                        continue
                    if argument.name not in args or isinstance(args[argument.name], str):
                        continue
                    argument_path = (*path, "args", argument.name)
                    targets.append(ScanTarget(
                        _target_id("action", argument_path), f"{call} / {argument.name}", "Instrument Action",
                        argument.description or f"Changes {argument.name} before executing {call} at each scan point.",
                        argument.unit, argument_path, "action",
                    ))
        return tuple(targets)

    def configure_scan_target(
        self, target_id: str, name: str, values: dict[str, Any] | list[Any]
    ) -> ScanTarget:
        target = next((item for item in self.list_scan_targets() if item.id == target_id), None)
        if target is None:
            raise KeyError(f"Unknown or no longer available scan target: {target_id}")
        if not name.strip():
            raise ValueError("scan name is required")
        before = self.snapshot()
        if target.kind == "sequence":
            parameter = _get(self.config, target.path)
            parameter.clear()
            if isinstance(values, list):
                parameter.update({"mode": "explicit", "values": deepcopy(values)})
            else:
                parameter.update({"mode": "linspace", **deepcopy(values)})
            if target.unit:
                parameter["unit"] = target.unit
            parameter.setdefault("expose_as", name)
        else:
            step_path = target.path[:-2]
            parent, index = step_path[:-1], _index(step_path)
            siblings = _get(self.config, parent)
            step = deepcopy(siblings[index])
            step["args"][target.path[-1]] = f"${{{name}}}"
            siblings[index] = {"scan": {"name": name, "values": deepcopy(values), "body": [step]}}
        self._commit(before)
        return target

    def insert_structural_step(self, kind: str, parent: WorkflowPath, index: int | None = None) -> WorkflowPath:
        if kind not in STRUCTURAL_KINDS: raise ValueError(f"unsupported structural step: {kind}")
        step = _default_step(kind)
        return self._insert(parent, step, index)

    def insert_action(self, resource: str, action: ActionSpec, values: dict[str, Any], parent: WorkflowPath, index: int | None = None, save_as: str | None = None) -> WorkflowPath:
        issues = validate_action_call(action, values, self.available_references(parent))
        errors = [i for i in issues if i.severity == "error"]
        if errors: raise ValueError("; ".join(i.message for i in errors))
        step: dict[str, Any] = {"call": f"{resource}.{action.method}", "args": deepcopy(values)}
        if save_as: step["save_as"] = save_as
        return self._insert(parent, step, index)

    def duplicate(self, path: WorkflowPath) -> WorkflowPath:
        parent, index = path[:-1], _index(path); return self._insert(parent, deepcopy(_get(self.config, path)), index + 1)

    def delete(self, path: WorkflowPath) -> None:
        before = self.snapshot(); del _get(self.config, path[:-1])[_index(path)]; self._commit(before)

    def update_action(self, path: WorkflowPath, values: dict[str, Any], save_as: str | None,
                      *, enabled: bool = True) -> None:
        resolved = self.action_spec(path)
        if resolved is not None:
            _resource, action = resolved
            issues = validate_action_call(action, values, self.available_references(path))
            errors = [item for item in issues if item.severity == "error"]
            if errors: raise ValueError("; ".join(item.message for item in errors))
        before = self.snapshot(); step = _get(self.config, path)
        step["args"] = deepcopy(values)
        if save_as: step["save_as"] = save_as
        else: step.pop("save_as", None)
        _set_enabled(step, enabled); self._commit(before)

    def update_structural(self, path: WorkflowPath, fields: dict[str, Any], *, enabled: bool = True) -> None:
        step = _get(self.config, path); kind = _step_kind(step)
        if kind not in STRUCTURAL_KINDS: raise ValueError("selected step is not an editable workflow block")
        before = self.snapshot(); payload = step[kind]
        if kind == "scan":
            name = str(fields.get("name") or "").strip()
            if not name: raise ValueError("scan name is required")
            old = payload.get("name"); payload["name"] = name; payload["values"] = deepcopy(fields["values"])
            if isinstance(old, str) and old != name:
                for ref_path in _find_value_paths(self.config, f"${{{old}}}"):
                    _set(self.config, ref_path, f"${{{name}}}")
        elif kind == "average":
            count = int(fields.get("count", 1))
            if count < 1: raise ValueError("average count must be >= 1")
            payload["name"] = str(fields.get("name") or "average"); payload["count"] = count
        elif kind in {"measurement", "cleanup"}:
            payload["name"] = str(fields.get("name") or kind)
        elif kind == "run":
            timeout = float(fields.get("timeout_s", 10.0))
            if timeout <= 0: raise ValueError("run timeout_s must be > 0")
            payload["name"] = str(fields.get("name") or "run"); payload["timeout_s"] = timeout
        elif kind == "wait":
            duration = float(fields.get("duration_s", 0.1))
            if duration < 0: raise ValueError("wait duration_s must be >= 0")
            payload["name"] = str(fields.get("name") or "wait"); payload["duration_s"] = duration
        elif kind == "sequence_sweep":
            plan = str(fields.get("plan") or "").strip()
            if plan not in (self.config.get("sequence_plans", {}) or {}): raise ValueError(f"unknown sequence plan: {plan}")
            payload["plan"] = plan
        _set_enabled(step, enabled); self._commit(before)

    def move_sibling(self, path: WorkflowPath, delta: int) -> WorkflowPath:
        siblings = _get(self.config, path[:-1]); index = _index(path); target = index + int(delta)
        if not isinstance(siblings, list) or target < 0 or target >= len(siblings): return path
        before = self.snapshot(); siblings.insert(target, siblings.pop(index)); self._commit(before)
        return (*path[:-1], target)

    def move(self, path: WorkflowPath, parent: WorkflowPath, index: int | None = None) -> WorkflowPath:
        if tuple(parent[:len(path)]) == tuple(path): raise ValueError("cannot move a step inside itself")
        source = _get(self.config, path[:-1]); target = _get(self.config, parent)
        if not isinstance(source, list) or not isinstance(target, list): raise TypeError("move paths must identify workflow lists")
        if source is target:
            desired = len(source) - 1 if index is None else max(0, min(int(index), len(source) - 1))
            return self.move_sibling(path, desired - _index(path))
        before = self.snapshot(); step = source.pop(_index(path)); insertion = len(target) if index is None else max(0, min(int(index), len(target)))
        target.insert(insertion, step); self._commit(before)
        return (*parent, insertion)

    def wrap_steps(self, paths: Iterable[WorkflowPath], kind: str) -> WorkflowPath:
        selected = sorted(tuple(paths), key=lambda p: _index(p))
        if not selected or any(p[:-1] != selected[0][:-1] for p in selected): raise ValueError("wrapped steps must be siblings")
        if kind not in {"scan", "average", "measurement", "run", "cleanup"}: raise ValueError(f"unsupported wrapper: {kind}")
        before = self.snapshot(); parent = selected[0][:-1]; siblings = _get(self.config, parent)
        items = [deepcopy(siblings[_index(p)]) for p in selected]
        for p in reversed(selected): del siblings[_index(p)]
        wrapper = _default_step(kind); payload = wrapper[kind]; payload["steps" if kind in {"run", "cleanup"} else "body"] = items
        insertion = _index(selected[0]); siblings.insert(insertion, wrapper); self._commit(before); return (*parent, insertion)

    def available_references(self, path: WorkflowPath) -> set[str]:
        refs = set(self.config.get("parameters", {})) if isinstance(self.config.get("parameters"), dict) else set()
        cursor: WorkflowPath = ()
        for part in path:
            cursor = (*cursor, part)
            try: node = _get(self.config, cursor)
            except (KeyError, IndexError, TypeError): continue
            if isinstance(node, dict) and isinstance(node.get("scan"), dict) and isinstance(node["scan"].get("name"), str): refs.add(node["scan"]["name"])
        plans = self.config.get("sequence_plans", {})
        if isinstance(plans, dict):
            for plan in plans.values():
                if isinstance(plan, dict):
                    for name, value in (plan.get("parameters", {}) or {}).items():
                        if isinstance(value, dict): refs.add(str(value.get("expose_as") or name))
        return refs

    def preview_rename_scan(self, path: WorkflowPath, new_name: str) -> RenamePreview:
        step = _get(self.config, path); old = step.get("scan", {}).get("name")
        if not isinstance(old, str): raise ValueError("path is not a named scan")
        return RenamePreview(old, new_name, tuple(_find_value_paths(self.config, f"${{{old}}}")))

    def rename_scan(self, path: WorkflowPath, new_name: str, *, update_references: bool = True) -> RenamePreview:
        preview = self.preview_rename_scan(path, new_name); before = self.snapshot(); _get(self.config, path)["scan"]["name"] = new_name
        if update_references:
            for ref_path in preview.references: _set(self.config, ref_path, f"${{{new_name}}}")
        self._commit(before); return preview

    def validate_incremental(self) -> tuple[ConfigDiagnostic, ...]: return self.validate_complete()

    def validate_complete(self) -> tuple[ConfigDiagnostic, ...]:
        diagnostics: list[ConfigDiagnostic] = []; resources = self.config.get("resources", {}) if isinstance(self.config.get("resources"), dict) else {}
        states: dict[str, set[str]] = {name: set() for name in resources}; active: set[str] = set(); save_keys: set[str] = set()
        sequence_macros: set[str] = set(); sequence_plans = self.config.get("sequence_plans", {}) if isinstance(self.config.get("sequence_plans"), dict) else {}
        safety = self.config.get("safety", {}) if isinstance(self.config.get("safety"), dict) else {}; allow_output = bool(safety.get("allow_output"))
        for section in ("setup", "procedure", "cleanup"):
            for path, step in _walk_steps(self.config.get(section, []), (section,)):
                macro = step.get("sequence_sweep")
                if isinstance(macro, dict):
                    plan_id = str(macro.get("plan") or "")
                    if plan_id not in sequence_plans: diagnostics.append(ConfigDiagnostic("error", "sequence_plan_not_found", f"Unknown sequence plan '{plan_id}'.", path, path))
                    elif plan_id in sequence_macros: diagnostics.append(ConfigDiagnostic("error", "sequence_macro_duplicate", f"Sequence plan '{plan_id}' is linked more than once.", path, path))
                    sequence_macros.add(plan_id)
                call = step.get("call")
                if not isinstance(call, str) or "." not in call: continue
                resource, method = call.split(".", 1)
                if resource not in resources:
                    diagnostics.append(ConfigDiagnostic("error", "action_resource_unknown", f"Unknown resource '{resource}'.", path, path)); continue
                raw = resources[resource]; adapter = raw.get("adapter") if isinstance(raw, dict) else None
                spec = DEFAULT_ACTION_REGISTRY.resolve_action(str(adapter), method)
                if spec is None:
                    diagnostics.append(ConfigDiagnostic("warning", "action_schema_incomplete", f"No ActionSpec for {call}.", path, path)); continue
                if method == "compile_sequence" and "sequence_sweep" in path:
                    states[resource].add("sequence_loaded")
                missing = set(spec.requires_states) - states[resource]
                if missing: diagnostics.append(ConfigDiagnostic("error", "workflow_lifecycle_missing", f"{call} requires state(s): {', '.join(sorted(missing))}.", path, path))
                if spec.safety_class in {"output", "analog_output", "unknown"} and not allow_output and section != "cleanup":
                    diagnostics.append(ConfigDiagnostic("warning", "unsafe_action_not_authorized", f"{call} requires explicit output authorization.", path, path))
                states[resource].difference_update(spec.invalidates_states); states[resource].update(spec.provides_states)
                if {"running", "output_enabled"} & states[resource]: active.add(resource)
                if spec.phase == "cleanup": active.discard(resource)
                save_as = step.get("save_as")
                if spec.returns and spec.returns.save_recommended and not save_as:
                    diagnostics.append(ConfigDiagnostic("warning", "action_result_unsaved", f"Data-producing action {call} has no save_as.", path, path))
                if isinstance(save_as, str):
                    if save_as in save_keys: diagnostics.append(ConfigDiagnostic("error", "data_key_collision", f"Duplicate save_as '{save_as}'.", path, path))
                    save_keys.add(save_as)
        for resource in sorted(active): diagnostics.append(ConfigDiagnostic("warning", "cleanup_missing", f"Resource '{resource}' may remain running or output-enabled; add cleanup.", ("cleanup",)))
        return tuple(diagnostics)

    def apply_recipe(self, name: str, *, project_root: Path | None = None) -> None:
        if name not in RECIPE_FILES: raise KeyError(name)
        root = project_root or Path(__file__).resolve().parents[3]
        replacement = load_experiment_config(root / RECIPE_FILES[name]); before = self.snapshot(); self.config.clear(); self.config.update(replacement)
        safety = self.config.setdefault("safety", {}); safety["allow_output"] = False; safety["physical_verification"] = False; self._commit(before)

    def undo(self) -> bool:
        if not self._undo: return False
        self._redo.append(self.snapshot()); previous = self._undo.pop(); self.config.clear(); self.config.update(previous); self.prepared_hash = None; return True
    def redo(self) -> bool:
        if not self._redo: return False
        self._undo.append(self.snapshot()); nxt = self._redo.pop(); self.config.clear(); self.config.update(nxt); self.prepared_hash = None; return True
    def mark_prepared(self, plan_hash: str) -> None: self.prepared_hash = plan_hash
    def _insert(self, parent: WorkflowPath, step: dict[str, Any], index: int | None) -> WorkflowPath:
        before = self.snapshot(); target = _get(self.config, parent)
        if not isinstance(target, list): raise TypeError("parent path must identify a workflow list")
        insertion = len(target) if index is None else index; target.insert(insertion, step); self._commit(before); return (*parent, insertion)
    def _commit(self, before: dict[str, Any]) -> None: self._undo.append(before); self._redo.clear(); self.prepared_hash = None

def convert_form_values(action: ActionSpec, raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}; specs = {a.name: a for a in action.arguments}
    for name, value in raw.items():
        spec = specs.get(name)
        if spec is None: result[name] = value; continue
        if isinstance(value, str) and value.startswith("${"): result[name] = value
        elif spec.dtype in {"number", "float"}: result[name] = float(value)
        elif spec.dtype in {"integer", "int"}: result[name] = int(value)
        elif spec.dtype == "boolean" and isinstance(value, str): result[name] = value.lower() in {"1", "true", "yes", "on"}
        elif spec.dtype == "list" and isinstance(value, str):
            parsed = json.loads(value) if value.lstrip().startswith("[") else [item.strip() for item in value.split(",") if item.strip()]
            result[name] = parsed
        elif spec.dtype == "mapping" and isinstance(value, str): result[name] = json.loads(value)
        elif spec.dtype in {"any", "object"} and isinstance(value, str) and value.strip().lower() in {"none", "null"}: result[name] = None
        else: result[name] = value
    return result

def _default_step(kind: str) -> dict[str, Any]:
    return {"scan": {"name": "scan", "values": [0, 1], "body": []}} if kind == "scan" else {"average": {"name": "avg", "count": 1, "body": []}} if kind == "average" else {"measurement": {"name": "measurement", "body": []}} if kind == "measurement" else {"run": {"name": "run", "timeout_s": 10.0, "steps": []}} if kind == "run" else {"wait": {"name": "wait", "duration_s": 0.1}} if kind == "wait" else {"cleanup": {"name": "cleanup", "steps": []}} if kind == "cleanup" else {"sequence_sweep": {"plan": "sequence_plan"}}
def _get(root: Any, path: WorkflowPath) -> Any:
    for part in path: root = root[part]
    return root
def _set(root: Any, path: WorkflowPath, value: Any) -> None: _get(root, path[:-1])[path[-1]] = value
def _index(path: WorkflowPath) -> int:
    if not path or not isinstance(path[-1], int): raise ValueError("path must end in list index")
    return path[-1]
def _find_value_paths(value: Any, wanted: Any, path: WorkflowPath = ()) -> list[WorkflowPath]:
    result: list[WorkflowPath] = []
    if value == wanted: result.append(path)
    elif isinstance(value, dict):
        for key, item in value.items(): result.extend(_find_value_paths(item, wanted, (*path, key)))
    elif isinstance(value, list):
        for index, item in enumerate(value): result.extend(_find_value_paths(item, wanted, (*path, index)))
    return result
def _walk_steps(steps: Any, path: WorkflowPath):
    if not isinstance(steps, list): return
    for i, step in enumerate(steps):
        if not isinstance(step, dict): continue
        p = (*path, i); yield p, step
        for kind in ("scan", "average", "measurement", "run", "cleanup", "sequence_sweep"):
            payload = step.get(kind)
            if isinstance(payload, dict):
                key = "steps" if kind in {"run", "cleanup"} and "steps" in payload else "body"
                yield from _walk_steps(payload.get(key), (*p, kind, key))
def _phase_group(phase: str) -> str:
    return {"configure": "Configure", "arm": "Arm / Start", "start": "Arm / Start", "read": "Acquire / Read", "stop": "Stop / Cleanup", "cleanup": "Stop / Cleanup"}.get(phase, "Task")

def _target_id(kind: str, path: WorkflowPath) -> str:
    return f"{kind}:" + "/".join(str(part) for part in path)

def _step_kind(step: dict[str, Any]) -> str:
    return next((kind for kind in ("call", *STRUCTURAL_KINDS) if kind in step), "unknown")

def _set_enabled(step: dict[str, Any], enabled: bool) -> None:
    if enabled: step.pop("enabled", None)
    else: step["enabled"] = False
