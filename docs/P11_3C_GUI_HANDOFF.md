# P11.3C Guided Sequence Qt Integration Handoff

## Result

Control has one Sequence Sweep tab. It is assembled by `pyqt_views.py`, while
the authoring rules remain Qt-free in `sequence_authoring.py` and immutable UI
snapshots live in `sequence_authoring_presenter.py`. The optional Qt widget and
timeline are isolated in `sequence_authoring_view.py`, preserving safe imports
when PySide6/PyQt6 is unavailable.

## Controller facade

The guided view uses `create_guided_sequence_plan`,
`get_guided_sequence_state`, `preview_sequence_mode_change`,
`change_sequence_mode`, `change_sequence_resource`, `update_sequence_roles`,
`update_sequence_plan_parameter`, `set_sequence_plan_sampling_order`,
`update_sequence_target_transform`, `add_sequence_anchor`,
`get_sequence_previews`, `validate_sequence_plan`,
`insert_sequence_macro`, `prepare_sequence_plan`,
`accept_sequence_editor_result`, and `get_sequence_provenance`.

Prepare records the expected authoring revision and rejects a completed build
if the plan changed while the worker was running. All mutations invalidate the
parsed/prepared view and update the shared canonical config.

## Mode matrix

| Capability | Curated | Generic template | Standalone editor |
|---|---:|---:|---:|
| Provider-driven parameters | Yes | Derived from plan | Derived from plan |
| Fixed/linspace/range/explicit | Yes | Yes | Yes |
| Template pulse inspection | Provider preview | Yes | Saved artifact |
| Structured target/propagation/anchor | Provider summary | Yes | Yes after save |
| First/current/last timeline and compare | Yes | Yes | Yes after save |
| External editor protocol | No | Optional source workflow | Yes |
| Explicit Prepare/provenance | Yes | Yes | Yes |

## Nine-step state rules

Step labels are fixed for navigation, but completion, enabled state, tooltip,
issues, point count, edited/stale/prepared state, hash, and revision come from
the presenter/model. Mode changes show retained and removed paths and require
confirmation. Invalid parameter values are rejected transactionally. External
template changes and accepted editor saves invalidate Prepare. Issue rows carry
a responsible step/field and navigate back to that step.

## Validation and evidence

Headless tests cover presenter/controller state, mode and role mutation,
transactional parameters, targets/constraints, normalized previews, issue
location, macro lifecycle, revision safety, and curated/generic dry-runs.
PySide6 offscreen interaction tests create real widgets and cover the unique
tab, nine-step state, dynamic fields, all supported parameter wiring, mode
migration, template inspection, pulse binding, issue navigation, and workflow
macro synchronization.

Screenshots are generated as non-source artifacts and are intentionally not
stored in Git. Windows experiment-computer checks (125% scaling, physical cable
routing, real editor runtime, and output safety) remain manual bench acceptance.
