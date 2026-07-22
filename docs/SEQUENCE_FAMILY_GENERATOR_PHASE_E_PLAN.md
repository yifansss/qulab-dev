# Sequence Family and Sweep Generator - Phase E Plan

Status: planned. P9.1 and P9.2 are implemented; this document defines the next
sequence-generation and GUI integration phase.

## 1. Problem Statement

P9.1 and P9.2 provide a reliable execution substrate:

```text
manifest -> validated bundle -> workflow point -> concrete sequence
         -> ASG load -> SequenceSelected -> RunStore provenance
```

The current authoring path is still too manual. Changing a Rabi `tau_s` range
can require editing a generator script, running it, writing or updating a
manifest, declaring the bundle in the experiment YAML, and manually keeping the
workflow scan values consistent with the generated entries. This duplicates
the same information across several files and makes data provenance depend on
the operator remembering every step.

The desired Phase E experience is:

1. Select a sequence family or a generic sequence template in the GUI.
2. See its fixed and scannable parameters with labels, units, ranges, and
   validation.
3. Choose fixed, linspace, range, explicit, or later table-based values.
4. For a generic template, select one or more pulse properties and define how
   dependent pulses move.
5. Press Prepare.
6. Qulab generates concrete files and the manifest, expands the canonical
   workflow scan, validates the resulting bundle, and records the full plan.
7. Hardware connection/output remains blocked until generation and preflight
   succeed.

Users must not need to hand-write generated sequence files, manifest entries,
`sequence_bundles` declarations, or repetitive bundle-load workflow actions for
normal use.

## 2. Architecture Decision

Phase E is not only an optional Python hook. It is a structured authoring and
preparation layer built on top of P9.1/P9.2:

```text
Sequence Family Provider       Generic Template Sweep Provider
          |                                |
          +---------- describe() ----------+
                          |
                   SequenceFamilySpec
                          |
GUI Sequence Sweep <-> SequenceSweepPlan in experiment config
                          |
                  Prepare Compiler
          +---------------+----------------+
          |                                |
  canonical workflow scans        generated bundle + manifest
          |                                |
          +----------- P9.1/P9.2 -----------+
                          |
                preflight / run / storage
```

The existing bundle loader, resolver, runtime event, preflight, and RunStore
remain authoritative. Phase E produces valid inputs for them; it does not
replace them.

## 3. Three Authoring Modes

### 3.1 Curated Sequence Family

Recommended for routine experiments such as Rabi, Ramsey, Hahn echo, pulsed
ODMR, and readout calibration.

A family provider declares meaningful parameters instead of exposing file
internals:

```text
Rabi
  laser_init_s
  mw_delay_s
  tau_s
  readout_delay_s
  readout_s
  trigger_delay_s
```

The provider owns the mapping from these parameters to the ASG format and any
experiment-specific timing constraints. The operator edits values and sweep
ranges; they do not edit Python source.

Curated families are presets over the same generator contract. They must not
create a second execution path.

### 3.2 Generic Template Sweep

Recommended when a user already has a concrete ASG sequence and wants MATLAB
`SweepSEQ`-like control without writing a new generator.

The operator selects:

- template sequence file;
- target channel and pulse;
- target property, such as start, duration, end, gap, repeat count, or spacing;
- parameter name and unit;
- sweep values;
- propagation/constraint policy for dependent pulses.

The generic provider parses and modifies the ASG format. This format-specific
logic is a provider/plugin responsibility, not a Qulab core pulse model.

### 3.3 Existing Concrete Bundle

P9.1/P9.2 remain available as an expert/fallback mode. A user may load a bundle
created by an external tool without using Phase E generation.

This is important for migration, vendor tools, and experiments whose sequence
compiler cannot yet be represented by a Qulab provider.

## 4. Core Concepts

### 4.1 SequenceFamilySpec

`SequenceFamilySpec` is a read-only description returned by a trusted provider.
It drives validation and GUI construction.

Recommended fields:

```python
@dataclass(frozen=True)
class SequenceFamilySpec:
    id: str
    version: str
    label: str
    description: str | None
    resource_capability: str
    output_format: str
    parameters: tuple[SequenceParameterSpec, ...]
    supports_preview: bool
    source_identity: SourceIdentity
```

Each parameter spec should include:

```python
@dataclass(frozen=True)
class SequenceParameterSpec:
    name: str
    label: str
    dtype: str
    unit: str | None
    default: object
    minimum: float | None
    maximum: float | None
    choices: tuple[object, ...] | None
    sweepable: bool
    role: str
    safety_class: str
```

Parameter names use snake_case and canonical SI units. Conversion to ASG
microseconds or vendor-specific values happens inside the provider.

### 4.2 SequenceSweepPlan

The experiment config stores one source-of-truth plan. It references a provider
and contains parameter values, scan definitions, resource binding, and optional
template transforms.

The plan is authoring state, not a generated manifest. It must be editable by
GUI and CLI and fully serializable to YAML.

### 4.3 GeneratedSequencePoint

The provider receives one complete, validated parameter mapping and returns one
concrete sequence artifact plus metadata:

```python
@dataclass(frozen=True)
class GeneratedSequencePoint:
    sequence_bytes: bytes
    extension: str
    metadata: Mapping[str, Any]
```

The provider does not write the bundle manifest. The framework owns entry IDs,
file naming, hashes, coordinate indexing, manifest serialization, atomic output,
and P9.1 validation. This prevents every user generator from reimplementing the
same packaging rules.

### 4.4 Generator Provider Contract

Recommended minimum protocol:

```python
class SequenceGeneratorProvider(Protocol):
    def describe(self) -> SequenceFamilySpec: ...

    def validate_plan(
        self,
        plan: SequenceSweepPlan,
    ) -> SequencePlanValidationResult: ...

    def generate_point(
        self,
        parameters: Mapping[str, Any],
        *,
        template: Path | None,
    ) -> GeneratedSequencePoint: ...

    def preview_point(
        self,
        parameters: Mapping[str, Any],
        *,
        template: Path | None,
    ) -> SequencePreview | None: ...
```

The framework enumerates the parameter grid and calls `generate_point()` for
each unique coordinate. A later optimized `generate_bundle()` method may be
added, but it must return the same typed results and may not bypass framework
hashing or validation.

## 5. Planned Config Schema

The recommended top-level authoring schema is `sequence_plans`. Example curated
Rabi plan:

```yaml
sequence_plans:
  rabi_main:
    resource: asg
    family:
      provider: analysis_modules.sequence_generators.rabi
      version: "1"

    parameters:
      laser_init_s:
        mode: fixed
        value: 3e-6
      tau_s:
        mode: linspace
        start: 20e-9
        stop: 2e-6
        points: 101
      readout_s:
        mode: fixed
        value: 2e-6

    sampling:
      mode: cartesian
      order: [tau_s]

    materialize:
      cache: true
      max_points: 10000
```

Generic template example:

```yaml
sequence_plans:
  custom_rabi:
    resource: asg
    family:
      provider: qulab.sequence_generators.asg_template_sweep
      version: "1"
    template: configs/sequences/rabi_base.json

    targets:
      mw_pulse:
        channel: Channel 1
        pulse: 0
      readout_gate:
        channel: Channel 6
        pulse: 0

    parameters:
      tau_s:
        mode: linspace
        start: 20e-9
        stop: 2e-6
        points: 101
        transform:
          target: mw_pulse
          property: duration
          propagation:
            mode: shift_after
            scope: all_channels
            boundary: target_end

    constraints:
      - type: anchor
        target: readout_gate.start
        reference: mw_pulse.end
        offset_s: 1e-6

    sampling:
      mode: cartesian
      order: [tau_s]
```

The YAML contains no arbitrary Python expression. Pulse relationships use a
small structured schema that can be validated and represented in the GUI.

### 5.1 Parameter Modes

Phase E must support:

- `fixed`: one value;
- `linspace`: `start`, `stop`, `points`;
- `range`: `start`, `stop`, `step`;
- `explicit`: ordered `values` list.

For multiple swept parameters, initial sampling is Cartesian product with an
explicit loop order. `zip` and explicit coordinate-table sampling are useful
follow-ups, but must not be silently emulated by Cartesian product.

### 5.2 Experiment Parameter Identity

Sequence plan parameters must become ordinary experiment parameters and point
coordinates. The default exported name is the parameter name, for example
`tau_s`. An optional `expose_as` supports namespacing when two plans use the
same internal name.

Name collisions must be detected during Prepare. Qulab must not silently merge
two parameters that have different units, values, or meanings.

These coordinates may also be referenced by ordinary workflow calls:

```yaml
args:
  delay_s: "${tau_s}"
```

This allows a sequence parameter and another instrument setting to share one
scan axis without duplicate scan definitions.

## 6. Authoring Macro and Workflow Compilation

Phase E adds an authoring macro, not a new executor loop:

```yaml
procedure:
  - sequence_sweep:
      plan: rabi_main
      body:
        - measurement:
            name: rabi_point
            body:
              - call: daq.configure_ai_external_trigger
                args: {...}
              - run:
                  name: pulse_readout
                  steps: [...]
```

Before the existing parser builds the `Procedure`, a preparation/compiler layer
expands this to canonical existing nodes:

```yaml
- scan:
    name: tau_s
    values: {start: 20e-9, stop: 2e-6, points: 101}
    body:
      - measurement:
          name: rabi_point
          body:
            - call: asg.load_sequence_from_bundle
              args:
                bundle: generated_rabi_main
                coordinates: {tau_s: "${tau_s}"}
            - call: daq.configure_ai_external_trigger
              args: {...}
            - run: {...}
```

For N dimensions, the compiler creates deterministic nested scan nodes in
`sampling.order`. The existing executor remains unchanged.

The authoring config and expanded config have separate identities:

- `config.yaml`: user-facing `sequence_plans` and `sequence_sweep` macro;
- `resolved_config.yaml`: generated `sequence_bundles` declaration and fully
  expanded canonical workflow;
- `sequence_plan.yaml`: frozen normalized plan used for generation.

The GUI modifies the authoring plan. Builder Workflow can show either the macro
or a read-only preview of the expanded nodes; it must not require the user to
maintain both forms.

## 7. Generic Pulse Transform Model

The generic provider should offer the useful parts of the previous MATLAB
`SweepSEQ` model while making dependencies explicit and deterministic.

### 7.1 Stable Pulse Targets

Raw `(channel index, pulse index)` is supported for compatibility but is fragile
when the template changes. Preferred targets use aliases stored in the plan or
an editor sidecar:

```yaml
targets:
  mw_pulse: {channel: Channel 1, pulse: 0}
  readout_gate: {channel: Channel 6, pulse: 0}
```

The target record should include a template fingerprint. If the selected pulse
no longer matches after the template is edited, Prepare must report a target
stale/ambiguous error instead of modifying another pulse.

Future editor versions may maintain persistent pulse IDs in an editor sidecar.
Do not require vendor drivers to accept Qulab-only ID fields in concrete output.

### 7.2 Direct Transform Operations

Initial generic operations:

- `set_start`;
- `set_duration`;
- `set_end`;
- `shift`;
- `set_gap_after`;
- format-supported repeat count or pulse spacing.

The ASG JSON provider maps these semantic operations to fields such as
`start_time`, `time_on`, `rise`, and `d`. Units at the framework boundary are
SI; provider conversion is explicit and tested.

### 7.3 Propagation Policies

Simple, GUI-friendly policies:

- `none`: only change the target;
- `shift_after / same_channel`: shift later pulses on the same channel by the
  target edge delta;
- `shift_after / all_channels`: shift all later pulses by that delta;
- `shift_group`: shift pulses in an explicitly named group;
- `constraints`: recompute dependent pulse positions from anchors.

The delta is based on the changed target boundary, not blindly on the parameter
delta. For example, increasing a pulse end by 20 ns shifts followers by 20 ns.

### 7.4 Anchor Constraints

Anchor constraints are more robust than a long sequence of imperative shifts:

```text
readout_gate.start = mw_pulse.end + 1 us
trigger.start      = readout_gate.start - 200 ns
```

YAML represents these as structured target/reference/offset fields. The engine
builds a dependency graph, rejects cycles and multiple writers, evaluates in
topological order, and reports the exact conflicting targets.

### 7.5 Determinism Rule

Every bundle point is generated from an immutable base template:

```text
base template + complete point parameters -> concrete sequence
```

Point N must never be produced by mutating point N-1. This prevents cumulative
floating-point drift, order-dependent pulse shifts, and bundle differences when
scan order changes.

Generation order:

1. Clone immutable template.
2. Apply independent direct transforms.
3. Apply propagation/anchor graph.
4. Validate duration, non-negative timing, overlap policy, channel limits, and
   provider-specific constraints.
5. Serialize concrete vendor sequence.
6. Compute metadata and return bytes to the framework packager.

If two parameters write the same pulse property, validation fails unless the
provider explicitly defines a composition rule.

## 8. Prepare and Materialization Lifecycle

Prepare becomes a two-stage, hardware-free process:

```text
Stage 1: authoring validation
  schema -> provider discovery -> parameter/unit validation -> grid estimate

Stage 2: materialization
  generate points -> framework writes bundle -> P9.1 load/hash/coverage
  -> P9.2 trigger/window preflight -> freeze resolved config

Only after both stages pass:
  hardware connect/authorize/configure/arm/start
```

Generator failure, timeout, invalid output, missing coverage, or stale template
must prevent hardware connection/output.

### 8.1 Output and Cache

Generated bundles should not be written into `configs/` by default. Use an
immutable project-local cache/staging area such as:

```text
.qulab/cache/sequence_bundles/<plan_id>/<plan_hash>/
```

`plan_hash` includes:

- normalized plan;
- provider id/version/source hash;
- template bytes hash;
- parameter values and sampling order;
- Qulab generator schema version.

Generate into a temporary sibling directory, validate it, then atomically
rename to the final cache path. Never expose a partially generated bundle.

At run creation, existing RunStore copies the manifest and every selected
unique sequence into the run artifacts. The cache is an optimization, not the
provenance authority.

GUI must show estimated point count and block materialization above
`max_points` unless the operator explicitly increases the plan limit. A later
disk-size estimate can use preview point size times point count.

### 8.2 Provider Execution

Project-local providers are trusted experiment code but should run in a helper
process for GUI stability, timeout handling, and stdout/stderr capture. This is
process isolation, not a security sandbox.

Provider rules:

- import-safe discovery; `describe()` must not connect hardware;
- no vendor SDK import required for description/preview unless explicitly
  optional and handled cleanly;
- write access restricted by contract to the assigned staging directory;
- no ASG/NI/MW connection or output;
- deterministic output for the same plan hash;
- clear timeout and cancellation behavior;
- source identity and captured diagnostics returned to the parent process.

## 9. GUI Integration

Add `Sequence Sweep` as a submode inside the existing `Control` page:

```text
[ Operator Parameters ] [ Sequence Sweep ] [ Builder Workflow ] [ Direct Control ]
```

It is not a second application. All submodes edit the same authoring config
model.

### 9.1 Main Layout

The Sequence Sweep submode should contain:

```text
Family / Template
  provider selector | template file | Open Editor | refresh

Parameters
  name | mode | value/range | unit | points | validation

Targets and Timing Links (advanced)
  parameter | target pulse | property | propagation | dependency summary

Preview and Build
  current coordinate selector | timing preview | first/current/last
  point count | cache/build status | manifest/hash | preflight issues
```

Controls use number inputs, mode selectors, file pickers, tables, checkboxes,
and icons consistent with the existing GUI. Units must be visible. Large
free-form YAML or Python text is not the normal operator surface.

### 9.2 Easy and Advanced Views

Curated family mode shows only provider-declared experiment parameters and a
read-only timing/dependency summary.

Generic template mode adds an advanced target/link editor. Pulse selection can
come from the Qulab-native sequence preview. Opening the standalone editor still
edits the base template; when it is saved, Qulab invalidates the old plan hash,
refreshes targets, and requires Prepare again.

### 9.3 Preview

Preview must not materialize the full bundle on every field change. Generate or
render only selected representative points:

- first;
- current point selected by axis sliders/inputs;
- last;
- optional comparison overlay.

Full materialization occurs on explicit Prepare. Preview errors appear next to
the responsible parameter/target and do not connect hardware.

### 9.4 Synchronization with Other GUI Views

- Editing a sequence plan updates Operator Parameters values.
- Operator Parameters may expose selected plan values, but Sequence Sweep owns
  sequence-specific mode/target/link editing.
- Builder Workflow shows the `sequence_sweep` macro and a generated read-only
  expansion preview.
- Saving YAML preserves the authoring plan, not a second independently editable
  generated workflow.
- Preflight shows plan validation, materialization, bundle coverage, trigger,
  and acquisition-window issues in one issue table.

## 10. Parameter and Data Provenance

Sequence parameters must be first-class experiment metadata and point coords,
not merely generator arguments hidden inside a manifest.

RunStore should add:

```text
artifacts/sequence_generation/<plan_id>/sequence_plan.yaml
artifacts/sequence_generation/<plan_id>/provider_source_or_identity.json
artifacts/sequence_generation/<plan_id>/generation_log.txt
artifacts/sequences/<bundle_id>/manifest.yaml
sequence_selections.jsonl
```

`metadata.json` should record a compact summary:

```json
{
  "experiment_parameters": {
    "tau_s": {
      "label": "MW pulse duration",
      "unit": "s",
      "mode": "linspace",
      "role": "sequence_coordinate",
      "plan": "rabi_main"
    }
  },
  "sequence_generation": [
    {
      "plan_id": "rabi_main",
      "plan_hash": "...",
      "provider": "analysis_modules.sequence_generators.rabi",
      "provider_version": "1",
      "provider_source_hash": "...",
      "template_sha256": "...",
      "bundle_id": "generated_rabi_main",
      "manifest_sha256": "...",
      "point_count": 101,
      "cache_hit": false,
      "status": "generated"
    }
  ]
}
```

The full normalized parameter values and sweep definitions live in
`sequence_plan.yaml` and `resolved_config.yaml`; large grids do not need to be
duplicated in `metadata.json`.

Each measured `DataPoint.coords` already includes active scan values. Therefore
`tau_s`, multi-dimensional sequence coordinates, and ordinary instrument scan
coordinates naturally align with raw and derived data. `SequenceSelected`
continues to prove which concrete file was used at that point.

Generation provenance must include failed attempts when a run directory exists;
before run creation, GUI/CLI preparation logs may be kept in the preparation
result and copied when the run starts.

## 11. Validation and Failure Policy

Stable issue codes should cover at least:

- `sequence_provider_not_found`;
- `sequence_provider_import_failed`;
- `sequence_provider_version_mismatch`;
- `sequence_parameter_unknown`;
- `sequence_parameter_missing`;
- `sequence_parameter_unit_invalid`;
- `sequence_sweep_empty`;
- `sequence_sweep_too_large`;
- `sequence_target_missing`;
- `sequence_target_ambiguous`;
- `sequence_target_stale`;
- `sequence_transform_conflict`;
- `sequence_constraint_cycle`;
- `sequence_timing_invalid`;
- `sequence_generation_timeout`;
- `sequence_generation_failed`;
- `sequence_output_invalid`;
- `sequence_plan_name_collision`.

Prepare fails closed for provider errors, invalid timing, incomplete generation,
hash mismatch, or bundle coverage gaps. Optional preview metadata may warn, but
missing concrete output never falls back silently to an old bundle.

## 12. Framework Modules

Recommended implementation boundaries:

```text
src/qulab/sequence_generation/
  __init__.py
  models.py            # specs, plans, normalized values, results
  registry.py          # explicit provider discovery/import
  sampling.py          # fixed/linspace/range/explicit enumeration
  compiler.py          # sequence_sweep -> canonical workflow/config
  materializer.py      # point generation, manifest packaging, atomic cache
  preparation.py       # two-stage validation/materialization orchestration
  worker.py            # optional helper-process JSON protocol
  providers/
    asg_template.py    # built-in generic ASG template sweep provider
    transforms.py      # format-specific target/constraint engine

src/qulab/gui/
  sequence_sweep_model.py
  sequence_sweep_view.py
```

Project-local curated providers:

```text
analysis_modules/sequence_generators/
  rabi.py
  ramsey.py
  hahn_echo.py
```

Project-local providers use the public protocol and may reuse the built-in ASG
template transform utilities. They must not import GUI code.

The pure model, sampling, transform, and compiler layers must be testable with
no Qt, no hardware SDK, and no display.

## 13. Implementation Stages

### Phase E1: Contracts, Schema, and Sampling

- Add typed provider/family/parameter/plan models.
- Parse optional `sequence_plans` and `sequence_sweep` authoring macro.
- Implement fixed/linspace/range/explicit normalization and Cartesian order.
- Add provider registry with explicit import errors and source identity.
- Validate name/unit/range/collision/max-point rules.

Acceptance:

- A Rabi plan can change `tau_s` start/stop/points without editing Python.
- No hardware and no GUI are needed for tests.
- Old concrete bundle configs remain unchanged.

### Phase E2: Materializer and Prepare Compiler

- Implement provider point contract.
- Generate concrete files in atomic cache staging.
- Let framework write hashes, entries, coordinates, metadata, and manifest.
- Load the generated result through P9.1.
- Expand `sequence_sweep` to existing scan/load workflow nodes.
- Run P9.2 preflight before hardware connection.
- Add normalized plan and generator provenance to RunStore inputs.

Acceptance:

- One authoring config produces a runnable Rabi bundle with no handwritten
  manifest, `sequence_bundles` block, or bundle-load action.
- Changing only YAML/GUI `tau_s` values produces a new deterministic plan hash
  and correct entries.
- Failure occurs before hardware output.

### Phase E3: Generic ASG Template Sweep Provider

- Extract or implement headless ASG JSON IO/model independent of PyQt5.
- Add target aliases/fingerprints.
- Add start/duration/end/gap/shift transforms.
- Add same-channel, all-channel, named-group propagation.
- Add structured anchor dependency graph and conflict/cycle checks.
- Generate metadata used by existing trigger/window preflight.

Acceptance:

- A user can select a channel pulse duration and scan it without writing a
  custom generator.
- Multiple sequence dimensions generate a deterministic Cartesian bundle.
- Following pulses move according to the selected policy with no cumulative
  drift.

### Phase E4: Sequence Sweep GUI Submode — Implemented (mock/dry-run)

P11.3C-GUI completes the Phase E4 operator surface. The unique Sequence Sweep
tab is now a nine-step guided editor rather than the former plan table plus raw
JSON fields. It supports curated, generic-template, and standalone-editor plans;
descriptor-driven parameter forms and sampling order; structured pulse target,
propagation, group, and anchor controls; normalized timing timelines and
first/last comparison; issue-to-step navigation; revision-safe asynchronous
Prepare; and read-only bundle/workflow/RunStore provenance.

The implementation deliberately leaves pulse compilation in the existing
providers and generic transform engine. It does not add pulse workflow nodes,
resource-global sequence source state, hardware access during preview/validate,
or manifest editing. Physical route verification remains a bench task.

- Add family/template selector.
- Generate parameter controls from `SequenceFamilySpec`.
- Add target/property/propagation editor for generic mode.
- Add representative-point timing preview.
- Show point count, plan hash, cache/build status, manifest, and preflight.
- Synchronize authoring config with Operator Parameters and Builder preview.

Acceptance:

- Rabi `tau_s` range can be changed and prepared from one integrated panel.
- No generated YAML plumbing must be edited manually.
- GUI restart and saved YAML preserve the same authoring plan.

### Phase E5: Curated Families and Migration — Implemented (mock/dry-run; bench templates unverified)

- Add tested Rabi family first.
- Add Ramsey/Hahn echo only after the Rabi contract is stable.
- Provide import/conversion path from an existing concrete sequence to a generic
  template plan.
- Keep standalone editor bridge for base-template editing.
- Add bench template that materializes first, then uses the existing P9.2 ASG/NI
  sequence path.

Acceptance:

- The same provider contract serves curated and generic modes.
- Old offline generator and concrete bundle remain usable.
- Run artifacts fully reconstruct provider, plan, template, bundle, and point
  selection.

## 14. Relationship to Former Phase F

The old Phase F combined two different needs:

1. sequence-specific scan authoring needed to make generated bundles usable;
2. a universal GUI scan editor for all experiment/instrument parameters.

Phase E now includes the first need because generation without integrated scan
authoring remains operationally cumbersome. The remaining Phase F is narrower:

- unified scan authoring across MW, NI, temperature, magnet, sequence, and other
  resources;
- arbitrary nesting/reordering of heterogeneous scan dimensions;
- zipped/table/adaptive scan authoring;
- broader parameter binding visualization.

Phase E must not wait for this universal editor. It only compiles the axes owned
by one `sequence_plan` and lets its body reference those coordinates.

## 15. Non-Goals

- Qulab core does not become a universal vendor-independent pulse compiler.
- The executor does not gain a second scan engine.
- YAML does not execute arbitrary Python expressions.
- Generation never controls hardware.
- The GUI does not silently mutate an external template without saving a
  visible authoring plan.
- Phase E does not replace P9.1/P9.2 artifacts or provenance.
- Adaptive scans that generate an unknown future sequence after each measured
  result are not part of the first Phase E implementation.

## 16. Recommended Worker Decomposition

Use sequential workers, not one broad GUI/core worker:

1. P9.3A: E1 contracts/schema/sampling plus E2 materializer/compiler and a
   headless curated Rabi example. Prompt:
   `prompts/009_followup_p9_3a_sequence_generation_foundation.md`.
2. P9.3B: E3 generic ASG template transform provider with pure unit tests.
   Prompt: `prompts/009_followup_p9_3b_generic_asg_template_sweep.md`.
3. P9.3C: E4 GUI Sequence Sweep submode and preview integration.
   Prompt: `prompts/009_followup_p9_3c_sequence_sweep_gui.md`.
4. P9.3D: E5 curated family expansion, migration tools, and hardware bench
   template after the first three stages pass. Prompt:
   `prompts/009_followup_p9_3d_curated_families_migration_bench.md`.

P9.3A is the critical path. P9.3B and P9.3C must consume its public contracts
instead of creating GUI-only generator state.

## 17. Implementation Record

P9.3A–D are implemented. `prepare_sequence_config()` is the only generation
side-effect boundary; the runner and OperatorController both use it before any
hardware connection. Built-ins are `rabi` (v2), `ramsey` (v1), `hahn_echo`
(v1), and `asg_template` (v1). The immutable cache is
`.qulab/cache/sequence_bundles/<plan>/<plan_hash>` and every hit is revalidated
through the P9.1 loader and coverage check.

This status means implemented and tested with mock/dry-run resources. Bench
10–12 are templates only and have not been physically verified.
