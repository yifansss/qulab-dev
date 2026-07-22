from pathlib import Path

from qulab.core import DataPoint, SequenceSelected
from qulab.gui.controller import OperatorController
from qulab.storage import HistoricalRunWorkspace

ROOT = Path(__file__).resolve().parents[2]


def test_guided_curated_rabi_prepare_run_and_provenance(tmp_path: Path) -> None:
    controller = OperatorController(tmp_path / "runs")
    assert controller.load_config(ROOT / "configs/experiments/dry_run_rabi_sequence_family.yaml").activated
    controller.update_sequence_plan_parameter("rabi", "tau_s", {
        "mode": "linspace", "start": 20e-9, "stop": 60e-9, "points": 3, "unit": "s",
    })
    previews = controller.get_sequence_previews("rabi", 1)
    assert all(item.pulses for item in previews)
    revision = controller.get_guided_sequence_state("rabi").revision
    controller.prepare_sequence_plan("rabi", expected_revision=revision)
    provenance = controller.get_sequence_provenance("rabi")
    assert provenance and provenance["point_count"] == 3
    events = []
    result = controller.start_dry_run(events.append)
    selected = [item for item in events if isinstance(item, SequenceSelected)]
    points = [item for item in events if isinstance(item, DataPoint)]
    assert len(selected) == len(points) == 3
    assert {item.coords["tau_s"] for item in selected} == {20e-9, 40e-9, 60e-9}
    historical = HistoricalRunWorkspace.open(result.run_path)
    assert historical.metadata["sequence_generation"][0]["manifest_sha256"] == provenance["manifest_sha256"]


def test_guided_generic_target_constraint_prepare_and_run(tmp_path: Path) -> None:
    controller = OperatorController(tmp_path / "runs")
    assert controller.load_config(ROOT / "configs/experiments/dry_run_generic_asg_template_sweep.yaml").activated
    model = controller.sequence_authoring(); model.inspect_generic_template("generic_rabi")
    controller.update_sequence_target_transform(
        "generic_rabi", "mw_pulse", "Channel 1", 0, parameter="tau_s",
        property_name="duration", propagation="shift_after", scope="all_channels",
    )
    controller.add_sequence_anchor("generic_rabi", "readout_gate.end", "mw_pulse.end", 5e-6)
    first, _, last = controller.get_sequence_previews("generic_rabi")
    assert first.pulses != last.pulses
    revision = controller.get_guided_sequence_state("generic_rabi").revision
    controller.prepare_sequence_plan("generic_rabi", expected_revision=revision)
    events = []
    controller.start_dry_run(events.append)
    assert len([item for item in events if isinstance(item, SequenceSelected)]) == 4
