"""JSON-safe public models for declared and runtime analysis data."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


def json_safe(value: Any) -> Any:
    """Return a detached JSON-compatible representation or raise TypeError."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("mapping keys must be strings")
            result[key] = json_safe(item)
        return result
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if hasattr(value, "item"):
        return json_safe(value.item())
    raise TypeError(f"value of type {type(value).__name__} is not JSON-safe")


@dataclass(frozen=True)
class ComputeArgumentSpec:
    name: str
    value_type: str = "any"
    required: bool = False
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[Any, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class ComputePoint:
    point_id: str
    coords: Mapping[str, Any]
    data: Mapping[str, Any]
    metadata: Mapping[str, Any]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class ComputeResult:
    data: Mapping[str, Any]
    units: Mapping[str, str | None] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    quality: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class AnalysisSourceIdentity:
    import_target: str
    resolved_path: str | None
    sha256: str | None
    version: str

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class ComputeModuleSpec:
    name: str
    version: str
    input_keys: tuple[str, ...]
    output_keys: tuple[str, ...]
    argument_specs: tuple[ComputeArgumentSpec, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class ComputeModulePlan:
    instance_name: str
    import_target: str
    object_name: str
    object_kind: str
    enabled: bool
    run_live: bool
    run_post: bool
    show: bool
    save: bool
    fail_policy: str
    inputs: tuple[str, ...]
    declared_outputs: tuple[str, ...]
    effective_outputs: tuple[str, ...]
    args: Mapping[str, Any]
    source_identity: AnalysisSourceIdentity
    namespace: str | None = None
    dependencies: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class AnalysisLiveConfig:
    enabled: bool = False
    fail_policy: str = "warn"
    save_outputs: bool = True
    emit_events: bool = True
    execution: str = "sync"
    queue_size: int = 64
    backpressure: str = "skip_newest"
    drain_on_close: bool = True
    drain_timeout_s: float = 10.0
    worker_count: int = 1
    status_interval_s: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


@dataclass(frozen=True)
class AnalysisExecutionPlan:
    live: AnalysisLiveConfig
    modules: tuple[ComputeModulePlan, ...] = ()
    raw_inputs: tuple[str, ...] = ()
    derived_outputs: tuple[str, ...] = ()
    dependency_edges: tuple[tuple[str, str], ...] = ()

    @property
    def ordered_modules(self) -> tuple[ComputeModulePlan, ...]:
        return self.modules

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))
