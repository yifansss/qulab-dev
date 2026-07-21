"""Parameter and scan value primitives for hardware-free procedures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

import numpy as np


@dataclass
class Parameter:
    """A named experiment parameter with optional unit and metadata."""

    name: str
    value: Any = None
    unit: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParameterRef:
    """Deferred reference to a parameter value in an ExperimentContext."""

    name: str

    def resolve(self, context: Any) -> Any:
        return context.get_parameter_value(self.name)


def P(name: str) -> ParameterRef:
    """Create a deferred parameter reference."""

    return ParameterRef(name)


@dataclass(frozen=True)
class ScanValues:
    """Concrete scan values generated from explicit, linspace, or range specs."""

    values: tuple[Any, ...]

    def __iter__(self) -> Iterator[Any]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, index: int) -> Any:
        return self.values[index]

    @classmethod
    def explicit(cls, values: Iterable[Any]) -> "ScanValues":
        return cls(tuple(values))

    @classmethod
    def linspace(cls, start: float, stop: float, points: int) -> "ScanValues":
        if points <= 0:
            raise ValueError("linspace points must be positive")
        return cls(tuple(float(v) for v in np.linspace(start, stop, points)))

    @classmethod
    def range(cls, start: float, stop: float, step: float) -> "ScanValues":
        if step == 0:
            raise ValueError("range step must be non-zero")
        if (stop - start) * step < 0:
            raise ValueError("range step moves away from stop")

        values: list[float] = []
        current = float(start)
        epsilon = abs(step) * 1e-12
        if step > 0:
            while current <= stop + epsilon:
                values.append(current)
                current += step
        else:
            while current >= stop - epsilon:
                values.append(current)
                current += step
        return cls(tuple(values))
