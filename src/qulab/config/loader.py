"""YAML loading helpers for experiment configs."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from qulab.paths import resolve_project_path

from .errors import ConfigLoadError

_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def _convert_numeric_strings(value: Any) -> Any:
    if isinstance(value, str) and _NUMERIC_RE.match(value.strip()):
        text = value.strip()
        if any(ch in text for ch in ".eE"):
            return float(text)
        return int(text)
    if isinstance(value, list):
        return [_convert_numeric_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: _convert_numeric_strings(item) for key, item in value.items()}
    return value


def _ensure_config_dict(data: Any, source: str) -> dict[str, Any]:
    if data is None:
        raise ConfigLoadError(f"Empty experiment config: {source}")
    if not isinstance(data, dict):
        raise ConfigLoadError(f"Experiment config top level must be a mapping: {source}")
    return _convert_numeric_strings(data)


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config file with ``yaml.safe_load``."""

    config_path = resolve_project_path(path) or Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return _ensure_config_dict(data, str(config_path))


def load_experiment_config(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Load an experiment config from a path, YAML string, or mapping."""

    if isinstance(source, dict):
        return _ensure_config_dict(deepcopy(source), "dict")
    if isinstance(source, Path):
        return load_yaml_config(source)
    if isinstance(source, str):
        possible_path = resolve_project_path(source, must_exist=True)
        if "\n" not in source and possible_path is not None:
            return load_yaml_config(possible_path)
        return _ensure_config_dict(yaml.safe_load(source), "string")
    raise ConfigLoadError(f"Unsupported config source type: {type(source).__name__}")
