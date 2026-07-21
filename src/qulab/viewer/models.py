"""Small viewer-facing models built on storage reader abstractions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qulab.storage import DatasetModel, RunReader
from qulab.storage.run_reader import BackendPreference


@dataclass
class ViewerState:
    """Read-only run viewer state independent from any GUI toolkit."""

    run_path: Path
    backend: BackendPreference = "auto"

    def open_model(self) -> DatasetModel:
        return DatasetModel(RunReader(self.run_path, backend=self.backend))
