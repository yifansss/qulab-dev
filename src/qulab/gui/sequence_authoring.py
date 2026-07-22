"""Ordered, Qt-free sequence authoring facade over ``sequence_plans``."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from qulab.sequence_generation.preparation import parse_sequence_plans
from qulab.sequence_generation.providers.asg_model import inspect_template
from qulab.sequence_generation.registry import DEFAULT_PROVIDER_REGISTRY
from qulab.sequence_generation.sampling import enumerate_plan_points, normalize_parameter_values
from qulab.instruments.action_specs import DEFAULT_ACTION_REGISTRY as ACTION_REGISTRY
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

@dataclass(frozen=True)
class NormalizedPulse:
    channel: str
    pulse: int
    start_s: float
    end_s: float
    label: str | None = None
    alias: str | None = None

    @property
    def duration_s(self) -> float: return self.end_s - self.start_s

@dataclass(frozen=True)
class NormalizedPreview:
    pulses: tuple[NormalizedPulse, ...]
    channels: tuple[str, ...]
    duration_s: float

@dataclass(frozen=True)
class LocatedSequenceIssue:
    severity: str
    code: str
    message: str
    step: str
    field: str | None = None
    hint: str | None = None

class SequenceAuthoringModel:
    def __init__(self, config: dict[str, Any], sweep_model: SequenceSweepEditorModel | None = None) -> None:
        self.config = config; self.sweep = sweep_model or SequenceSweepEditorModel.load(config)
        self._template_hashes: dict[str, str] = {}

    def mode(self, plan_id: str) -> str:
        raw = self._raw(plan_id); provider = raw.get("family", {}).get("provider") if isinstance(raw.get("family"), dict) else None
        if raw.get("options", {}).get("authoring_mode") == "standalone": return "standalone"
        return "generic" if provider == "asg_template" or str(provider).endswith(".asg_template") else "curated"

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
        spec = provider.describe()
        fields = [SequenceParameterField(p.name, p.label, p.dtype, p.unit, p.default, p.minimum, p.maximum, p.choices, p.sweepable, p.description)
                  for p in spec.parameters]
        if spec.dynamic_parameters:
            known = {item.name for item in fields}
            for name, value in plan.parameters.items():
                if name not in known:
                    fields.append(SequenceParameterField(name, name, "float", value.unit or "s",
                                                         value.value if value.value is not None else 0.0,
                                                         None, None, None, True, "Template transform parameter"))
        return tuple(fields)

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
        current_provider = raw.get("family", {}).get("provider") if isinstance(raw.get("family"), dict) else None
        if preview.old_mode == new_mode and new_mode == "curated" and provider == current_provider:
            return preview
        if preview.old_mode == new_mode and new_mode in {"generic", "standalone"}:
            if not template: raise ValueError(f"{new_mode} mode requires a sequence template")
            raw["template"] = template; raw.setdefault("options", {})["authoring_mode"] = new_mode
            info = inspect_sequence_file(template)
            if info.sha256: self._template_hashes[plan_id] = info.sha256
            self.sweep._edited(plan_id); return preview
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

    def update_roles(self, plan_id: str, roles: dict[str, str], *, confirmed: bool = True) -> None:
        raw = self._raw(plan_id)
        options = raw.setdefault("options", {})
        options["channels"] = {str(key): str(value) for key, value in roles.items() if str(value).strip()}
        options["channel_roles_confirmed"] = bool(confirmed)
        self.sweep._edited(plan_id)

    def update_resource(self, plan_id: str, resource: str) -> None:
        resources = self.config.get("resources", {})
        if not isinstance(resources, dict) or resource not in resources:
            raise ValueError(f"Unknown sequence resource: {resource}")
        self._raw(plan_id)["resource"] = resource
        self.sweep._edited(plan_id)

    def update_parameter(self, plan_id: str, name: str, patch: dict[str, Any]) -> None:
        fields = {item.name: item for item in self.parameter_fields(plan_id)}
        field = fields.get(name)
        if field is not None and not field.sweepable and patch.get("mode", "fixed") != "fixed":
            raise ValueError(f"Parameter '{name}' is not sweepable")
        previous = deepcopy(self._raw(plan_id))
        try:
            self.sweep.update_parameter(plan_id, name, patch)
            # Normalization is the authoritative dtype/range/unit check and
            # does not materialize provider output.
            plan = parse_sequence_plans(self.config)[plan_id]
            provider, _ = DEFAULT_PROVIDER_REGISTRY.load(plan.provider, plan.provider_version)
            normalize_parameter_values(plan, provider.describe())
        except Exception:
            self.config["sequence_plans"][plan_id] = previous
            raise

    def update_target_transform(
        self, plan_id: str, alias: str, channel: str, pulse: int, *, parameter: str,
        property_name: str, propagation: str = "none", group: str | None = None,
        scope: str = "same_channel",
    ) -> None:
        operations = self.generic_operation_catalog()
        if property_name not in operations["Basic Timing"]: raise ValueError(f"Unsupported property: {property_name}")
        if propagation not in operations["Propagation"]: raise ValueError(f"Unsupported propagation: {propagation}")
        inspection = self.inspect_generic_template(plan_id)
        channel_row = next((item for item in inspection.channels if str(item.get("name")) == channel), None)
        pulses = channel_row.get("pulses", ()) if channel_row else ()
        if not isinstance(pulse, int) or pulse < 0 or pulse >= len(pulses): raise ValueError("Selected pulse does not exist")
        fingerprint = str(pulses[pulse].get("fingerprint"))
        self.sweep.update_target(plan_id, alias, {"channel": channel, "pulse": pulse, "fingerprint": fingerprint})
        raw = self._raw(plan_id); parameters = raw.setdefault("parameters", {})
        current = dict(parameters.get(parameter, {"mode": "fixed", "value": 0.0, "unit": "s"}))
        propagation_map: dict[str, Any] = {"mode": propagation}
        if propagation == "shift_after": propagation_map["scope"] = scope
        if propagation == "shift_group":
            if not group: raise ValueError("Shift group requires a group name")
            propagation_map["group"] = group
        current["transform"] = {"target": alias, "property": property_name, "propagation": propagation_map}
        parameters[parameter] = current
        self.sweep._edited(plan_id)

    def set_target_group(self, plan_id: str, name: str, aliases: list[str]) -> None:
        if not name.strip() or not aliases or len(set(aliases)) != len(aliases): raise ValueError("Group needs a name and unique targets")
        self._raw(plan_id).setdefault("groups", {})[name] = list(aliases); self.sweep._edited(plan_id)

    def add_anchor_constraint(self, plan_id: str, target: str, reference: str, offset_s: float = 0.0) -> None:
        raw = self._raw(plan_id); constraints = list(raw.get("constraints", []))
        constraints.append({"type": "anchor", "target": target, "reference": reference, "offset_s": float(offset_s)})
        self.sweep.update_constraints(plan_id, constraints)

    def normalized_previews(self, plan_id: str, current_index: int | None = None) -> tuple[NormalizedPreview, NormalizedPreview, NormalizedPreview]:
        previews = self.previews(plan_id, current_index)
        return tuple(_normalize_preview(item) for item in (previews.first, previews.current, previews.last))  # type: ignore[return-value]

    def revision(self, plan_id: str) -> str:
        payload = json.dumps(self._raw(plan_id), sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(payload).hexdigest()

    def located_issues(self, plan_id: str) -> tuple[LocatedSequenceIssue, ...]:
        return tuple(_locate_issue(item) for item in self.validate(plan_id))

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
        issues.extend(self._integration_issues(plan_id))
        if self.sweep.states.get(plan_id) == "stale":
            issues.append(SequenceIssueViewModel("error", "sequence_prepared_stale", "Sequence plan changed after Prepare; prepare it again."))
        return tuple(issues)

    def _integration_issues(self, plan_id: str) -> list[SequenceIssueViewModel]:
        issues: list[SequenceIssueViewModel] = []; raw = self._raw(plan_id); resource = str(raw.get("resource") or "")
        macro = _find_macro(self.config, plan_id)
        if macro is None:
            issues.append(SequenceIssueViewModel("warning", "sequence_workflow_link_missing", f"Workflow has no sequence_sweep macro for '{plan_id}'."))
        else:
            calls = {str(step.get("call")) for _, step in _walk_steps_in_macro(macro)}
            required = {f"{resource}.compile_sequence", f"{resource}.arm", f"{resource}.start"}
            missing = sorted(required - calls)
            if missing: issues.append(SequenceIssueViewModel("error", "sequence_workflow_actions_missing", f"Sequence workflow is missing: {', '.join(missing)}"))
            if not any(call.endswith((".read", ".read_counts", ".read_analog")) for call in calls):
                issues.append(SequenceIssueViewModel("error", "sequence_workflow_read_missing", "Sequence workflow has no acquisition read action."))
        options = raw.get("options", {}) if isinstance(raw.get("options"), dict) else {}
        trigger_channels = {_normalize_channel(str(item)) for item in options.get("trigger_channels", ())}
        sync = self.config.get("sync", {}) if isinstance(self.config.get("sync"), dict) else {}
        sync_sources = {
            _normalize_channel(str(item.get("source", "")).split(".", 1)[1])
            for item in sync.get("triggers", ()) if isinstance(item, dict) and str(item.get("source", "")).startswith(f"{resource}.")
        }
        if trigger_channels and not trigger_channels <= sync_sources:
            issues.append(SequenceIssueViewModel("error", "sequence_trigger_channel_mismatch", f"Sequence trigger channels {sorted(trigger_channels)} do not match sync sources {sorted(sync_sources)}."))
        if trigger_channels and trigger_channels <= sync_sources:
            issues.append(SequenceIssueViewModel("warning", "sequence_physical_route_unverified", "Trigger route is logically consistent; physical cable verification is still required."))
        acquisition_s = _known_acquisition_duration(self.config)
        readout_s = options.get("readout_window_s")
        if acquisition_s is not None and isinstance(readout_s, (int, float)) and acquisition_s > float(readout_s) + 1e-15:
            issues.append(SequenceIssueViewModel("error", "sequence_acquisition_window_mismatch", f"Known acquisition window {acquisition_s:g}s exceeds readout window {float(readout_s):g}s."))
        return issues

    def insert_or_update_macro(self, plan_id: str, parent: tuple[str | int, ...] = ("procedure",), index: int | None = None) -> tuple[str | int, ...]:
        entry = _canonical_sequence_sweep_entry(self.config, plan_id, str(self._raw(plan_id).get("resource")))
        for path, step in _walk(self.config.get("procedure", []), ("procedure",)):
            if isinstance(step.get("sequence_sweep"), dict) and step["sequence_sweep"].get("plan") == plan_id:
                step.clear(); step.update(entry); self.sweep._edited(plan_id); return path
        target: Any = self.config
        for part in parent: target = target[part]
        insertion = len(target) if index is None else index; target.insert(insertion, entry)
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

def _find_macro(config: dict[str, Any], plan_id: str) -> dict[str, Any] | None:
    for _, step in _walk(config.get("procedure", []), ("procedure",)):
        value = step.get("sequence_sweep")
        if isinstance(value, dict) and value.get("plan") == plan_id: return value
    return None

def _walk_steps_in_macro(macro: dict[str, Any]):
    yield from _walk(macro.get("body", []), ("procedure",))

def _normalize_channel(value: str) -> str:
    text = value.strip().lower().replace("channel", "ch").replace(" ", "")
    return text

def _known_acquisition_duration(config: dict[str, Any]) -> float | None:
    for _, step in _walk([*config.get("setup", []), *config.get("procedure", [])], ("workflow",)):
        if not str(step.get("call", "")).endswith(("configure_counter", "configure_ai", "configure_ai_external_trigger")): continue
        args = step.get("args", {}) if isinstance(step.get("args"), dict) else {}
        rate, samples = args.get("sample_rate"), args.get("samples")
        if isinstance(rate, (int, float)) and rate > 0 and isinstance(samples, int) and samples > 0: return samples / rate
    return None

def _acquisition_resource(config: dict[str, Any], *, exclude: str) -> str | None:
    resources = config.get("resources", {}) if isinstance(config.get("resources"), dict) else {}
    for name, raw in resources.items():
        if name == exclude or not isinstance(raw, dict): continue
        adapter = str(raw.get("adapter") or raw.get("adaptor") or "")
        actions = ACTION_REGISTRY.list_actions(adapter)
        if any(item.phase == "read" and item.returns is not None for item in actions) and any(item.method == "arm" for item in actions):
            return str(name)
    return None

def _canonical_sequence_sweep_entry(config: dict[str, Any], plan_id: str, resource: str) -> dict[str, Any]:
    body: list[dict[str, Any]] = [{"call": f"{resource}.compile_sequence"}]
    run_steps: list[dict[str, Any]] = []
    acquisition = _acquisition_resource(config, exclude=resource)
    if acquisition is not None: run_steps.append({"call": f"{acquisition}.arm"})
    run_steps.extend(({"call": f"{resource}.arm"}, {"call": f"{resource}.start"}))
    if acquisition is not None:
        adapter = str(config.get("resources", {}).get(acquisition, {}).get("adapter") or "")
        read = next((item.method for item in ACTION_REGISTRY.list_actions(adapter)
                     if item.phase == "read" and item.returns is not None), "read_counts")
        run_steps.append({"call": f"{acquisition}.{read}", "save_as": "counts"})
    body.append({"run": {"name": f"{plan_id}_run", "timeout_s": 10.0, "steps": run_steps}})
    return {"sequence_sweep": {"plan": plan_id, "body": [{"measurement": {"name": f"{plan_id}_point", "body": body}}]}}

def _normalize_preview(preview: Any) -> NormalizedPreview:
    pulses: list[NormalizedPulse] = []
    for channel in getattr(preview, "channels", ()):
        name = str(getattr(channel, "name", "channel"))
        for index, pulse in enumerate(getattr(channel, "pulses", ())):
            pulses.append(NormalizedPulse(name, index, float(pulse.start_s), float(pulse.end_s),
                                          getattr(pulse, "label", None), getattr(pulse, "alias", None)))
    channels = tuple(dict.fromkeys(item.channel for item in pulses))
    return NormalizedPreview(tuple(pulses), channels, float(getattr(preview, "total_duration_s", 0.0)))

def _locate_issue(issue: SequenceIssueViewModel) -> LocatedSequenceIssue:
    code = issue.code
    if "target" in code or "fingerprint" in code: step, field = "targets_propagation", "target"
    elif "constraint" in code or "overlap" in code: step, field = "targets_propagation", "constraint"
    elif "trigger" in code or "acquisition" in code or "route" in code: step, field = "channel_roles", "trigger"
    elif "parameter" in code or "sampling" in code or "point" in code: step, field = "sweep_parameters", "parameter"
    elif "template" in code or "provider" in code: step, field = "source", "source"
    elif "workflow" in code or "macro" in code: step, field = "validation_prepare", "workflow"
    else: step, field = "validation_prepare", None
    return LocatedSequenceIssue(issue.severity, code, issue.message, step, field)
