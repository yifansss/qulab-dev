# P11 Authoring, Diagnostics, and Historical Workspace

## Transactional Load

`qulab.config.validate_config_candidate(path)` performs decode, structural,
reference/action-schema, and offline preflight checks. It returns a
`ConfigLoadResult`; it never connects an adapter, creates a run folder, starts
an output, or publishes hardware events.

`OperatorController.load_config()` activates only an error-free result.
Warnings remain visible. A blocked candidate remains available as
`last_candidate_result`, while `config`, `config_path`, parsed state, and live
models continue to refer to the last valid active experiment. Prepare reruns
the canonical parser/preparation path; Start fails closed on preflight errors.

Diagnostics contain stable severity/code/message fields, config and workflow
paths, YAML node-mark line/column, optional excerpt/hint, and related paths.
Generated paths without a direct YAML node use the closest authoring parent.

## Historical Runs

`HistoricalRunWorkspace.open(path)` validates a Qulab run and reports fidelity
for config, resolved config, resources, sync, sequence, analysis, events,
points, data, and logs. Values are `recorded`, `reconstructed`, `partial`,
`unavailable`, or `mismatch`. Missing old-run files do not prevent other
sections from opening. JSONL events are streamed and malformed lines are
isolated with their line/index.

Replay supports step, seek-by-index, reset, pause, and 0.25x/1x/4x/max modes.
It feeds dedicated historical presentation models and never publishes to the
hardware EventBus or writes RunStore. Time-based seek is not currently
provided. Unrecorded live-only derived values and physical instrument state
remain unavailable.

Clone writes a new draft from recorded `config.yaml` (or explicit resolved
snapshot choice), records only the source run id, resets output/physical
verification gates, and validates the draft transactionally. It never modifies
the source run. Hardware state is not restored.

## Action Schema Registry

`qulab.instruments.DEFAULT_ACTION_REGISTRY` exposes import-safe `AdapterSpec`,
`ActionSpec`, `ArgumentSpec`, and `ReturnSpec` models. Queries include
`list_adapters`, `describe_adapter`, `list_actions`, and `resolve_action`.
`validate_action_call` checks required/unknown arguments, literal types,
ranges, choices, and references. `to_json()` and
`render_action_catalog_markdown()` are deterministic. Descriptor discovery
does not instantiate adapters or import vendor drivers.

The registry covers microwave configure/output actions; pulse sequence
load/parameter/compile/trigger/arm/start/stop actions; DAQ counter and analog
configure/arm/read/stop actions; analog output; and AWG upload/play/stop.
Actions backed by intentionally open vendor keyword mappings are explicitly
marked schema-incomplete (`allow_unknown_arguments`) and retain unknown-risk
semantics.

## Workflow Composer

`WorkflowComposerModel` edits the same canonical config mapping used by raw
YAML, Operator Parameters, and Sequence Sweep. It provides a resource and
capability-filtered palette, schema form conversion, insert/duplicate/delete/
move/wrap, scoped reference discovery and scan rename preview, undo/redo, and
prepared-state invalidation.

Completeness checks use ActionSpec state requirements/provisions rather than
method-name guesses. Current checks include undeclared resources, lifecycle
requirements, output authorization, unsaved data-producing returns, duplicate
save keys, and missing cleanup. Recipes are ordinary editable YAML mappings:
mock scalar scan, NI manual AO/AI, NI-master AO/AI, ASG TTL scope, ASG-master NI
trace, generated Rabi, and low-power ODMR.

## Sequence Authoring

`SequenceAuthoringModel` presents nine ordered steps for three modes while
writing only `sequence_plans`:

1. resource and mode;
2. family/template/source;
3. channel and trigger roles;
4. fixed parameters;
5. sweep parameters;
6. targets and propagation;
7. preview and compare;
8. validation and Prepare;
9. bundle/workflow/provenance.

Curated fields come directly from `SequenceFamilySpec`. Generic operations are
limited to the implemented transform engine: start, duration, end, shift,
gap-after, shift-after, shift-group, and anchor. First/current/last previews are
deterministic. Plan edits invalidate prepared hashes and can insert the
canonical `sequence_sweep` macro.

The standalone editor bridge emits protocol version 1 with capabilities,
source, dirty state, validation, summary, and saved artifact path/hash. Logs go
to stderr and stdout contains only the JSON protocol. Missing editor/runtime,
invalid JSON, version mismatch, timeout, process error, and saved-file hash
mismatch are friendly fail-closed results.

### P11.3C GUI integration

The existing and only Control / Sequence Sweep tab now hosts a guided Qt view
backed by a Qt-free presenter snapshot. Its nine steps use the model's ordered
status, provider field descriptors, point estimate, located issues, revision,
and prepared state. The widget writes through stable `OperatorController`
commands, so Operator Parameters, Builder Workflow, YAML save, Prepare, Live
Run context, and historical provenance continue to observe one config mapping.

Curated mode exposes provider-defined fixed and sweep fields. Generic mode adds
template inspection, channel/pulse selection, transform and propagation
catalogs, group and anchor controls, and normalized first/current/last timeline
previews with overlay/difference. Standalone mode launches the external editor
off the UI thread and accepts only a protocol-reported artifact whose SHA-256
matches the saved file. Preview and validation never materialize a bundle or
touch hardware; explicit Prepare runs off the UI thread and discards a result
if the plan revision changed while it was building.

## Known Limits

- Historical replay cannot reconstruct facts that were never recorded.
- Historical software reconstruction never restores hardware outputs.
- Generated/offline diagnostics sometimes locate the nearest authoring parent
  rather than a generated node.
- GUI rendering remains provider/model-driven; pulse-level nodes are not part
  of the core workflow executor.
- Physical cable correctness remains a bench-verification warning.
