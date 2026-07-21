"""Parameter reference parsing for experiment configs."""

from __future__ import annotations

import re
from typing import Any

from qulab.core import P
from qulab.core.parameter import ParameterRef

from .errors import ConfigLoadError

_REF_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def resolve_parameter_refs(value: Any) -> Any:
    """Recursively convert complete ``${param}`` strings into ``P("param")``."""

    if isinstance(value, str):
        match = _REF_RE.match(value)
        if match:
            return P(match.group(1))
        if value.startswith("${") and value.endswith("}"):
            raise ConfigLoadError(f"Unsupported parameter reference syntax: {value}")
        return value
    if isinstance(value, list):
        return [resolve_parameter_refs(item) for item in value]
    if isinstance(value, tuple):
        return tuple(resolve_parameter_refs(item) for item in value)
    if isinstance(value, dict):
        return {key: resolve_parameter_refs(item) for key, item in value.items()}
    return value


def parameter_refs_to_strings(value: Any) -> Any:
    """Recursively convert ParameterRef values back to YAML-safe strings."""

    if isinstance(value, ParameterRef):
        return f"${{{value.name}}}"
    if isinstance(value, list):
        return [parameter_refs_to_strings(item) for item in value]
    if isinstance(value, tuple):
        return [parameter_refs_to_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: parameter_refs_to_strings(item) for key, item in value.items()}
    return value
