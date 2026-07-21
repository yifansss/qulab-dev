# Prompt 008-followup: Dual CSV + Zarr Advanced Storage and Viewer

This followup belongs to **Prompt 008: Advanced Storage Backend + Data Viewer Worker**. It supersedes any single-backend assumption in Prompt 008.

---

## /goal

Implement Prompt 008 with mandatory CSV backend support and optional Zarr backend support. Both formats must satisfy Qulab's multidimensional slow-scan and per-point trace requirements through one shared `dataset_manifest.json`, `RunReader`, `DatasetModel`, and `SliceController`.

Key requirements:

1. CSV backend is mandatory.
2. Zarr backend is optional but preferred when dependency exists.
3. Viewer must support both through one abstraction.
4. JSONL + SQLite remain the audit/index layer.
5. Default tests must pass without Zarr.

---

## Required Implementation Priority

1. Manifest abstraction.
2. CSV backend.
3. RunReader for CSV.
4. SliceController for CSV:
   - line plot
   - heatmap
   - point trace
5. Optional Zarr backend.
6. RunReader backend selector:
   - Auto
   - CSV
   - Zarr
7. Optional PyQt viewer.

Do not start with Zarr-only. CSV must work first.

---

## Required Synthetic Runs

Create synthetic runs for tests:

```text
synthetic_csv_1d_scalar
synthetic_csv_2d_scalar
synthetic_csv_3d_scalar
synthetic_csv_point_trace
synthetic_csv_multichannel_trace
```

If Zarr is installed:

```text
synthetic_zarr_2d_scalar
synthetic_zarr_point_trace
synthetic_zarr_multichannel_trace
```

---

## Required Test Behaviors

CSV:

- 1D scalar line extraction.
- 2D scalar heatmap extraction.
- 3D scalar heatmap with third-dimension selector.
- point trace lookup.
- multi-channel trace lookup.

Zarr:

- same tests as CSV when `zarr` installed.
- skip cleanly otherwise.

Backend selector:

- Auto prefers Zarr if available.
- Auto falls back to CSV.
- User-forced CSV works even if Zarr exists.
- User-forced Zarr gives clear error if unavailable.

---

## Documentation

Update:

```text
docs/DATA_MODEL.md
docs/DATA_VIEWER_REQUIREMENTS.md
README.md
workers/storage_worker.md
workers/plotting_worker.md
workers/gui_worker.md
```

Mention this followup explicitly in final response.

