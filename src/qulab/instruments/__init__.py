"""Instrument capability and adapter registry."""

from .base import (
    InstrumentAdapter,
    InstrumentConfigurationError,
    InstrumentConnectionError,
    InstrumentError,
    InstrumentSafetyError,
    InstrumentTimeoutError,
    InstrumentUnsupportedOperation,
)
from .profiles import build_context_from_resources
from .registry import InstrumentRegistry
from .action_specs import (
    MISSING, ActionSpec, ActionSpecRegistry, AdapterSpec, ArgumentSpec, CapabilitySpec,
    DataFieldSpec, ReturnSpec, DEFAULT_ACTION_REGISTRY, render_action_catalog_markdown,
    validate_action_call,
)

__all__ = [
    "InstrumentAdapter",
    "InstrumentConfigurationError",
    "InstrumentConnectionError",
    "InstrumentError",
    "InstrumentRegistry",
    "InstrumentSafetyError",
    "InstrumentTimeoutError",
    "InstrumentUnsupportedOperation",
    "MISSING",
    "ActionSpec",
    "ActionSpecRegistry",
    "AdapterSpec",
    "ArgumentSpec",
    "CapabilitySpec",
    "DataFieldSpec",
    "ReturnSpec",
    "DEFAULT_ACTION_REGISTRY",
    "render_action_catalog_markdown",
    "validate_action_call",
    "build_context_from_resources",
]
