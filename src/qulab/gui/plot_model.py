"""Event-to-plot reducers for the operator console."""

from __future__ import annotations

from dataclasses import dataclass, field
from numbers import Real
from typing import Any

from qulab.core import DataPoint, Event


@dataclass
class PlotSeries:
    """Reduce ``DataPoint`` events to a simple line series."""

    _points: list[tuple[float, float]] = field(default_factory=list)
    _fallback_index: int = 0

    def handle_event(self, event: Event) -> None:
        if not isinstance(event, DataPoint):
            return
        y = _find_numeric_scalar(event.data, preferred_names=("counts_mean", "mean", "counts"))
        if y is None:
            return
        x = _first_numeric_value(event.coords)
        if x is None:
            x = float(self._fallback_index)
        self._fallback_index += 1
        self._points.append((float(x), float(y)))

    @property
    def points(self) -> list[tuple[float, float]]:
        return list(self._points)

    def clear(self) -> None:
        self._points.clear()
        self._fallback_index = 0


def _first_numeric_value(mapping: dict[str, Any]) -> float | None:
    for value in mapping.values():
        if _is_number(value):
            return float(value)
    return None


def _find_numeric_scalar(value: Any, preferred_names: tuple[str, ...] = ()) -> float | None:
    if _is_number(value):
        return float(value)
    if isinstance(value, dict):
        for name in preferred_names:
            if name in value:
                found = _find_numeric_scalar(value[name], preferred_names)
                if found is not None:
                    return found
        for item in value.values():
            found = _find_numeric_scalar(item, preferred_names)
            if found is not None:
                return found
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)
