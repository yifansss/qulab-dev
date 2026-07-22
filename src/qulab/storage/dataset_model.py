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
    source_kind: str = "raw"
    group: str = "raw"
    source_module: str | None = None
    module_version: str | None = None


class DatasetModel:
    """Small testable model used by slicing and GUI layers."""

    def __init__(self, reader: RunReader, group: str | None = None) -> None:
        self.reader = reader
        self.group = group

    @classmethod
    def open(cls, run_path: str, backend: BackendPreference = "auto") -> "DatasetModel":
        return cls(RunReader(run_path, backend=backend))

    def list_data_groups(self) -> list[str]:
        return self.reader.list_data_groups()

    def list_data_keys(self, group: str | None = None) -> list[str]:
        return self.reader.list_data_keys(group=group or self.group)

    def describe_data_key(self, key: str) -> DataKeyInfo:
        selected_group = self.group
        data = self.reader.get_data_var_metadata(key, group=selected_group)
        return DataKeyInfo(
            key=key,
            kind=data.kind,
            dims=data.dims,
            unit=data.unit,
            backend=self.reader.backend_name,
            source_kind=data.attrs.get("source_kind", "raw"), group=selected_group or "root",
            source_module=data.attrs.get("source_module"), module_version=data.attrs.get("module_version"),
        )

    def get_data_var(self, key: str, selection: dict[str, object] | None = None) -> DataArray:
        return self.reader.get_data_var(key, selection=selection, group=self.group)

    def get_data_var_metadata(self, key: str) -> DataArray:
        return self.reader.get_data_var_metadata(key, group=self.group)

    def get_coords(self) -> dict[str, np.ndarray]:
        return self.reader.get_coords()
