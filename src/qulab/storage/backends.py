"""Shared backend selection utilities."""

from __future__ import annotations

from typing import Any


ADVANCED_BACKENDS = {"csv", "zarr"}


def normalize_storage_backends(
    config: dict[str, Any] | None = None,
    resolved_config: dict[str, Any] | None = None,
    explicit_backends: list[str] | tuple[str, ...] | str | None = None,
) -> list[str]:
    """Return selected advanced backends in stable order."""

    selected: list[str] = ["csv"]
    if explicit_backends is not None:
        selected = _coerce_backends(explicit_backends)
    else:
        for source in (resolved_config, config):
            storage = source.get("storage", {}) if isinstance(source, dict) else {}
            if not isinstance(storage, dict):
                continue
            if "backends" in storage:
                selected = _coerce_backends(storage["backends"])
                break
            if "backend" in storage:
                selected = _coerce_backends(storage["backend"])
                break
    normalized = [backend for backend in selected if backend in ADVANCED_BACKENDS]
    if "zarr" in normalized and "csv" not in normalized:
        normalized.insert(0, "csv")
    if not normalized:
        normalized = ["csv"]
    return normalized


def _coerce_backends(value: list[str] | tuple[str, ...] | str) -> list[str]:
    if isinstance(value, str):
        values = [value]
    else:
        values = list(value)
    normalized: list[str] = []
    for item in values:
        backend = str(item).lower()
        if backend == "jsonl":
            continue
        if backend not in normalized:
            normalized.append(backend)
    return normalized
