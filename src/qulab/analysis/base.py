"""Compute module protocol and the function shortcut adapter."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from .models import ComputePoint, ComputeResult


@runtime_checkable
class ComputeModule(Protocol):
    name: str
    version: str
    input_keys: tuple[str, ...]
    output_keys: tuple[str, ...]

    def setup(self, config: Mapping[str, Any], run_context: Mapping[str, Any]) -> None: ...
    def process_point(self, point: ComputePoint) -> ComputeResult | Mapping[str, Any] | None: ...
    def close(self) -> None: ...


class FunctionComputeAdapter:
    """Expose a ``compute(point, **args)`` function through the class protocol."""

    def __init__(self, function: Callable[..., Any], *, name: str, version: str,
                 input_keys: tuple[str, ...], output_keys: tuple[str, ...]) -> None:
        self.function = function
        self.name = name
        self.version = version
        self.input_keys = input_keys
        self.output_keys = output_keys
        self._args: dict[str, Any] = {}

    def setup(self, config: Mapping[str, Any], run_context: Mapping[str, Any]) -> None:
        self._args = dict(config)

    def process_point(self, point: ComputePoint) -> Any:
        return self.function(point, **self._args)

    def close(self) -> None:
        self._args = {}
