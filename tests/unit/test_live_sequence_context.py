from qulab.core import ErrorRaised, SequenceSelected
from qulab.gui import SequenceContextModel


def test_sequence_selected_context_and_failure_stale_clear():
    model = SequenceContextModel()
    event = SequenceSelected(point_id="p1", bundle_id="rabi", entry_id="tau_1", requested_coordinates={"tau": 1},
                             entry_coordinates={"tau": 1}, manifest_sha256="a" * 64, sequence_sha256="b" * 64,
                             metadata={"plan_id": "main", "family": "rabi"})
    model.handle_event(event)
    assert model.current().mode == "Curated Family"
    assert model.for_point("p1").entry_id == "tau_1"
    model.handle_event(ErrorRaised(error_type="SequenceSelectionError", message="sequence missing"))
    assert model.current().status == "error" and model.current().entry_id is None


def test_old_single_file_snapshot_does_not_fake_bundle():
    model = SequenceContextModel({"sequence_file": "one.seq"})
    assert model.current().mode == "Single File" and model.current().bundle_id is None
