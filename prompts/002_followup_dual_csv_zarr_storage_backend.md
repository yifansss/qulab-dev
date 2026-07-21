# Prompt 002-followup: CSV + Zarr Dual Storage Backend

This followup belongs to **Prompt 002: Storage RunStore Worker** and all future storage workers. It adds a concrete requirement: Qulab storage must support both CSV and Zarr as selectable advanced backends while preserving the existing JSONL + SQLite layer.

---

## /goal

Extend the storage plan so Qulab can write and read experiment data through selectable `csv` and `zarr` backends. Preserve the current `metadata.json`, `events.jsonl`, `points.jsonl`, `data.jsonl`, and `run_index.sqlite` behavior. Add a unified `dataset_manifest.json` so CSV and Zarr expose the same logical data model to `RunReader`, viewer, plotting, and analysis code.

Success criteria:

1. Existing JSONL + SQLite behavior remains unchanged.
2. Users can select:

```yaml
storage:
  backend: csv
```

or:

```yaml
storage:
  backend: zarr
```

or:

```yaml
storage:
  backends: [csv, zarr]
```

3. CSV backend supports scalar summaries, multidimensional slow-scan coordinates, per-point vector traces, and multi-channel traces.
4. Zarr backend supports chunked coordinate arrays, scalar grids, trace grids, and lazy slicing.
5. `dataset_manifest.json` describes all logical data variables and their backend URIs.
6. Default `python -m pytest` passes without optional `zarr`; Zarr tests skip if missing.
7. GUI/viewer code must not read CSV/Zarr directly; it must use `RunReader` / `DatasetModel`.

---

## Must Read

Before implementing, read:

1. `docs/DATA_MODEL.md`
2. `docs/DATA_VIEWER_REQUIREMENTS.md`
3. `prompts/supplements/dual_storage_backend_support.md`
4. `workers/storage_worker.md`
5. Current `src/qulab/storage/`

---

## Required Files or Modules

Suggested additions:

```text
src/qulab/storage/backends.py
src/qulab/storage/csv_backend.py
src/qulab/storage/zarr_backend.py
src/qulab/storage/manifest.py
src/qulab/storage/run_reader.py
src/qulab/storage/dataset_model.py
src/qulab/storage/slicing.py
```

Tests:

```text
tests/unit/test_csv_backend.py
tests/unit/test_manifest_backends.py
tests/unit/test_run_reader_backends.py
tests/unit/test_dataset_slicing_csv.py
tests/unit/test_dataset_slicing_zarr_optional.py
```

---

## CSV Backend Requirements

CSV is mandatory because it requires no heavy dependency.

Recommended layout:

```text
tables/
  points.csv
  data_keys.csv
  summaries/
    counts_mean.csv
  traces/
    photon_bins.csv
    analog_trace.csv
```

CSV must support long-form records:

Scalar summaries:

```text
point_id,mw_freq_hz,tau_s,key,value,unit
p000001,2.870e9,1.0e-7,counts_mean,1234,count
```

Trace rows:

```text
point_id,mw_freq_hz,tau_s,channel,time_s,key,value,unit
p000001,2.870e9,1.0e-7,ai0,0.000001,analog_trace,0.012,V
```

Rules:

- Always include `point_id`.
- Always preserve scan coordinates.
- Preserve `channel` and `time_s` for trace data.
- Preserve units where available.
- Make CSV reconstructable into the same `DatasetModel` used by Zarr.

---

## Zarr Backend Requirements

Zarr is preferred for large multidimensional data, but optional.

Recommended layout:

```text
arrays.zarr/
  coords/
    mw_freq_hz
    tau_s
    time_s
    channel
  summaries/
    counts_mean
  traces/
    photon_bins
    analog_trace
```

Rules:

- Import `zarr` lazily.
- If unavailable, raise a clear optional dependency error.
- Tests that require `zarr` must use `pytest.importorskip("zarr")`.
- Chunk arrays by slow scan dims and trace dims.

---

## Manifest Requirement

Both backends must be described by:

```text
dataset_manifest.json
```

Example:

```json
{
  "schema_version": 1,
  "preferred_backend": "zarr",
  "available_backends": ["csv", "zarr"],
  "coords": {
    "mw_freq_hz": {"unit": "Hz"},
    "tau_s": {"unit": "s"},
    "time_s": {"unit": "s"}
  },
  "data_vars": {
    "counts_mean": {
      "kind": "scalar_grid",
      "dims": ["mw_freq_hz", "tau_s"],
      "unit": "count",
      "backends": {
        "csv": "tables/summaries/counts_mean.csv",
        "zarr": "arrays.zarr:/summaries/counts_mean"
      }
    },
    "photon_bins": {
      "kind": "trace_grid",
      "dims": ["mw_freq_hz", "tau_s", "time_s"],
      "unit": "count",
      "backends": {
        "csv": "tables/traces/photon_bins.csv",
        "zarr": "arrays.zarr:/traces/photon_bins"
      }
    }
  }
}
```

---

## Validation Commands

Run:

```bash
python -m pytest
PYTHONPATH=src python -c "from qulab.storage.run_reader import RunReader; print(RunReader.__name__)"
PYTHONPATH=src python -c "from qulab.storage.manifest import DatasetManifest; print(DatasetManifest.__name__)"
```

If `zarr` is installed, also ensure Zarr tests pass. If it is not installed, Zarr tests must skip cleanly.

