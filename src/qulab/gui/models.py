"""View models and config-edit helpers for the operator console."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


PathPart = str | int


@dataclass(frozen=True)
class ParameterEdit:
    """A commonly edited experiment parameter exposed by the GUI."""

    id: str
    label: str
    value: Any
    value_type: str
    path: tuple[PathPart, ...]


@dataclass(frozen=True)
class ResourceViewModel:
    name: str
    adapter: str
    capabilities: tuple[str, ...] = ()
    connect_on_load: bool = False
    connected: bool = False
    simulation: bool = True
    health: dict[str, Any] = field(default_factory=dict)
    snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreflightIssueViewModel:
    severity: str
    code: str
    message: str
    location: str = ""
    hint: str = ""
    workflow_path: tuple[PathPart, ...] | None = None


@dataclass(frozen=True)
class SequenceSnapshotViewModel:
    resource: str
    sequence_file: str
    exists: bool
    reference_id: str = ""
    label: str = ""
    source: str = ""
    mtime: float | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    parameters: tuple[str, ...] = ()
    channels: tuple[str, ...] = ()
    preview_lines: tuple[str, ...] = ()
    sequence_params: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreflightViewModel:
    ok: bool
    resources: tuple[ResourceViewModel, ...] = ()
    issues: tuple[PreflightIssueViewModel, ...] = ()
    sequence_snapshots: tuple[SequenceSnapshotViewModel, ...] = ()


@dataclass(frozen=True)
class RunViewModel:
    run_path: str
    status: str
    event_count: int


def extract_parameter_edits(config: dict[str, Any]) -> list[ParameterEdit]:
    """Find scan and average controls that are safe for operator editing."""

    edits: list[ParameterEdit] = []
    for section in ("procedure",):
        _collect_parameter_edits(config.get(section, []), (section,), edits)
    return edits


def update_config_value(config: dict[str, Any], path: tuple[PathPart, ...], value: Any) -> None:
    """Update a nested config value addressed by a ``ParameterEdit.path``."""

    target: Any = config
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value


def parse_parameter_value(text: str, value_type: str) -> Any:
    """Parse text entered by an operator without evaluating Python code."""

    stripped = text.strip()
    if value_type == "int":
        return int(stripped)
    if value_type == "float":
        return float(stripped)
    if value_type == "number":
        return _parse_number(stripped)
    if value_type == "list":
        if stripped == "":
            return []
        payload = stripped if stripped.startswith("[") and stripped.endswith("]") else f"[{stripped}]"
        parsed = yaml.safe_load(payload)
        if not isinstance(parsed, list):
            raise ValueError("List parameter must be a YAML/JSON list or comma-separated values")
        return [_parse_number_or_string(item) if isinstance(item, str) else item for item in parsed]
    return stripped


def format_parameter_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _collect_parameter_edits(raw_steps: Any, path: tuple[PathPart, ...], edits: list[ParameterEdit]) -> None:
    if not isinstance(raw_steps, list):
        return
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            continue
        step_path = (*path, index)
        if "scan" in raw_step and isinstance(raw_step["scan"], dict):
            scan = raw_step["scan"]
            name = str(scan.get("name") or "scan")
            values = scan.get("values")
            values_path = (*step_path, "scan", "values")
            if isinstance(values, dict):
                for key in ("start", "stop", "points", "step"):
                    if key in values:
                        value = values[key]
                        value_type = "int" if key == "points" else "number"
                        edits.append(
                            ParameterEdit(
                                id=_path_id((*values_path, key)),
                                label=f"{name} {key}",
                                value=value,
                                value_type=value_type,
                                path=(*values_path, key),
                            )
                        )
            elif isinstance(values, list):
                edits.append(
                    ParameterEdit(
                        id=_path_id(values_path),
                        label=f"{name} values",
                        value=values,
                        value_type="list",
                        path=values_path,
                    )
                )
            _collect_parameter_edits(scan.get("body", []), (*step_path, "scan", "body"), edits)
        elif "average" in raw_step and isinstance(raw_step["average"], dict):
            average = raw_step["average"]
            name = str(average.get("name") or "average")
            if "count" in average:
                count_path = (*step_path, "average", "count")
                edits.append(
                    ParameterEdit(
                        id=_path_id(count_path),
                        label=f"{name} count",
                        value=average["count"],
                        value_type="int",
                        path=count_path,
                    )
                )
            _collect_parameter_edits(average.get("body", []), (*step_path, "average", "body"), edits)
        elif "measurement" in raw_step and isinstance(raw_step["measurement"], dict):
            _collect_parameter_edits(
                raw_step["measurement"].get("body", []), (*step_path, "measurement", "body"), edits
            )
        elif "run" in raw_step and isinstance(raw_step["run"], dict):
            run = raw_step["run"]
            _collect_parameter_edits(run.get("steps", run.get("body", [])), (*step_path, "run", "steps"), edits)
        elif "cleanup" in raw_step and isinstance(raw_step["cleanup"], dict):
            cleanup = raw_step["cleanup"]
            _collect_parameter_edits(
                cleanup.get("steps", cleanup.get("body", [])), (*step_path, "cleanup", "steps"), edits
            )


def _path_id(path: tuple[PathPart, ...]) -> str:
    return "/".join(str(part) for part in path)


def _parse_number(text: str) -> int | float:
    value = float(text)
    if value.is_integer() and "e" not in text.lower() and "." not in text:
        return int(value)
    return value


def _parse_number_or_string(text: str) -> Any:
    try:
        return _parse_number(text)
    except ValueError:
        return text
