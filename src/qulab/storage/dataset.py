"""Append-only JSONL dataset writer for measurement points."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

from qulab.core import DataPoint

from .events import to_jsonable


def infer_data_spec(value: Any) -> dict[str, Any]:
    """Infer a small schema for a DataPoint value."""

    jsonable = to_jsonable(value)
    spec: dict[str, Any] = {"unit": None}
    if isinstance(jsonable, (int, float, str, bool)) or jsonable is None:
        spec["kind"] = "scalar"
        spec["shape"] = []
    elif isinstance(jsonable, list):
        if jsonable and all(isinstance(item, list) for item in jsonable):
            spec["kind"] = "matrix"
            spec["shape"] = [len(jsonable), max((len(item) for item in jsonable), default=0)]
        else:
            spec["kind"] = "vector"
            spec["shape"] = [len(jsonable)]
    elif isinstance(jsonable, dict):
        spec["kind"] = "object"
        spec["shape"] = None
    else:
        spec["kind"] = "object"
        spec["shape"] = None
    return spec


def infer_data_specs(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {key: infer_data_spec(value) for key, value in data.items()}


class DatasetJsonlWriter:
    """Write DataPoint events to data.jsonl."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: TextIO | None = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")

    def append_data_point(self, event: DataPoint) -> dict[str, Any]:
        if self._file is None:
            raise RuntimeError("DatasetJsonlWriter is not open")
        data = to_jsonable(event.data)
        payload = {
            "kind": "data_point",
            "point_id": event.point_id,
            "coords": to_jsonable(event.coords),
            "data": data,
            "metadata": to_jsonable(event.metadata),
            "data_specs": infer_data_specs(data),
            "time": event.timestamp,
        }
        self._file.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        self._file.flush()
        return payload

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


class PointsJsonlWriter:
    """Append point lifecycle snapshots to points.jsonl."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: TextIO | None = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")

    def append(self, record: dict[str, Any]) -> None:
        if self._file is None:
            raise RuntimeError("PointsJsonlWriter is not open")
        self._file.write(json.dumps(to_jsonable(record), sort_keys=True, separators=(",", ":")) + "\n")
        self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
