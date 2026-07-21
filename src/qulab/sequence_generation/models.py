"""Typed public models for sequence family generation and preparation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol

from .errors import SequenceGenerationIssue


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        raise TypeError("sequence bytes are materializer-only and cannot be serialized")
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass(frozen=True)
class SourceIdentity:
    provider: str
    version: str
    source_path: str | None = None
    source_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return json_safe(self.__dict__)


@dataclass(frozen=True)
class SequenceParameterSpec:
    name: str
    label: str
    dtype: str
    unit: str | None
    default: object
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[object, ...] | None = None
    sweepable: bool = True
    role: str = "sequence_parameter"
    safety_class: str = "configure_no_output"
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return json_safe(self.__dict__)


@dataclass(frozen=True)
class SequenceFamilySpec:
    id: str
    version: str
    label: str
    output_format: str
    parameters: tuple[SequenceParameterSpec, ...]
    resource_capability: str = "pulse_sequencer"
    supports_preview: bool = False
    source_identity: SourceIdentity | None = None
    description: str | None = None
    dynamic_parameters: bool = False

    def to_dict(self) -> dict[str, Any]:
        return json_safe(self.__dict__)


@dataclass(frozen=True)
class GeneratedSequencePoint:
    sequence_bytes: bytes
    extension: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParameterValuePlan:
    mode: str
    value: Any = None
    start: Any = None
    stop: Any = None
    points: int | None = None
    step: Any = None
    values: tuple[Any, ...] = ()
    unit: str | None = None
    expose_as: str | None = None
    transform: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ParameterValuePlan":
        return cls(
            mode=str(raw.get("mode", "fixed")),
            value=raw.get("value"),
            start=raw.get("start"),
            stop=raw.get("stop"),
            points=raw.get("points"),
            step=raw.get("step"),
            values=tuple(raw.get("values", ())) if isinstance(raw.get("values", ()), (list, tuple)) else (),
            unit=raw.get("unit"),
            expose_as=raw.get("expose_as"),
            transform=dict(raw.get("transform", {})) if isinstance(raw.get("transform", {}), Mapping) else {},
        )

    @property
    def swept(self) -> bool:
        return self.mode != "fixed"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"mode": self.mode}
        for name in ("value", "start", "stop", "points", "step", "unit", "expose_as"):
            value = getattr(self, name)
            if value is not None:
                result[name] = json_safe(value)
        if self.values:
            result["values"] = list(self.values)
        if self.transform:
            result["transform"] = json_safe(self.transform)
        return result


@dataclass(frozen=True)
class MaterializePolicy:
    cache: bool = True
    max_points: int = 10_000

    def to_dict(self) -> dict[str, Any]:
        return {"cache": self.cache, "max_points": self.max_points}


@dataclass(frozen=True)
class SequenceSweepPlan:
    id: str
    resource: str
    provider: str
    provider_version: str | None
    parameters: Mapping[str, ParameterValuePlan]
    sampling_mode: str
    sampling_order: tuple[str, ...]
    template: Path | None = None
    materialize: MaterializePolicy = field(default_factory=MaterializePolicy)
    targets: Mapping[str, Any] = field(default_factory=dict)
    groups: Mapping[str, Any] = field(default_factory=dict)
    constraints: tuple[Mapping[str, Any], ...] = ()
    options: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "resource": self.resource,
            "provider": self.provider,
            "provider_version": self.provider_version,
            "parameters": {name: item.to_dict() for name, item in self.parameters.items()},
            "sampling": {"mode": self.sampling_mode, "order": list(self.sampling_order)},
            "template": None if self.template is None else str(self.template),
            "materialize": self.materialize.to_dict(),
            "targets": json_safe(self.targets),
            "groups": json_safe(self.groups),
            "constraints": json_safe(self.constraints),
            "options": json_safe(self.options),
        }
        return result


@dataclass(frozen=True)
class PlanPoint:
    index: int
    parameters: Mapping[str, Any]
    coordinates: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "parameters": json_safe(self.parameters), "coordinates": json_safe(self.coordinates)}


@dataclass(frozen=True)
class SequencePlanValidationResult:
    issues: tuple[SequenceGenerationIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


class SequenceGeneratorProvider(Protocol):
    def describe(self) -> SequenceFamilySpec: ...

    def validate_plan(self, plan: SequenceSweepPlan) -> SequencePlanValidationResult: ...

    def generate_point(
        self, parameters: Mapping[str, Any], *, template: Path | None
    ) -> GeneratedSequencePoint: ...

    def preview_point(self, parameters: Mapping[str, Any], *, template: Path | None) -> Any: ...


@dataclass(frozen=True)
class MaterializedSequenceBundle:
    plan: SequenceSweepPlan
    family_spec: SequenceFamilySpec
    bundle_id: str
    manifest_path: Path
    manifest_sha256: str
    plan_hash: str
    point_count: int
    cache_hit: bool
    normalized_values: Mapping[str, tuple[Any, ...]]
    source_identity: SourceIdentity
    template_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "family_spec": self.family_spec.to_dict(),
            "bundle_id": self.bundle_id,
            "manifest_path": str(self.manifest_path),
            "manifest_sha256": self.manifest_sha256,
            "plan_hash": self.plan_hash,
            "point_count": self.point_count,
            "cache_hit": self.cache_hit,
            "normalized_values": json_safe(self.normalized_values),
            "source_identity": self.source_identity.to_dict(),
            "template_sha256": self.template_sha256,
        }


@dataclass(frozen=True)
class SequenceGenerationRecord:
    plan_id: str
    plan_hash: str
    provider: str
    provider_version: str
    provider_source_hash: str | None
    template_sha256: str | None
    bundle_id: str
    manifest_path: str
    manifest_sha256: str
    point_count: int
    cache_hit: bool
    status: str = "generated"

    def to_dict(self) -> dict[str, Any]:
        return json_safe(self.__dict__)


@dataclass
class SequencePreparationResult:
    authoring_config: dict[str, Any]
    compiled_config: dict[str, Any]
    plans: dict[str, SequenceSweepPlan] = field(default_factory=dict)
    materialized: dict[str, MaterializedSequenceBundle] = field(default_factory=dict)
    generation_records: tuple[SequenceGenerationRecord, ...] = ()
    experiment_parameters: dict[str, dict[str, Any]] = field(default_factory=dict)
    issues: tuple[SequenceGenerationIssue, ...] = ()
    cache_root: Path | None = None

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "authoring_config": json_safe(self.authoring_config),
            "compiled_config": json_safe(self.compiled_config),
            "plans": {key: value.to_dict() for key, value in self.plans.items()},
            "materialized": {key: value.to_dict() for key, value in self.materialized.items()},
            "generation_records": [record.to_dict() for record in self.generation_records],
            "experiment_parameters": json_safe(self.experiment_parameters),
            "issues": [issue.to_dict() for issue in self.issues],
            "cache_root": None if self.cache_root is None else str(self.cache_root),
        }
