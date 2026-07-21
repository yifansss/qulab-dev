"""Setup profile helpers."""

from __future__ import annotations

from typing import Any

from qulab.core import ExperimentContext

from .registry import InstrumentRegistry


def build_context_from_resources(
    resources_config: dict[str, dict[str, Any]],
    registry: InstrumentRegistry | None = None,
) -> ExperimentContext:
    registry = registry or InstrumentRegistry()
    context = ExperimentContext()
    for name, config in resources_config.items():
        resource = registry.create(name, config)
        if config.get("connect_on_load", False):
            resource.connect()
        context.resources[name] = resource
    return context
