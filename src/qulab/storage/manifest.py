"""Dataset manifest helpers shared by CSV and Zarr backends."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .events import to_jsonable


@dataclass
class DatasetManifest:
    """Logical dataset manifest for advanced storage backends."""

    preferred_backend: str | None = None
    available_backends: list[str] = field(default_factory=list)
    coords: dict[str, dict[str, Any]] = field(default_factory=dict)
    data_vars: dict[str, dict[str, Any]] = field(default_factory=dict)
    schema_version: int = 1

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DatasetManifest":
        available = payload.get("available_backends")
        if available is None:
            available = sorted(payload.get("backends", {}).keys())
        return cls(
            preferred_backend=payload.get("preferred_backend"),
            available_backends=list(available),
            coords=dict(payload.get("coords", {})),
            data_vars=dict(payload.get("data_vars", {})),
            schema_version=int(payload.get("schema_version", 1)),
        )

    @classmethod
    def read(cls, path: Path | str) -> "DatasetManifest":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        backends = {name: "tables" if name == "csv" else "arrays.zarr" for name in self.available_backends}
        return {
            "schema_version": self.schema_version,
            "preferred_backend": self.preferred_backend,
            "available_backends": list(self.available_backends),
            "backends": backends,
            "coords": self.coords,
            "data_vars": self.data_vars,
        }

    def write(self, path: Path | str) -> None:
        Path(path).write_text(
            json.dumps(to_jsonable(self.to_dict()), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
