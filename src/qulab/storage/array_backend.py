"""Shared array backend models for advanced run storage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np


class OptionalDependencyError(RuntimeError):
    """Raised when a requested optional storage backend is unavailable."""


@dataclass(frozen=True)
class DataArray:
    """A labelled numeric array exposed by a storage backend."""

    key: str
    dims: tuple[str, ...]
    coords: dict[str, np.ndarray]
    values: np.ndarray
    kind: str
    unit: str | None = None
    attrs: dict[str, Any] | None = None


class ArrayBackend(Protocol):
    """Protocol implemented by CSV and optional Zarr array backends."""

    name: str

    def read_array(self, key: str, selection: dict[str, Any] | None = None) -> DataArray:
        """Read a labelled array, optionally sliced by dimension selectors."""

    def list_arrays(self) -> list[str]:
        """Return data variable keys available in this backend."""
