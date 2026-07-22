# Sequence Sweep and Live Compute GUI Integration Plan

Status: implemented for P9.3/P10 headless contracts and the shared Operator
Console pages. Sequence Sweep remains the sole authoring panel; Live Run is a
read-only consumer of `SequenceSelected`, raw, derived, and status events.

## 1. Responsibility Split

The main window keeps three top-level pages:

```text
Control | Live Run | Data Viewer
```

### Control

Submodes:

```text
Operator Parameters | Sequence Sweep | Builder Workflow | Direct Control
```

`Sequence Sweep` owns authoring and preparation:

- curated Sequence Family selection;
- Generic ASG Template Sweep selection;
- fixed/linspace/range/explicit sequence parameters;
- pulse target/property/propagation/anchor editing;
- representative-point preview;
- bundle materialization and P9 preflight;
- generated plan/bundle/hash status.

It does not execute live analysis or plot derived formulas.

### Live Run

Live Run owns observation, not authoring:

- raw/derived data key selection;
- scalar/line/heatmap/trace plot selection;
- extra-dimension selectors;
- compute module status/latency/error state;
- current sequence context from `SequenceSelected`;
- current scan coordinates and point status;
- event/run log.

It does not edit pulse targets, generate bundles, or execute formulas directly.

### Data Viewer

Data Viewer reads completed runs through `RunReader`/`DatasetModel`:

- stored raw keys;
- stored live-derived keys;
- post-run recompute result groups;
- analysis and sequence provenance.

It remains read-only for raw data.

## 2. Shared Controller State

`OperatorController` remains the headless-friendly owner of config/preparation
and run state. P9.3 and P10 may extend it, but must not create separate GUI-only
controllers.

Recommended state:

```text
authoring_config
prepared_experiment
sequence_plan_status
analysis_plan_status
current_run
live_data_catalog
analysis_module_status
current_sequence_selection
```

Any authoring change invalidates `prepared_experiment`. Start is enabled only
after both sequence and analysis preflight pass.

P10.3 must consume the actual P9.3C controller handoff. It must not overwrite or
fork P9.3C's sequence plan model.

## 3. Event Contract

Live Run consumes:

```text
MeasurementStarted / MeasurementCompleted
ParameterChanged
DataPoint                 # raw
DerivedData               # analysis output
AnalysisStatus            # module lifecycle/error/latency/queue
SequenceSelected          # concrete sequence used at point
ErrorRaised / LogMessage
```

Required ordering per raw event:

```text
raw DataPoint
  -> RunStore raw write
  -> GUI raw catalog/update
  -> LiveComputeEngine
  -> DerivedData
      -> RunStore conditional derived write
      -> GUI derived catalog/update
```

EventBus re-emission must be queued rather than recursively dispatched. The
compute engine never processes `DerivedData` as a new raw point.

For async Phase E, derived events may arrive after later raw points. Point ID
and coords, not arrival order, are the association authority.

## 4. Live Data Catalog

Use a headless model shared by GUI tests:

```python
@dataclass(frozen=True)
class LiveDataKeySpec:
    key: str
    source_kind: Literal["raw", "derived"]
    data_kind: str
    unit: str | None
    dims: tuple[str, ...]
    source_module: str | None
    saved: bool
    visible_default: bool
    status: str
```

The catalog is initialized from config declarations:

- raw `save_as` and plot/data specs when discoverable;
- declared analysis module outputs;
- scan/sequence-plan coordinate definitions.

It is updated by actual events. Pending declared outputs remain visible as
`waiting`; they do not disappear before the first result.

Raw/derived key collisions are preflight errors unless the derived output has
an explicit namespace.

## 5. Live Run Layout

Recommended work-focused layout:

```text
Left/side controls
  Data Sources
    Raw       [x] counts  [ ] trace
    Derived   [x] contrast (saved) [ ] live_only (live-only)
  Plot
    type | x | y | selectors | channel

Main plot
  selected compatible overlays or one primary key

Right/status
  Compute Modules
    name | state | last point | latency | queue | error
  Sequence Context
    plan/family | bundle/entry | point coords | sequence hash

Bottom
  point/event table | run log
```

Do not put formula editors in Live Run. Module args and enable/show/save policy
belong to Control/Operator Parameters or a compact analysis configuration
section before Prepare.

## 6. Plot Rules

- Scalar + one selected scan coordinate -> line.
- Scalar + two selected scan coordinates -> heatmap.
- Vector/trace -> selected point trace.
- More than two scan dimensions -> x/y plus selectors for remaining dims.
- Compatible scalar keys may overlay; incompatible units/dims require separate
  selection or explicit secondary-axis support later.
- Raw and derived data use the same plot pipeline.
- Key names do not determine plot type; data specs/dims do.
- Sequence coordinates generated by P9.3 appear like normal scan coords.

Live buffers are append/update models keyed by `(point_id, data_key)`. A derived
result arriving later updates the same point, not a new measurement point.

## 7. Sequence Context in Live Run

On `SequenceSelected`, show:

- sequence plan ID if generated;
- family/provider and template/generic mode when available;
- bundle and entry ID;
- requested and resolved coordinates;
- short sequence and manifest hashes;
- trigger/duration metadata summary;
- status if source changed or selection failed.

This panel is read-only. An `Open in Control` command may switch to Sequence
Sweep for authoring, but it must not mutate the running plan.

For old single-file `asg.load_sequence`, show the resource sequence snapshot
when available. Do not pretend it is a bundle entry.

## 8. Analysis Configuration in Control

Operator Parameters may expose a compact module table:

```text
Enabled | Module | Run Live | Show | Save | Fail Policy | Status
```

Module-specific `args` can use schema-driven controls if the module declares an
optional argument spec. Otherwise Builder/YAML remains the explicit editor.

No arbitrary formula text/eval is added to the GUI. User formulas remain Python
modules under `analysis_modules/`.

Any module config change invalidates Prepare. Import/setup validation runs
without hardware.

## 9. Storage and Viewer Contract

RunStore distinguishes:

- raw `DataPoint`;
- saved `DerivedData`;
- live-only `DerivedData` (not persisted in events/data backends);
- `AnalysisStatus`/analysis diagnostics;
- post-run recompute groups.

`dataset_manifest.json` data vars must include source kind/module/provenance
references so `RunReader` can expose raw/derived categories.

Data Viewer must not infer source kind from key names. Post-run recompute results
are exposed as an explicit result group/version, not merged destructively over
live-derived data.

## 10. Dependency Order

Safe implementation order:

1. P10.1 schema/module registry.
2. P10.2 synchronous engine/events/storage.
3. Wait for P9.3C GUI controller/submode handoff.
4. P10.3 integrated Live Run GUI and sequence context.
5. P10.4 provenance/recompute/viewer groups.
6. P10.5 async queue/lag/backpressure.

P10.1/P10.2 can proceed while P9.3 workers are active if they avoid P9-owned GUI
files. P10.3 must begin only after both P10.2 and P9.3C public interfaces are
stable.

## 11. Acceptance

- A generated Rabi sequence plan runs through the normal P9 bundle action.
- Live Run shows current `tau_s`, bundle entry, and sequence hash.
- A raw trace produces a declared derived scalar through P10.
- Raw and derived keys appear in one catalog with clear source/save badges.
- Operator can select the derived scalar for line/heatmap display.
- Module error/latency/queue status is visible without hiding raw data.
- Saved derived data appears in Data Viewer; live-only data does not appear in
  completed-run storage.
- Sequence authoring and live analysis remain separate but coordinated views of
  the same prepared experiment.
