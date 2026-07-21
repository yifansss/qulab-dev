"""Editable workflow tree model backed by experiment YAML mappings."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


PathPart = str | int
Path = tuple[PathPart, ...]


@dataclass
class WorkflowNode:
    id: str
    kind: str
    label: str
    path: Path
    enabled: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    children: list["WorkflowNode"] = field(default_factory=list)


@dataclass
class WorkflowDocument:
    """Mutable workflow/config document shared by GUI submodes."""

    config: dict[str, Any]

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "WorkflowDocument":
        return cls(config)

    def tree(self) -> WorkflowNode:
        return build_workflow_tree(self.config)

    def update_node(self, path: Path, patch: dict[str, Any]) -> None:
        self.config = update_node(self.config, path, patch)

    def add_step(self, parent_path: Path, step: dict[str, Any]) -> None:
        self.config = add_step(self.config, parent_path, step)

    def delete_step(self, path: Path) -> None:
        self.config = delete_step(self.config, path)


def build_workflow_tree(config: dict[str, Any]) -> WorkflowNode:
    """Build an editable tree model with setup/procedure/cleanup roots."""

    root = WorkflowNode("root", "root", str(config.get("name") or "experiment"), ())
    for section in ("setup", "procedure", "cleanup"):
        section_node = WorkflowNode(section, section, section, (section,), True)
        for index, step in enumerate(_step_list(config, (section,))):
            section_node.children.append(_step_to_node(step, (section, index)))
        root.children.append(section_node)
    return root


def get_node(config: dict[str, Any], path: Path) -> Any:
    target: Any = config
    for part in path:
        target = target[part]
    return target


def update_node(config: dict[str, Any], path: Path, patch: dict[str, Any]) -> dict[str, Any]:
    """Return a new config with a step/list node patched."""

    updated = deepcopy(config)
    target = get_node(updated, path)
    if not isinstance(target, dict):
        raise TypeError(f"Workflow path does not point to a mapping: {path}")
    _deep_update(target, deepcopy(patch))
    return updated


def add_step(config: dict[str, Any], parent_path: Path, step: dict[str, Any]) -> dict[str, Any]:
    """Return a new config with ``step`` appended to a section or body list."""

    updated = deepcopy(config)
    steps = _step_list(updated, parent_path)
    steps.append(deepcopy(step))
    return updated


def delete_step(config: dict[str, Any], path: Path) -> dict[str, Any]:
    """Return a new config with the step at ``path`` removed."""

    updated = deepcopy(config)
    parent_path, index = _parent_list_path(path)
    steps = _step_list(updated, parent_path)
    del steps[index]
    return updated


def duplicate_step(config: dict[str, Any], path: Path) -> dict[str, Any]:
    """Return a new config with the step at ``path`` duplicated after itself."""

    updated = deepcopy(config)
    parent_path, index = _parent_list_path(path)
    steps = _step_list(updated, parent_path)
    steps.insert(index + 1, deepcopy(steps[index]))
    return updated


def make_default_step(kind: str) -> dict[str, Any]:
    if kind == "scan":
        return {"scan": {"name": "new_scan", "values": {"start": 0.0, "stop": 1.0, "points": 2}, "body": []}}
    if kind == "average":
        return {"average": {"name": "avg", "count": 1, "body": []}}
    if kind == "call":
        return {"call": "resource.method", "args": {}}
    raise ValueError(f"Unsupported default step kind: {kind}")


def set_step_enabled(config: dict[str, Any], path: Path, enabled: bool) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if enabled:
        patch["enabled"] = True
    else:
        patch["enabled"] = False
    return update_node(config, path, patch)


def _step_to_node(step: dict[str, Any], path: Path) -> WorkflowNode:
    kind = _step_kind(step)
    enabled = bool(step.get("enabled", True))
    payload = step.get(kind) if kind in step else None
    data = deepcopy(payload) if isinstance(payload, dict) else {}
    if kind == "call":
        label = str(step.get("call") or "call")
        data = {"call": step.get("call"), "args": deepcopy(step.get("args", {})), "save_as": step.get("save_as")}
    elif kind == "scan":
        label = f"scan {data.get('name', 'scan')}"
    elif kind == "average":
        label = f"average {data.get('name', 'avg')}"
    elif kind == "measurement":
        label = f"measurement {data.get('name', 'measurement')}"
    elif kind == "run":
        label = f"run {data.get('name', 'run')}"
    elif kind == "cleanup":
        label = f"cleanup {data.get('name', 'cleanup')}"
    else:
        label = "unsupported"

    children: list[WorkflowNode] = []
    child_path = _child_list_path(step, path, kind)
    if child_path is not None:
        for index, child in enumerate(_step_list_from_step(step, kind)):
            children.append(_step_to_node(child, (*child_path, index)))
    return WorkflowNode(_path_id(path), kind, label, path, enabled, data, children)


def _step_kind(step: dict[str, Any]) -> str:
    for kind in ("call", "scan", "average", "measurement", "run", "cleanup"):
        if kind in step:
            return kind
    return "unknown"


def _child_list_path(step: dict[str, Any], path: Path, kind: str) -> Path | None:
    if kind in {"scan", "average", "measurement"}:
        return (*path, kind, "body")
    if kind == "run":
        key = "steps" if "steps" in step.get("run", {}) else "body"
        return (*path, "run", key)
    if kind == "cleanup":
        key = "steps" if "steps" in step.get("cleanup", {}) else "body"
        return (*path, "cleanup", key)
    return None


def _step_list_from_step(step: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    if kind in {"scan", "average", "measurement"}:
        return step.get(kind, {}).get("body", [])
    if kind == "run":
        payload = step.get("run", {})
        return payload.get("steps", payload.get("body", []))
    if kind == "cleanup":
        payload = step.get("cleanup", {})
        return payload.get("steps", payload.get("body", []))
    return []


def _step_list(config: dict[str, Any], path: Path) -> list[Any]:
    target = get_node(config, path)
    if not isinstance(target, list):
        raise TypeError(f"Workflow path does not point to a step list: {path}")
    return target


def _parent_list_path(path: Path) -> tuple[Path, int]:
    if not path or not isinstance(path[-1], int):
        raise ValueError(f"Workflow path does not point to a step: {path}")
    return path[:-1], path[-1]


def _deep_update(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if key == "args":
            target[key] = value
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        elif value is _DELETE:
            target.pop(key, None)
        else:
            target[key] = value


def _path_id(path: Path) -> str:
    return "/".join(str(part) for part in path)


class _Delete:
    pass


_DELETE = _Delete()
