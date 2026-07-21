"""Qt-free authoring model for Sequence Sweep controls."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from qulab.sequence_generation import SequenceGenerationError
from qulab.sequence_generation.preparation import parse_sequence_plans
from qulab.sequence_generation.registry import DEFAULT_PROVIDER_REGISTRY, SequenceProviderRegistry
from qulab.sequence_generation.sampling import enumerate_plan_points, normalize_parameter_values


@dataclass(frozen=True)
class SequenceIssueViewModel:
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class SequenceParameterRow:
    name: str
    label: str
    mode: str
    unit: str | None
    sweepable: bool
    values: Mapping[str, Any]


@dataclass(frozen=True)
class SequenceTargetRow:
    alias: str
    channel: str
    pulse: int
    fingerprint: str | None


@dataclass(frozen=True)
class SequenceConstraintRow:
    type: str
    target: str
    reference: str
    offset_s: float


@dataclass(frozen=True)
class SequencePlanViewModel:
    id: str
    resource: str
    provider: str
    provider_version: str | None
    template: str | None
    parameters: tuple[SequenceParameterRow, ...]
    targets: tuple[SequenceTargetRow, ...]
    constraints: tuple[SequenceConstraintRow, ...]
    point_count: int
    plan_hash: str | None
    state: str
    issues: tuple[SequenceIssueViewModel, ...] = ()


@dataclass(frozen=True)
class PlanEstimate:
    point_count: int
    axes: tuple[str, ...]
    first: Mapping[str, Any]
    last: Mapping[str, Any]


class SequenceSweepEditorModel:
    def __init__(self, config: dict[str, Any], registry: SequenceProviderRegistry | None = None) -> None:
        self.config = config
        self.registry = registry or DEFAULT_PROVIDER_REGISTRY
        self.states: dict[str, str] = {}
        self.plan_hashes: dict[str, str] = {}

    @classmethod
    def load(cls, config: dict[str, Any], registry: SequenceProviderRegistry | None = None) -> "SequenceSweepEditorModel":
        return cls(config, registry)

    def list_plans(self) -> list[SequencePlanViewModel]:
        raw_plans = self.config.get("sequence_plans", {})
        if not isinstance(raw_plans, dict):
            return []
        output = []
        for plan_id in raw_plans:
            try:
                plan = parse_sequence_plans(self.config)[plan_id]
                provider, _ = self.registry.load(plan.provider, plan.provider_version)
                spec = provider.describe(); values = normalize_parameter_values(plan, spec)
                points = enumerate_plan_points(plan, values)
                specs = {item.name: item for item in spec.parameters}
                rows = tuple(SequenceParameterRow(name, specs[name].label if name in specs else name,
                                                   value.mode, specs[name].unit if name in specs else value.unit,
                                                   specs[name].sweepable if name in specs else True, value.to_dict())
                             for name, value in plan.parameters.items())
                targets = tuple(SequenceTargetRow(str(alias), str(raw.get("channel", "")), int(raw.get("pulse", 0)), raw.get("fingerprint"))
                                for alias, raw in plan.targets.items() if isinstance(raw, Mapping))
                constraints = tuple(SequenceConstraintRow(str(raw.get("type", "")), str(raw.get("target", "")),
                                                            str(raw.get("reference", "")), float(raw.get("offset_s", 0.0)))
                                    for raw in plan.constraints)
                output.append(SequencePlanViewModel(plan_id, plan.resource, plan.provider, plan.provider_version,
                                                     str(plan.template) if plan.template else None, rows, targets, constraints,
                                                     len(points), self.plan_hashes.get(plan_id), self.states.get(plan_id, "valid")))
            except Exception as exc:
                code = getattr(exc, "code", "sequence_plan_invalid")
                raw = raw_plans.get(plan_id, {}) if isinstance(raw_plans.get(plan_id), dict) else {}
                family = raw.get("family", {}) if isinstance(raw.get("family"), dict) else {}
                output.append(SequencePlanViewModel(str(plan_id), str(raw.get("resource", "")), str(family.get("provider", "")),
                                                     family.get("version"), raw.get("template"), (), (), (), 0, None, "error",
                                                     (SequenceIssueViewModel("error", code, str(exc)),)))
        return output

    def create_plan(self, plan_id: str, resource: str, provider: str, template: str | None = None) -> None:
        plans = self.config.setdefault("sequence_plans", {})
        if plan_id in plans:
            raise ValueError(f"Sequence plan '{plan_id}' already exists")
        loaded, _ = self.registry.load(provider)
        spec = loaded.describe()
        parameters = {item.name: {"mode": "fixed", "value": item.default, **({"unit": item.unit} if item.unit else {})}
                      for item in spec.parameters}
        plan = {"resource": resource, "family": {"provider": provider, "version": spec.version},
                "parameters": parameters, "sampling": {"mode": "cartesian", "order": []},
                "materialize": {"cache": True, "max_points": 10000}}
        if template is not None: plan["template"] = template
        plans[plan_id] = plan; self._edited(plan_id)

    def duplicate_plan(self, plan_id: str, new_plan_id: str) -> None:
        plans = self.config.setdefault("sequence_plans", {})
        if plan_id not in plans or new_plan_id in plans: raise KeyError(plan_id)
        plans[new_plan_id] = deepcopy(plans[plan_id]); self._edited(new_plan_id)

    def remove_plan(self, plan_id: str) -> None:
        self.config.get("sequence_plans", {}).pop(plan_id)
        self.states.pop(plan_id, None); self.plan_hashes.pop(plan_id, None)

    def update_parameter(self, plan_id: str, name: str, patch: Mapping[str, Any]) -> None:
        parameters = self._raw(plan_id).setdefault("parameters", {})
        current = dict(parameters.get(name, {})); current.update(deepcopy(dict(patch)))
        mode = current.get("mode", "fixed")
        allowed = {"fixed": {"mode", "value", "unit", "expose_as", "transform"},
                   "linspace": {"mode", "start", "stop", "points", "unit", "expose_as", "transform"},
                   "range": {"mode", "start", "stop", "step", "unit", "expose_as", "transform"},
                   "explicit": {"mode", "values", "unit", "expose_as", "transform"}}
        if mode not in allowed: raise ValueError(f"Unsupported parameter mode: {mode}")
        parameters[name] = {key: value for key, value in current.items() if key in allowed[mode]}
        order = self._raw(plan_id).setdefault("sampling", {}).setdefault("order", [])
        if mode == "fixed" and name in order: order.remove(name)
        if mode != "fixed" and name not in order: order.append(name)
        self._edited(plan_id)

    def update_target(self, plan_id: str, alias: str, patch: Mapping[str, Any]) -> None:
        self._raw(plan_id).setdefault("targets", {}).setdefault(alias, {}).update(deepcopy(dict(patch))); self._edited(plan_id)

    def update_constraints(self, plan_id: str, constraints: list[Mapping[str, Any]]) -> None:
        self._raw(plan_id)["constraints"] = deepcopy(constraints); self._edited(plan_id)

    def set_sampling_order(self, plan_id: str, order: list[str]) -> None:
        self._raw(plan_id).setdefault("sampling", {})["order"] = list(order); self._edited(plan_id)

    def estimate(self, plan_id: str) -> PlanEstimate:
        plan = parse_sequence_plans(self.config)[plan_id]; provider, _ = self.registry.load(plan.provider, plan.provider_version)
        values = normalize_parameter_values(plan, provider.describe()); points = enumerate_plan_points(plan, values)
        return PlanEstimate(len(points), plan.sampling_order, points[0].coordinates if points else {}, points[-1].coordinates if points else {})

    def mark_prepared(self, plan_id: str, plan_hash: str) -> None:
        self.states[plan_id] = "prepared"; self.plan_hashes[plan_id] = plan_hash

    def to_config_patch(self) -> dict[str, Any]:
        return {"sequence_plans": deepcopy(self.config.get("sequence_plans", {}))}

    def _raw(self, plan_id: str) -> dict[str, Any]:
        plan = self.config.get("sequence_plans", {}).get(plan_id)
        if not isinstance(plan, dict): raise KeyError(plan_id)
        return plan

    def _edited(self, plan_id: str) -> None:
        self.states[plan_id] = "stale" if plan_id in self.plan_hashes else "edited"
        self.plan_hashes.pop(plan_id, None)
