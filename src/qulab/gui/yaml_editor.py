"""YAML round-trip helpers for GUI-edited experiment configs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from qulab.config import load_experiment_config, parse_experiment_config


def load_config_yaml(path: str | Path) -> dict[str, Any]:
    return load_experiment_config(Path(path))


def dump_config_yaml(config: dict[str, Any]) -> str:
    return yaml.safe_dump(config, sort_keys=False)


def save_config_yaml(config: dict[str, Any], path: str | Path) -> Path:
    destination = Path(path)
    destination.write_text(dump_config_yaml(config), encoding="utf-8")
    return destination


def validate_config_yaml(config: dict[str, Any]) -> None:
    parse_experiment_config(config)
