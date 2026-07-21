import json

from qulab.core import SequenceSelected
from qulab.storage.events import event_to_jsonable


def test_sequence_selected_event_is_structured_and_json_safe() -> None:
    event = SequenceSelected(
        point_id="p000001",
        coords={"tau_s": 20e-9},
        resource="asg",
        bundle_id="rabi_tau",
        entry_id="tau_20ns",
        requested_coordinates={"tau_s": 20e-9},
        entry_coordinates={"tau_s": 20e-9},
        manifest_path="/tmp/manifest.yaml",
        manifest_sha256="a" * 64,
        sequence_file="/tmp/tau_20ns.json",
        sequence_sha256="b" * 64,
        metadata={"duration_s": 8e-6},
    )

    payload = event_to_jsonable(event)
    assert payload["type"] == "SequenceSelected"
    assert payload["point_id"] == "p000001"
    assert payload["entry_id"] == "tau_20ns"
    assert payload["sequence_sha256"] == "b" * 64
    json.dumps(payload)
