"""Run storage, metadata, and dataset persistence."""

from .array_backend import DataArray, OptionalDependencyError
from .backends import ADVANCED_BACKENDS, normalize_storage_backends
from .csv_backend import CsvBackend
from .dataset import DatasetJsonlWriter, PointsJsonlWriter, infer_data_spec, infer_data_specs
from .dataset_model import DataKeyInfo, DatasetModel
from .events import EventJsonlWriter, event_to_jsonable, to_jsonable
from .index import RunIndex
from .manifest import DatasetManifest
from .metadata import MetadataWriter
from .run_store import RunStore
from .run_reader import RunReader
from .slicing import HeatmapData, LineData, SliceController, TraceData
from .synthetic import create_synthetic_advanced_run
from .zarr_backend import ZarrBackend

__all__ = [
    "CsvBackend",
    "ADVANCED_BACKENDS",
    "DataArray",
    "DataKeyInfo",
    "DatasetJsonlWriter",
    "DatasetModel",
    "DatasetManifest",
    "EventJsonlWriter",
    "HeatmapData",
    "LineData",
    "MetadataWriter",
    "OptionalDependencyError",
    "PointsJsonlWriter",
    "RunIndex",
    "RunReader",
    "RunStore",
    "SliceController",
    "TraceData",
    "ZarrBackend",
    "create_synthetic_advanced_run",
    "event_to_jsonable",
    "infer_data_spec",
    "infer_data_specs",
    "normalize_storage_backends",
    "to_jsonable",
]
