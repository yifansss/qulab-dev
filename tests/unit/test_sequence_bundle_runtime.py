from pathlib import Path

import pytest

from qulab.config import load_experiment_config, parse_experiment_config
from qulab.core import ActionStep, EventBus, ExperimentContext, ExperimentExecutor, MeasurementStep, Procedure
from qulab.sequence_bundles import load_sequence_bundle
from qulab.sequence_runtime import SequenceBundleRuntimeError


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "dry_run_rabi_sequence_bundle.yaml"
MANIFEST = ROOT / "configs" / "sequences" / "examples" / "rabi_tau_bundle" / "manifest.yaml"


def test_three_point_runtime_loads_resolved_files_and_emits_selections() -> None:
    parsed = parse_experiment_config(load_experiment_config(CONFIG))
    bus = EventBus()

    ExperimentExecutor(parsed.procedure, parsed.context, bus, dry_run=True).run()

    selected = [event for event in bus.events if event.type == "SequenceSelected"]
    assert [event.entry_id for event in selected] == ["tau_20ns", "tau_40ns", "tau_60ns"]
    assert [event.point_id for event in selected] == ["p000001", "p000002", "p000003"]
    assert [event.coords["tau_s"] for event in selected] == [20e-9, 40e-9, 60e-9]
    assert parsed.context.resources["asg"].sequence_file == str(
        parsed.sequence_bundles["rabi_tau"].entries[-1].sequence_file
    )


def test_adapter_failure_emits_error_but_not_sequence_selected() -> None:
    class FailingLoader:
        def load_sequence(self, sequence_file=None):
            raise RuntimeError(f"adapter refused {sequence_file}")

    bundle = load_sequence_bundle(MANIFEST)
    context = ExperimentContext(resources={"asg": FailingLoader()}, sequence_bundles={bundle.id: bundle})
    procedure = Procedure(
        name="failure",
        body=[
            MeasurementStep(
                name="point",
                body=[
                    ActionStep(
                        name="select",
                        action="asg.load_sequence_from_bundle",
                        kwargs={"bundle": "rabi_tau", "coordinates": {"tau_s": 20e-9}},
                    )
                ],
            )
        ],
    )
    bus = EventBus()

    with pytest.raises(RuntimeError, match="adapter refused"):
        ExperimentExecutor(procedure, context, bus).run()

    assert not any(event.type == "SequenceSelected" for event in bus.events)
    assert any(event.type == "ErrorRaised" and "adapter refused" in event.message for event in bus.events)


def test_unknown_bundle_fails_before_resource_load() -> None:
    class TrackingLoader:
        called = False

        def load_sequence(self, sequence_file=None):
            self.called = True

    resource = TrackingLoader()
    context = ExperimentContext(resources={"asg": resource})
    procedure = Procedure(
        name="unknown",
        body=[
            ActionStep(
                name="select",
                action="asg.load_sequence_from_bundle",
                kwargs={"bundle": "missing", "coordinates": {"tau_s": 20e-9}},
            )
        ],
    )

    with pytest.raises(SequenceBundleRuntimeError, match="unknown sequence bundle"):
        ExperimentExecutor(procedure, context).run()
    assert resource.called is False


def test_old_direct_load_sequence_action_is_unchanged() -> None:
    class Loader:
        received = None

        def load_sequence(self, sequence_file=None):
            self.received = sequence_file
            return {"sequence_file": sequence_file}

    resource = Loader()
    procedure = Procedure(
        name="legacy",
        body=[ActionStep(name="load", action="asg.load_sequence", kwargs={"sequence_file": "legacy.json"})],
    )

    ExperimentExecutor(procedure, ExperimentContext(resources={"asg": resource})).run()
    assert resource.received == "legacy.json"
