"""YAML node-mark based source locations and duplicate-key discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from .diagnostics import ConfigPath


@dataclass(frozen=True)
class SourceLocation:
    line: int
    column: int


@dataclass(frozen=True)
class DuplicateKey:
    path: ConfigPath
    key: Any
    location: SourceLocation


def compose_source_map(text: str) -> tuple[dict[ConfigPath, SourceLocation], tuple[DuplicateKey, ...]]:
    root = yaml.compose(text, Loader=yaml.SafeLoader)
    if root is None:
        return {}, ()
    locations: dict[ConfigPath, SourceLocation] = {}
    duplicates: list[DuplicateKey] = []
    _visit(root, (), locations, duplicates)
    return locations, tuple(duplicates)


def nearest_location(source_map: dict[ConfigPath, SourceLocation], path: ConfigPath) -> SourceLocation | None:
    candidate = path
    while candidate:
        if candidate in source_map:
            return source_map[candidate]
        candidate = candidate[:-1]
    return source_map.get(())


def _visit(
    node: Node,
    path: ConfigPath,
    locations: dict[ConfigPath, SourceLocation],
    duplicates: list[DuplicateKey],
) -> None:
    locations[path] = SourceLocation(node.start_mark.line + 1, node.start_mark.column + 1)
    if isinstance(node, MappingNode):
        seen: set[Any] = set()
        for key_node, value_node in node.value:
            key = _scalar_key(key_node)
            child_path = (*path, key)
            locations[child_path] = SourceLocation(key_node.start_mark.line + 1, key_node.start_mark.column + 1)
            if key in seen:
                duplicates.append(DuplicateKey(child_path, key, locations[child_path]))
            seen.add(key)
            _visit(value_node, child_path, locations, duplicates)
    elif isinstance(node, SequenceNode):
        for index, child in enumerate(node.value):
            _visit(child, (*path, index), locations, duplicates)


def _scalar_key(node: Node) -> Any:
    if isinstance(node, ScalarNode):
        try:
            return yaml.safe_load(node.value)
        except Exception:
            return node.value
    return str(getattr(node, "value", "<complex-key>"))
