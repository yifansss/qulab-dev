"""Backend-independent dataset model for run viewers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .array_backend import DataArray
from .run_reader import BackendPreference, RunReader


@dataclass(frozen=True)
class DataKeyInfo:
    key: str
    kind: str
    dims: tuple[str, ...]
    unit: str | None
    backend: str | None


class DatasetModel:
    """Small testable model used by slicing and GUI layers."""

    def __init__(self, reader: RunReader) -> None:
        self.reader = reader

    @classmethod
    def open(cls, run_path: str, backend: BackendPreference = "auto") -> "DatasetModel":
        return cls(RunReader(run_path, backend=backend))

    def list_data_keys(self) -> list[str]:
        return self.reader.list_data_keys()

    def describe_data_key(self, key: str) -> DataKeyInfo:
        data = self.reader.get_data_var_metadata(key)
        return DataKeyInfo(
            key=key,
            kind=data.kind,
            dims=data.dims,
            unit=data.unit,
            backend=self.reader.backend_name,
        )

    def get_data_var(self, key: str, selection: dict[str, object] | None = None) -> DataArray:
        return self.reader.get_data_var(key, selection=selection)

    def get_data_var_metadata(self, key: str) -> DataArray:
        return self.reader.get_data_var_metadata(key)

    def get_coords(self) -> dict[str, np.ndarray]:
        return self.reader.get_coords()
