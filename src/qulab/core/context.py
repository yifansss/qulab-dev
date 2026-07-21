"""Execution context for dry-run and mock-resource procedures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qulab.sequence_bundles import SequenceBundle

from .parameter import Parameter, ParameterRef


@dataclass
class ExperimentContext:
    parameters: dict[str, Parameter] = field(default_factory=dict)
    coords: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)
    sequence_bundles: dict[str, "SequenceBundle"] = field(default_factory=dict)
    current_point_id: str | None = None
    _point_counter: int = 0

    def set_parameter(self, name: str, value: Any, unit: str | None = None) -> None:
        if name in self.parameters:
            self.parameters[name].value = value
            if unit is not None:
                self.parameters[name].unit = unit
        else:
            self.parameters[name] = Parameter(name=name, value=value, unit=unit)

    def get_parameter_value(self, name: str) -> Any:
        if name not in self.parameters:
            raise KeyError(f"Unknown parameter reference: {name}")
        return self.parameters[name].value

    def resolve(self, value: Any) -> Any:
        if isinstance(value, ParameterRef):
            return value.resolve(self)
        if isinstance(value, dict):
            return {key: self.resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.resolve(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.resolve(item) for item in value)
        return value

    def next_point_id(self) -> str:
        self._point_counter += 1
        return f"p{self._point_counter:06d}"

    def snapshot_coords(self) -> dict[str, Any]:
        return dict(self.coords)
