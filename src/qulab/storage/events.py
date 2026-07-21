"""JSONL event serialization for RunStore."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, TextIO

from qulab.core import Event


def to_jsonable(value: Any) -> Any:
    """Convert common experiment values into JSON-safe objects."""

    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    try:
        import numpy as np

        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    except Exception:
        pass

    return str(value)


def event_to_jsonable(event: Event) -> dict[str, Any]:
    """Return a JSON-safe dict for a core Event."""

    return to_jsonable(event.to_dict())


class EventJsonlWriter:
    """Append-only JSONL writer that flushes after each event."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: TextIO | None = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")

    def append(self, event: Event) -> dict[str, Any]:
        if self._file is None:
            raise RuntimeError("EventJsonlWriter is not open")
        payload = event_to_jsonable(event)
        self._file.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        self._file.flush()
        return payload

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
