"""Optional Zarr implementation of the advanced storage backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .array_backend import DataArray, OptionalDependencyError
from .csv_backend import _selector_to_index


class ZarrBackend:
    """Read Qulab advanced arrays from an optional Zarr store."""

    name = "zarr"

    def __init__(self, run_path: Path | str, manifest: dict[str, Any]) -> None:
        try:
            import zarr  # type: ignore
        except ImportError as exc:
            raise OptionalDependencyError("Zarr backend requires the optional 'zarr' package") from exc
        self._zarr = zarr
        self.run_path = Path(run_path)
        self.manifest = manifest
        zarr_root = manifest.get("backends", {}).get("zarr", "arrays.zarr")
        self.store_path = self.run_path / str(zarr_root)
        self.root = zarr.open_group(str(self.store_path), mode="r")

    @staticmethod
    def available() -> bool:
        try:
            import zarr  # noqa: F401
        except ImportError:
            return False
        return True

    def list_arrays(self) -> list[str]:
        return sorted(
            key for key, spec in self.manifest.get("data_vars", {}).items() if self._zarr_uri(spec) is not None
        )

    def read_array(self, key: str, selection: dict[str, Any] | None = None) -> DataArray:
        spec = self._data_spec(key)
        array_path = self._zarr_uri(spec)
        if array_path is None:
            raise KeyError(f"data variable {key!r} has no Zarr backend entry")
        dims = tuple(spec.get("dims", []))
        coords = {dim: np.asarray(self.root[f"coords/{dim}"][:]) for dim in dims}
        zarray = self.root[array_path]
        index = tuple(_selector_to_index(coords[dim], selection[dim]) if selection and dim in selection else slice(None) for dim in dims)
        values = np.asarray(zarray[index])
        kept_dims = tuple(dim for dim, part in zip(dims, index) if isinstance(part, slice))
        kept_coords = {dim: coords[dim][part] for dim, part in zip(dims, index) if isinstance(part, slice)}
        return DataArray(
            key=key,
            dims=kept_dims,
            coords=kept_coords,
            values=values,
            kind=spec.get("kind", "array"),
            unit=spec.get("unit"),
            attrs={"backend": self.name, **spec},
        )

    def _data_spec(self, key: str) -> dict[str, Any]:
        try:
            return self.manifest["data_vars"][key]
        except KeyError as exc:
            raise KeyError(f"unknown data variable {key!r}") from exc

    def _zarr_uri(self, spec: dict[str, Any]) -> str | None:
        uri = spec.get("backends", {}).get("zarr")
        if uri is None and str(spec.get("uri", "")).startswith("arrays.zarr:"):
            uri = spec.get("uri")
        if uri is None:
            return None
        text = str(uri)
        if ":" in text:
            text = text.split(":", 1)[1]
        return text.lstrip("/")
