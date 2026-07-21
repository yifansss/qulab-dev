# Live Compute and Derived Data Framework Plan

Status: planned framework, not yet implemented.

This document defines a framework for real-time derived quantities in Qulab.
It intentionally does not define experiment-specific formulas such as ODMR
fits, Rabi fits, contrast definitions, or detector-specific calibrations.
Instead, it defines where user-written compute modules live, how experiments
load them, what interface they must implement, how derived values are emitted,
how Live View selects raw and derived quantities, and how RunStore records the
results for later analysis.

## 1. Motivation

Long experiments cannot wait until the end of a run for all analysis and plots.
Operators need to see useful summary and derived quantities while the run is
still collecting data. At the same time, Qulab must preserve raw data and avoid
hardcoding experiment-specific analysis into the core executor or GUI.

Required behavior:

- Raw measurement data continues to be stored immediately.
- User-defined compute modules can transform raw point data into derived
  quantities during the run.
- Live View can display selected raw and derived quantities.
- RunStore can persist selected derived quantities and module provenance.
- All live computation can be enabled, disabled, or configured from YAML.
- A compute module failure must not silently corrupt raw data.

## 2. Current State

Implemented today:

- `EventBus` emits events during execution.
- `RunStore` subscribes to events and writes `events.jsonl`, `data.jsonl`,
  `points.jsonl`, CSV tables, and optional array backends.
- `DataPoint` events carry point data and coordinates.
- PyQt Operator Console subscribes to events and displays:
  - run log
  - simple line plot
  - point preview table
- The offline Data Viewer can read completed run folders through
  `RunReader`, `DatasetModel`, and `SliceController`.

Not yet implemented:

- A formal compute module interface.
- A compute registry/loader.
- A dedicated derived-data event type.
- Live View selection of raw vs derived data keys.
- Persistent metadata for compute module provenance.
- Per-module enable/show/save/fail policies.

## 3. Design Goals

1. Keep compute modules outside the core executor.

   The executor should keep running procedures and emitting raw events. Compute
   modules should subscribe to events or be invoked by a compute engine around
   the event stream.

2. Keep formulas user-owned and experiment-specific.

   Qulab defines the interface and storage semantics. Users define formulas in
   project-local modules.

3. Store derived values as first-class data, not GUI-only state.

   If a derived value is useful in Live View, it should be optionally saved with
   enough provenance to reproduce it later.

4. Never overwrite raw data.

   Derived data must be appended as separate data keys, derived events, analysis
   artifacts, or manifest entries.

5. Make failure policy explicit.

   A compute module can fail without stopping the experiment if configured as
   `warn` or `skip`, but critical modules can be configured as `fail`.

6. Keep Live View read/select/display oriented.

   Live View should choose which quantities to show. It should not contain
   formula logic.

## 4. Proposed Directory Layout

Project-local compute modules should live under:

```text
analysis_modules/
  README.md
  trace_window_mean.py
  scalar_formula.py
  fitting/
    odmr_fit.py
```

Alternative package-style location for built-in helpers:

```text
src/qulab/analysis/
  __init__.py
  base.py
  registry.py
  engine.py
  events.py
```

Rules:

- `analysis_modules/` is for lab/user formulas.
- `src/qulab/analysis/` is for framework code and optional generic helpers.
- Relative module paths are resolved from the Qulab project root first.
- User modules must not import hardware drivers or perform hardware actions.
- User modules should be import-safe; expensive model loading should happen in
  `setup(...)`, not module import.

## 5. Compute Module Interface

The preferred interface is class-based, with a lightweight function shortcut
allowed later.

Planned base protocol:

```python
class ComputeModule:
    name: str
    version: str = "0"
    input_keys: tuple[str, ...]
    output_keys: tuple[str, ...]

    def setup(self, config: dict, run_context: dict) -> None:
        ...

    def process_point(self, point: "ComputePoint") -> "ComputeResult | None":
        ...

    def close(self) -> None:
        ...
```

`ComputePoint` should provide:

```python
@dataclass(frozen=True)
class ComputePoint:
    point_id: str
    coords: dict[str, Any]
    data: dict[str, Any]
    metadata: dict[str, Any]
    timestamp: str
```

`ComputeResult` should provide:

```python
@dataclass(frozen=True)
class ComputeResult:
    data: dict[str, Any]
    units: dict[str, str | None] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
```

Notes:

- `data` contains derived values keyed by output name.
- Outputs may be scalar, vector, trace, image-like arrays, or structured dicts,
  but scalar and small vectors should be the first implementation target.
- Units are optional but strongly recommended.
- Metadata records windows, coefficients, thresholds, or other formula settings.
- Quality may record flags, fit errors, warnings, or confidence scores.

## 6. YAML Configuration

Planned top-level section:

```yaml
analysis:
  live:
    enabled: true
    fail_policy: warn        # warn | skip | fail
    save_outputs: true
    emit_events: true

  modules:
    - name: trace_summary
      module: analysis_modules.trace_window_mean
      class: TraceWindowMean
      enabled: true
      run_live: true
      run_post: false
      show: true
      save: true
      fail_policy: warn
      inputs: [pse_ai1_trace]
      outputs: [signal_mean, baseline_mean, contrast]
      args:
        signal_window_s: [1.0e-6, 3.0e-6]
        baseline_window_s: [0.0, 0.8e-6]

    - name: custom_scalar
      module: analysis_modules.scalar_formula
      function: compute
      enabled: false
      run_live: true
      show: false
      save: true
      inputs: [counts_mean]
      outputs: [normalized_counts]
      args: {}
```

Configuration fields:

- `analysis.live.enabled`: global live compute switch.
- `analysis.live.fail_policy`: default failure behavior.
- `analysis.live.save_outputs`: default derived storage switch.
- `analysis.live.emit_events`: whether to emit derived result events.
- `modules[*].name`: stable module instance name.
- `modules[*].module`: import path or project-relative `.py` file.
- `modules[*].class`: class name implementing the protocol.
- `modules[*].function`: optional function-style shortcut.
- `modules[*].enabled`: module-level switch.
- `modules[*].run_live`: run during acquisition.
- `modules[*].run_post`: eligible for post-run recomputation.
- `modules[*].show`: default visible in Live View.
- `modules[*].save`: write derived outputs into RunStore.
- `modules[*].inputs`: data keys required from raw or prior derived data.
- `modules[*].outputs`: declared output keys.
- `modules[*].args`: formula/module-specific settings.

The framework must validate that `inputs` and `outputs` are declared. It should
warn if an input key is not observed yet, but it should not fail before the run
unless the key is impossible from config metadata.

## 7. Event Flow

Current flow:

```text
Executor -> DataPoint event -> RunStore
                         \-> Live View plot
```

Planned flow:

```text
Executor
  -> raw DataPoint event
      -> RunStore raw storage
      -> LiveComputeEngine
          -> DerivedData event
              -> RunStore derived storage
              -> Live View raw/derived selector
```

The compute engine should subscribe to the same `EventBus`. It should receive
raw `DataPoint` events after or alongside RunStore. To keep raw storage safe,
the recommended subscription order is:

1. RunStore stores raw event.
2. LiveComputeEngine processes raw event.
3. RunStore stores derived event.
4. GUI displays raw/derived event.

The event bus may need a safe re-emit mechanism so compute modules can emit
derived events without recursive loops.

## 8. Derived Event Type

Planned event:

```python
@dataclass
class DerivedData(Event):
    point_id: str
    coords: dict[str, Any]
    data: dict[str, Any]
    source_module: str
    input_keys: list[str]
    output_keys: list[str]
    units: dict[str, str | None] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
```

Architecture decision:

- Use a dedicated `DerivedData` event from P10.2 onward.
- Add `AnalysisStatus` for module lifecycle, latency, error, queue, and lag
  information.
- Do not infer raw/derived kind from a normal `DataPoint` metadata field.
- `DerivedData.save` controls persistence; `show` controls the default Live View
  selection. A live-only event (`show: true`, `save: false`) must not be written
  to `events.jsonl`, data backends, or completed-run manifests.
- EventBus nested emissions use queued, non-recursive dispatch so every raw
  event reaches raw storage and GUI subscribers before its derived events.

## 9. RunStore Storage Rules

RunStore must be able to store derived outputs according to module settings.

Raw data:

- Always stored when emitted as raw `DataPoint`.
- Never overwritten by derived outputs.

Derived data:

- Stored only when `analysis.live.save_outputs` and module `save` are true.
- Stored as separate data keys.
- Marked with metadata indicating:
  - `kind: derived`
  - `source_module`
  - `module_version`
  - `input_keys`
  - `output_keys`
  - `args`
  - `run_live: true/false`

Suggested key naming:

```text
contrast
signal_mean
baseline_mean
trace_summary.contrast       # optional namespace if collisions occur
```

Collision rule:

- If a derived output key collides with a raw key, preflight should error unless
  the module declares an explicit namespace.
- The framework should never replace raw `counts_mean` with a derived
  `counts_mean` without an explicit, visible configuration.

Metadata addition:

```json
{
  "analysis_modules": [
    {
      "name": "trace_summary",
      "module": "analysis_modules.trace_window_mean",
      "class": "TraceWindowMean",
      "version": "1",
      "enabled": true,
      "run_live": true,
      "save": true,
      "show": true,
      "inputs": ["pse_ai1_trace"],
      "outputs": ["signal_mean", "baseline_mean", "contrast"],
      "args": {
        "signal_window_s": [1e-6, 3e-6]
      }
    }
  ]
}
```

## 10. Live View Requirements

Live View should separate raw and derived keys:

```text
Raw
  [x] counts_mean
  [ ] photon_bins
  [x] pse_ai1_trace

Derived
  [x] signal_mean
  [x] contrast
  [ ] fit_center_hz
```

Required controls:

- raw/derived key selector
- plot type selector: scalar monitor, line, heatmap, trace
- x-axis selector from coords
- selector controls for extra dimensions
- module status panel:
  - enabled/disabled
  - last success
  - last warning/error
  - processing latency

Live View must be able to show:

- raw scalar per point
- derived scalar per point
- raw trace for selected point
- derived trace or reduced trace if provided
- 2D heatmap when two scan coords exist and selected key is scalar

Live View should not be responsible for formula execution. It only receives
events and reads already declared raw/derived keys.

P9/P10 GUI integration also adds a read-only Sequence Context panel in Live
Run. It consumes `SequenceSelected` and shows the actual plan/family,
Template/Generic Sweep mode, bundle entry, point coordinates, and hashes used at
the current point. Sequence authoring remains in the Control page's Sequence
Sweep submode. Detailed layout and shared controller contract:
`docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md`.

## 11. Post-Run Recompute

The same compute modules should be reusable after the run:

```bash
python -m qulab.analysis.recompute --run runs/... --module trace_summary
```

Post-run recompute must:

- read raw data through `RunReader` / `DatasetModel`, not ad hoc paths
- write new derived artifacts or a new derived dataset group
- never overwrite raw data
- update metadata with recompute timestamp and module version

This enables:

- fixing analysis settings after a run
- recomputing with a newer module version
- comparing live-derived and post-derived results

## 12. Failure Policy

Policies:

- `warn`: log error, emit module status warning, continue run.
- `skip`: skip output for that point, continue run quietly except debug log.
- `fail`: raise error and fail the run.

Default should be `warn` for live compute because raw data preservation is more
important than derived display during long experiments.

Failure records should include:

- module name
- point_id
- input keys
- exception type and message
- traceback in logs only, not necessarily in GUI summary

RunStore should record analysis error count separately from hardware/executor
error count if possible.

## 13. Performance and Safety

Live compute must not block time-critical hardware sequencing.

Rules:

- Compute runs after a point's raw data is available, not during hardware pulse
  timing.
- Long-running modules should run in a worker thread/process.
- Compute queue must be bounded or backpressure-aware.
- If compute falls behind, policy can be:
  - skip live compute for some points
  - continue storing raw data
  - mark module status as lagging
- Compute modules must not mutate raw data objects in place.
- Compute modules must not open hardware connections.

Initial MVP can run modules synchronously after each `DataPoint` if modules are
lightweight and marked safe, but the framework should leave room for async
execution.

## 14. Preflight and Validation

Preflight should validate:

1. Module import path resolves from project root.
2. Class/function exists.
3. Module declares input and output keys.
4. Output keys do not collide with raw keys unless namespaced.
5. `args` are JSON/YAML serializable.
6. Module `setup(...)` can run without hardware.
7. Unknown fail policy or mode is rejected.
8. `show: true` without `save: true` is allowed, but GUI should mark the result
   as live-only unless another storage path is configured.

Validation should not require that all input keys have already appeared before
the run starts. Many input keys are only known once the first point emits data.

## 15. Example Generic Compute Module

This is an interface example, not a required formula:

```python
class ExampleModule:
    name = "example_module"
    version = "1"
    input_keys = ("raw_key",)
    output_keys = ("derived_key",)

    def setup(self, config, run_context):
        self.scale = float(config.get("scale", 1.0))

    def process_point(self, point):
        value = point.data["raw_key"]
        return {
            "data": {"derived_key": value * self.scale},
            "units": {"derived_key": None},
            "metadata": {"scale": self.scale},
        }
```

Framework implementation can accept either a `ComputeResult` object or a plain
dict with `data`, `units`, and `metadata` keys.

## 16. Implementation Phases

### Phase A: Framework Schema and Import-Safe Registry

Worker prompt: `prompts/010_followup_p10_1_analysis_schema_registry.md`.

Add:

- `src/qulab/analysis/base.py`
- `src/qulab/analysis/registry.py`
- parser for `analysis.live` and `analysis.modules`
- validation tests

No GUI or storage changes required beyond metadata preview.

### Phase B: LiveComputeEngine and Derived Event Storage

Worker prompt: `prompts/010_followup_p10_2_live_compute_engine_storage.md`.

Add:

- `LiveComputeEngine`
- compute engine subscription to `DataPoint`
- derived outputs emitted as dedicated `DerivedData`
- module lifecycle/failure emitted as `AnalysisStatus`
- EventBus queued re-emit preserves raw-before-derived dispatch
- RunStore stores derived outputs like normal data keys

Acceptance:

- A test module in `analysis_modules/` computes a derived scalar from a raw
  scalar during dry-run.
- Raw and derived keys both appear in `metadata.json.data_keys`.

### Phase C: Live View Raw/Derived Selector

Worker prompt:
`prompts/010_followup_p10_3_live_view_gui_sequence_integration.md`.

Add:

- raw/derived data key model
- checkboxes or list selector in Live Run page
- plot selected key rather than auto-picking `counts_mean`
- module status panel
- read-only P9 sequence context for curated/template/generic bundle runs

Acceptance:

- User can select `contrast` instead of raw `counts_mean` for live line plot.
- User can hide/show derived keys without changing stored data.

### Phase D: Analysis Provenance and Post-Run Recompute

Worker prompt:
`prompts/010_followup_p10_4_analysis_provenance_recompute.md`.

Add:

- analysis module metadata in `metadata.json`
- optional `analysis.jsonl`
- recompute CLI using `RunReader`
- derived artifacts or derived dataset groups

Acceptance:

- A completed run can be recomputed with a module and new derived outputs are
  written without modifying raw arrays.

### Phase E: Async Compute for Long Runs

Worker prompt:
`prompts/010_followup_p10_5_async_compute_backpressure.md`.

Add:

- worker queue
- processing latency metrics
- skip/backpressure policy
- GUI lag status

Acceptance:

- Slow live compute does not stop raw acquisition/storage.

## 17. Non-Goals

This framework does not define:

- ODMR fitting equations.
- Rabi fitting equations.
- Detector-specific calibration formulas.
- A general symbolic math language.
- Hardware-timing behavior.

Those belong in user modules under `analysis_modules/` or later optional helper
packages. The core framework only defines how such modules are loaded, run,
displayed, stored, and tracked.

## 18. Immediate Next Tasks

1. Start P10.1 schema/registry without modifying P9-owned GUI files.
2. Start P10.2 after P10.1 and establish the final event/storage lifecycle.
3. Wait for P9.3C handoff before P10.3 modifies shared controller/Qt views.
4. Implement P10.4 immutable recompute groups after the live storage contract is
   stable.
5. Implement P10.5 async queue only after synchronous engine and GUI point
   association are proven.
