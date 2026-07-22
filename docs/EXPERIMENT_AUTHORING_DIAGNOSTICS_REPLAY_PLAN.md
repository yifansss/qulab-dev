# Experiment Authoring Diagnostics and Historical Replay Plan

Status: planned (P11)

## 1. Purpose

P11 makes experiment authoring understandable and fail-closed without turning Qulab into a vendor-specific visual programming system. It addresses three operator problems:

1. Invalid YAML or invalid workflow steps currently appear to load successfully because full parsing and preflight happen later.
2. Historical runs can be opened as datasets, but the Operator Console cannot reconstruct the recorded workflow, parameters, sequence context, diagnostics, logs, and event timeline as one read-only workspace.
3. Workflow and sequence authoring currently require users to know adapter method names, argument names, units, ordering, save behavior, and sequence-plan syntax from memory.

The source of truth remains portable YAML plus explicit project modules. GUI forms edit that model; they do not become a second execution format.

## 2. Current Baseline

### 2.1 Config load

- `OperatorController.load_config()` currently loads YAML and constructs the sequence sweep model.
- Full `prepare_and_parse_experiment_config()` runs only during Prepare.
- The Qt load path clears the preflight issue table after loading.
- PyYAML syntax errors can reach a modal dialog, but semantic failures do not have a common diagnostic model with code, config path, workflow node, line, column, and suggested correction.
- The core parser already treats missing `setup` and `cleanup` as valid empty sections.

### 2.2 Historical runs

RunStore already records much of the reproducible state:

- `config.yaml`;
- `resolved_config.yaml`;
- `metadata.json`;
- `events.jsonl`, `points.jsonl`, `data.jsonl`, and advanced data backends;
- logs;
- sequence snapshots, generated plans, manifests, selected entries, and copied sequence artifacts;
- analysis module declarations and recompute result groups.

The Data Viewer can open historical data, but there is no read-only historical Operator workspace. Exact physical state cannot be reconstructed when it was never recorded. Historical replay must distinguish recorded fact, derived reconstruction, and unavailable information.

### 2.3 Authoring

- Workflow Builder supports basic tree operations and free-form call/args editing.
- Capability names exist, but there is no machine-readable action schema for arguments, units, defaults, return shape, safety class, allowed phase, or ordering constraints.
- Sequence providers already expose `SequenceFamilySpec` and `SequenceParameterSpec`.
- Sequence Sweep supports curated families and generic template plans, but guidance and inline validation are incomplete.
- The standalone sequence editor is bridged as an external tool, but its supported operations and diagnostics are not presented as a versioned contract in the main GUI.

## 3. Design Decisions

### 3.1 Candidate load is transactional

Loading a file creates a candidate document. Validation runs without connecting hardware or enabling output. A candidate with errors does not replace the last valid active experiment. The diagnostics UI still shows the attempted file and all available errors.

Stages:

1. `decode`: file access, encoding, YAML syntax, duplicate-key detection.
2. `structure`: top-level and step schema, required fields, types, unknown step forms.
3. `references`: resources, adapters, capabilities, actions, arguments, parameter references, sequence providers/templates/bundles, analysis modules.
4. `preflight_offline`: sync ordering, bundle coverage, timing/acquisition compatibility, save key collisions, safety/template gates.

Load may activate a candidate with warnings, but Start remains blocked for any error. Prepare reruns the same validation pipeline and may add hardware-derived checks only when explicitly requested by the existing workflow.

### 3.2 One diagnostic contract

All config-facing validation should converge on a structured issue:

```python
@dataclass(frozen=True)
class ConfigDiagnostic:
    severity: str                 # error | warning | info
    code: str
    message: str
    config_path: tuple[str | int, ...]
    workflow_path: tuple[str | int, ...] | None = None
    source_file: str | None = None
    line: int | None = None        # one-based
    column: int | None = None      # one-based
    hint: str | None = None
    related_paths: tuple[tuple[str | int, ...], ...] = ()
```

Stable codes are for tests and filtering. Human messages explain the concrete resource, action, argument, value, or missing step. Tracebacks are logged for developers but are not the primary operator message.

PyYAML node composition can build a path-to-source-mark index without introducing a second YAML parser. Duplicate keys require an explicit loader check because normal `safe_load` silently overwrites them.

### 3.3 Historical workspace is read-only

Opening a historical run must never:

- connect hardware;
- call an adapter action;
- mutate the run folder;
- overwrite the active experiment silently;
- claim that unrecorded physical state is known.

The workspace shows:

- run identity/status/timestamps/software and provenance;
- authoring and resolved workflow snapshots;
- operator/sequence parameters;
- declared resources, recorded snapshots, sync plan, and missing-snapshot indicators;
- sequence plans, artifacts, hashes, and point selections;
- raw/derived/recomputed data;
- logs, errors, and an event timeline;
- a replay of recorded events into read-only Live View models.

`Clone as new experiment` is a separate explicit action. It copies authoring config to a new project-relative file, rewrites references only when a safe recorded artifact mapping exists, disables output authorization, marks hardware verification as required, and runs P11.1 validation. It never edits the historical run.

### 3.4 Action descriptions are explicit, not introspection-only

GUI authoring needs a public, import-safe descriptor registry:

```python
AdapterSpec -> CapabilitySpec -> ActionSpec -> ArgumentSpec / ReturnSpec
```

Descriptors include:

- stable id and label;
- capability and canonical method;
- argument dtype, required/default, unit, range, choices, reference support, and description;
- return data kind/unit and whether `save_as` is meaningful;
- lifecycle phase (`connect`, `configure`, `arm`, `start`, `read`, `stop`, `cleanup`);
- safety class (`read_only`, `configure_no_output`, `output`, `analog_output`, `unknown`);
- ordering requirements and provided state tokens;
- mock support and adapter-specific notes.

Explicit descriptors are authoritative. Python signature inspection may assist migration tests but must not become runtime truth. Descriptor discovery must not import vendor DLLs or connect hardware.

### 3.5 Guided authoring edits the same workflow

The Builder gains a palette and schema-generated inspector:

- structural steps: scan, average, measurement, run, wait, cleanup;
- resource actions filtered by configured resources and capabilities;
- required arguments shown first, optional arguments collapsed below;
- units, ranges, choices, references, defaults, safety, return shape, and `save_as` shown from descriptors;
- parameter reference picker lists in-scope scan/config/sequence coordinates;
- inserts produce canonical existing workflow nodes;
- YAML remains viewable and saveable;
- every edit runs incremental diagnostics;
- full Validate/Prepare provides workflow completeness diagnostics.

Recipe templates create complete editable skeletons, not opaque executor types. Examples include ASG-master pulsed readout, NI-master AI/AO, manual slow scan, ODMR, and generated Rabi.

### 3.6 Sequence detail remains outside core workflow

Qulab does not turn every pulse into a core workflow node. Sequence authoring has three guided modes:

1. Curated family: provider-declared parameters and dependencies.
2. Generic template sweep: select pulse targets and apply supported duration/start/end/gap/group transforms.
3. Standalone editor: edit a concrete/base sequence through a versioned bridge contract.

The UI presents supported operations in task order:

1. choose resource and authoring mode;
2. choose family/template/base sequence;
3. map channels and trigger/readout roles;
4. edit fixed parameters;
5. define swept parameters;
6. select pulse targets and propagation constraints where applicable;
7. preview first/current/last points and timing dependencies;
8. validate trigger/acquisition window and point count;
9. Prepare/materialize bundle;
10. inspect manifest/hash/provenance and generated workflow expansion.

Unsupported operations are not offered. Provider/template/editor errors are attached to the responsible field, pulse, channel, or constraint.

## 4. Architecture

Recommended modules:

```text
src/qulab/config/diagnostics.py
src/qulab/config/source_map.py
src/qulab/config/validation_pipeline.py
src/qulab/instruments/action_specs.py
src/qulab/instruments/action_registry.py
src/qulab/gui/config_load_model.py
src/qulab/gui/action_catalog_model.py
src/qulab/gui/workflow_composer_model.py
src/qulab/gui/historical_run_model.py
src/qulab/gui/sequence_authoring_model.py
src/qulab/storage/run_workspace.py
```

Models remain Qt-free. Qt views consume snapshots and controller APIs. Validation, descriptors, historical reconstruction, and sequence-plan editing must be testable without Qt, hardware, vendor SDKs, or a display.

## 5. Validation and Completeness

Minimum checks include:

- malformed YAML, duplicate keys, invalid top-level types;
- unknown step type and multiple step kinds in one node;
- invalid/missing scan values, empty scans, nonpositive averages/timeouts;
- missing resource/adapter/capability/action;
- unknown/missing/incorrectly typed action arguments;
- invalid units/ranges/choices and unresolved `${...}` references;
- `save_as` missing on data-producing actions when data would otherwise be discarded;
- duplicate/colliding data keys;
- configure/arm/start/read/stop lifecycle completeness;
- output actions outside safety authorization;
- missing cleanup for started/output-enabled resources;
- sync source/target resource and terminal validation;
- ASG/NI order and acquisition-window checks already available in sync/preflight;
- sequence provider/parameter/target/constraint/bundle validation;
- analysis input/output dependency validation.

Ordering diagnostics should distinguish definite errors from recommended warnings. Not every adapter requires the same lifecycle; rules come from ActionSpecs and sync contracts, not method-name guessing.

## 6. Historical Fidelity Levels

The historical workspace reports fidelity per category:

- `recorded`: exact artifact/config/event/snapshot is present;
- `reconstructed`: deterministically rebuilt from recorded events/config;
- `partial`: some required records are absent;
- `unavailable`: state was never recorded;
- `mismatch`: artifact hash or schema compatibility check failed.

The phrase “restore现场” means restoring the recorded software workspace and timeline. It does not mean forcing instruments back to old outputs. Hardware state restoration is explicitly out of scope and unsafe.

## 7. GUI Responsibilities

### Load diagnostics

- Show a summary banner with error/warning counts and candidate path.
- Show diagnostic table with severity, code, location, message, hint.
- Selecting an issue highlights the corresponding workflow node/field; syntax issues show line/column and a short source excerpt.
- Keep previous valid active config until candidate activation succeeds.
- Never show a successful-loaded status when activation failed.

### Historical workspace

- Open from Data Viewer run selector or a dedicated History action.
- Visibly mark the whole workspace `Historical / Read-only`.
- Keep Data Viewer integrated rather than duplicating storage rendering.
- Timeline replay has play/pause/step/speed and never emits hardware actions.
- Clone is explicit and produces a new draft with diagnostics.

### Guided workflow

- Resource/action palette is searchable and capability-filtered.
- Forms are generated from schemas and use suitable controls.
- Required fields and safety are visible before insertion.
- Structural and lifecycle diagnostics update after each edit.
- Advanced raw YAML remains available, but routine work does not require it.

### Guided sequence

- Curated and generic modes consume provider descriptors.
- Standalone editor bridge reports version, supported operations, validation, dirty state, and save result.
- Timeline/channel/pulse preview is read-only until an explicit editor action.
- Prepare remains the only full materialization boundary.

## 8. Implementation Order

1. **P11.1 Transactional Config Load and Diagnostics**: common diagnostic model, source locations, candidate validation, Qt feedback.
2. **P11.2 Historical Run Workspace and Event Replay**: read-only reconstruction and clone-to-draft.
3. **P11.3A Capability Action Schema Registry**: import-safe adapter/action metadata and validators.
4. **P11.3B Guided Workflow Composer**: palette, generated forms, completeness checks, recipes.
5. **P11.3C Guided Sequence Authoring and Feedback**: curated/generic/editor modes, ordered operation catalog, inline timing/target feedback.

P11.2 can proceed after the P11.1 diagnostic contract stabilizes. P11.3A can run in parallel with P11.2 if shared GUI/controller files are avoided. P11.3B depends on P11.1 and P11.3A. P11.3C depends on P11.3A/P11.3B and the completed P9.3 sequence-generation contracts.

## 9. Non-goals

- no automatic hardware state restoration from history;
- no vendor SDK reflection in the GUI;
- no second workflow execution engine;
- no pulse-level nodes in core workflow;
- no hidden fallback from invalid hardware config to simulation;
- no automatic correction that silently changes experimental meaning;
- no requirement that old runs contain information that was never recorded.

## 10. Completion Criteria

P11 is complete when:

- invalid files cannot appear successfully activated and diagnostics identify actionable locations;
- valid files receive offline validation on load without hardware access;
- historical runs open as coherent read-only workspaces with fidelity reporting and event replay;
- cloning a historical run creates a safe new draft without mutating the original;
- adapter actions and sequence provider functions are discoverable through import-safe schemas;
- a user can compose a representative Rabi/ODMR/NI acquisition workflow without memorizing method or argument names;
- the composer identifies missing required steps and unsafe ordering before Start;
- sequence authoring exposes supported operations in order, validates targets/timing, and previews representative points;
- all generated YAML remains CLI-compatible and passes the same validation pipeline.
