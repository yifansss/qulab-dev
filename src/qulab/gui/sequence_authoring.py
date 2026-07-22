"""Ordered, Qt-free sequence authoring facade over ``sequence_plans``."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qulab.sequence_generation.preparation import parse_sequence_plans
from qulab.sequence_generation.providers.asg_model import inspect_template
from qulab.sequence_generation.registry import DEFAULT_PROVIDER_REGISTRY
from qulab.sequence_generation.sampling import enumerate_plan_points, normalize_parameter_values
from .sequence_bridge import inspect_sequence_file
from .sequence_sweep_model import SequenceIssueViewModel, SequenceSweepEditorModel

AUTHORING_STEPS = (
    "resource_mode", "source", "channel_roles", "fixed_parameters", "sweep_parameters",
    "targets_propagation", "preview_compare", "validation_prepare", "bundle_provenance",
)
MODES = ("curated", "generic", "standalone")

@dataclass(frozen=True)
class AuthoringStepStatus:
    id: str; enabled: bool; complete: bool; message: str = ""

@dataclass(frozen=True)
class ModeMigrationPreview:
    old_mode: str; new_mode: str; removed_paths: tuple[str, ...]; retained_paths: tuple[str, ...]

@dataclass(frozen=True)
class SequenceParameterField:
    name: str; label: str; dtype: str; unit: str | None; default: Any
    minimum: float | None; maximum: float | None; choices: tuple[Any, ...] | None; sweepable: bool; description: str | None

@dataclass(frozen=True)
class PreviewSet:
    first: Any; current: Any; last: Any; coordinates: tuple[dict[str, Any], ...]; point_count: int

class SequenceAuthoringModel:
    def __init__(self, config: dict[str, Any], sweep_model: SequenceSweepEditorModel | None = None) -> None:
        self.config = config; self.sweep = sweep_model or SequenceSweepEditorModel.load(config)
        self._template_hashes: dict[str, str] = {}

    def mode(self, plan_id: str) -> str:
        raw = self._raw(plan_id); provider = raw.get("family", {}).get("provider") if isinstance(raw.get("family"), dict) else None
        if raw.get("options", {}).get("authoring_mode") == "standalone": return "standalone"
        return "generic" if provider == "asg_template" else "curated"

    def ordered_status(self, plan_id: str) -> tuple[AuthoringStepStatus, ...]:
        raw = self._raw(plan_id); resource_ok = raw.get("resource") in (self.config.get("resources") or {})
        source_ok = bool(raw.get("family", {}).get("provider")) and (self.mode(plan_id) == "curated" or bool(raw.get("template")))
        targets_ok = self.mode(plan_id) == "curated" or bool(raw.get("targets"))
        prior = [resource_ok, source_ok, source_ok, source_ok, source_ok, targets_ok, source_ok, source_ok, False]
        result = []
        for index, name in enumerate(AUTHORING_STEPS):
            enabled = index == 0 or all(prior[:index]); complete = prior[index]
            result.append(AuthoringStepStatus(name, enabled, complete, "" if enabled else "Complete earlier steps first."))
        return tuple(result)

    def parameter_fields(self, plan_id: str) -> tuple[SequenceParameterField, ...]:
        plan = parse_sequence_plans(self.config)[plan_id]; provider, _ = DEFAULT_PROVIDER_REGISTRY.load(plan.provider, plan.provider_version)
        return tuple(SequenceParameterField(p.name, p.label, p.dtype, p.unit, p.default, p.minimum, p.maximum, p.choices, p.sweepable, p.description)
                     for p in provider.describe().parameters)

    def preview_mode_change(self, plan_id: str, new_mode: str) -> ModeMigrationPreview:
        if new_mode not in MODES: raise ValueError(new_mode)
        old = self.mode(plan_id); raw = self._raw(plan_id); removed = []
        if old != new_mode:
            if new_mode == "curated": removed += [k for k in ("template", "targets", "groups", "constraints") if k in raw]
            elif new_mode in {"generic", "standalone"}: removed += ["family.provider", "parameters"]
        retained = tuple(k for k in ("resource", "materialize", "sampling") if k in raw)
        return ModeMigrationPreview(old, new_mode, tuple(removed), retained)

    def change_mode(self, plan_id: str, new_mode: str, *, provider: str | None = None, template: str | None = None) -> ModeMigrationPreview:
        preview = self.preview_mode_change(plan_id, new_mode); raw = self._raw(plan_id)
        if new_mode == "curated":
            if not provider or provider == "asg_template": raise ValueError("curated mode requires a curated provider")
            loaded, _ = DEFAULT_PROVIDER_REGISTRY.load(provider); spec = loaded.describe()
            raw.pop("template", None); raw.pop("targets", None); raw.pop("groups", None); raw.pop("constraints", None)
            raw["family"] = {"provider": provider, "version": spec.version}
            raw["parameters"] = {p.name: {"mode": "fixed", "value": p.default, **({"unit": p.unit} if p.unit else {})} for p in spec.parameters}
        else:
            if not template: raise ValueError(f"{new_mode} mode requires a sequence template")
            raw["family"] = {"provider": "asg_template", "version": "1"}; raw["template"] = template
            raw.setdefault("targets", {}); raw.setdefault("parameters", {}); raw.setdefault("options", {})["authoring_mode"] = new_mode
            info = inspect_sequence_file(template)
            if info.sha256: self._template_hashes[plan_id] = info.sha256
        self.sweep._edited(plan_id); return preview

    def generic_operation_catalog(self) -> dict[str, tuple[str, ...]]:
        return {"Basic Timing": ("duration", "start", "end", "shift", "gap_after"),
                "Propagation": ("none", "shift_after", "shift_group"), "Constraints": ("anchor",),
                "Preview": ("first", "current", "last", "overlay", "difference"), "Build": ("validate", "estimate", "prepare", "inspect_bundle")}

    def inspect_generic_template(self, plan_id: str):
        raw = self._raw(plan_id); template = raw.get("template")
        if not template: raise ValueError("plan has no template")
        inspection = inspect_template(template); self._template_hashes.setdefault(plan_id, inspection.template_sha256); return inspection

    def previews(self, plan_id: str, current_index: int | None = None) -> PreviewSet:
        plan = parse_sequence_plans(self.config)[plan_id]; provider, _ = DEFAULT_PROVIDER_REGISTRY.load(plan.provider, plan.provider_version)
        if callable(getattr(provider, "configure_plan", None)): provider.configure_plan(plan)
        values = normalize_parameter_values(plan, provider.describe()); points = enumerate_plan_points(plan, values)
        if not points: raise ValueError("sequence plan has no points")
        index = min(max(current_index if current_index is not None else len(points) // 2, 0), len(points) - 1)
        def preview(point): return provider.preview_point(point.parameters, template=plan.template)
        return PreviewSet(preview(points[0]), preview(points[index]), preview(points[-1]), tuple(dict(p.coordinates) for p in points), len(points))

    def validate(self, plan_id: str) -> tuple[SequenceIssueViewModel, ...]:
        issues: list[SequenceIssueViewModel] = []; raw = self._raw(plan_id)
        try:
            plan = parse_sequence_plans(self.config)[plan_id]; provider, _ = DEFAULT_PROVIDER_REGISTRY.load(plan.provider, plan.provider_version)
            result = provider.validate_plan(plan)
            issues.extend(SequenceIssueViewModel(i.severity, i.code, i.message) for i in result.issues)
            estimate = self.sweep.estimate(plan_id); maximum = int(raw.get("materialize", {}).get("max_points", 10000))
            if estimate.point_count > maximum: issues.append(SequenceIssueViewModel("error", "sequence_point_limit", f"{estimate.point_count} points exceed limit {maximum}."))
            template = raw.get("template")
            if template:
                info = inspect_sequence_file(template); known = self._template_hashes.get(plan_id)
                if not info.exists: issues.append(SequenceIssueViewModel("error", "sequence_template_not_found", f"Template not found: {template}"))
                elif known and info.sha256 != known: issues.append(SequenceIssueViewModel("error", "sequence_template_stale", "Template changed externally; re-inspect before Prepare."))
        except Exception as exc:
            issues.append(SequenceIssueViewModel("error", getattr(exc, "code", "sequence_plan_invalid"), str(exc)))
        if not _has_macro(self.config, plan_id): issues.append(SequenceIssueViewModel("warning", "sequence_workflow_link_missing", f"Workflow has no sequence_sweep macro for '{plan_id}'."))
        return tuple(issues)

    def insert_or_update_macro(self, plan_id: str, parent: tuple[str | int, ...] = ("procedure",), index: int | None = None) -> tuple[str | int, ...]:
        for path, step in _walk(self.config.get("procedure", []), ("procedure",)):
            if isinstance(step.get("sequence_sweep"), dict) and step["sequence_sweep"].get("plan") == plan_id: return path
        target: Any = self.config
        for part in parent: target = target[part]
        entry = {"sequence_sweep": {"plan": plan_id}}; insertion = len(target) if index is None else index; target.insert(insertion, entry)
        self.sweep._edited(plan_id); return (*parent, insertion)

    def accept_editor_result(self, plan_id: str, saved_artifact: dict[str, Any] | None) -> None:
        if not saved_artifact or not saved_artifact.get("path") or not saved_artifact.get("sha256"): raise ValueError("Editor did not report a saved artifact")
        info = inspect_sequence_file(saved_artifact["path"])
        if not info.exists or info.sha256 != saved_artifact["sha256"]: raise ValueError("Saved editor artifact hash mismatch")
        self._raw(plan_id)["template"] = saved_artifact["path"]; self._template_hashes[plan_id] = info.sha256; self.sweep._edited(plan_id)

    def _raw(self, plan_id: str) -> dict[str, Any]:
        value = self.config.get("sequence_plans", {}).get(plan_id)
        if not isinstance(value, dict): raise KeyError(plan_id)
        return value

def _walk(steps: Any, path: tuple[str | int, ...]):
    if not isinstance(steps, list): return
    for index, step in enumerate(steps):
        if not isinstance(step, dict): continue
        p = (*path, index); yield p, step
        for kind in ("scan", "average", "measurement", "run", "cleanup"):
            payload = step.get(kind)
            if isinstance(payload, dict):
                key = "steps" if kind in {"run", "cleanup"} and "steps" in payload else "body"
                yield from _walk(payload.get(key), (*p, kind, key))
def _has_macro(config: dict[str, Any], plan_id: str) -> bool:
    return any(isinstance(step.get("sequence_sweep"), dict) and step["sequence_sweep"].get("plan") == plan_id for _, step in _walk(config.get("procedure", []), ("procedure",)))
