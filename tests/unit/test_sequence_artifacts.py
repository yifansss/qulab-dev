import json
from pathlib import Path

from qulab.storage import RunStore
from qulab.config import parse_experiment_config
from qulab.gui.controller import _bind_frozen_sequence_artifacts


def test_run_store_copies_all_sequence_files_as_artifacts(tmp_path: Path) -> None:
    resource_sequence = tmp_path / "resource_sequence.json"
    point_sequence = tmp_path / "point_sequence.json"
    resource_sequence.write_text('[{"channel_name": "Channel 1", "pulses": []}]', encoding="utf-8")
    point_sequence.write_text('[{"channel_name": "Channel 2", "pulses": []}]', encoding="utf-8")
    config = {
        "name": "sequence_artifact_test",
        "resources": {
            "asg": {
                "adapter": "mock_asg",
                "capabilities": ["pulse_sequencer"],
                "sequence_file": str(resource_sequence),
            }
        },
        "setup": [
            {"call": "asg.load_sequence", "args": {"sequence_file": str(point_sequence)}},
        ],
        "procedure": [],
        "cleanup": [],
    }

    store = RunStore(root=tmp_path / "runs", experiment_name="sequence_artifact_test", config=config)
    store.open()
    store.close()

    metadata = json.loads((store.run_path / "metadata.json").read_text(encoding="utf-8"))
    snapshots = metadata["sequence_snapshots"]

    assert len(snapshots) == 2
    assert {snapshot["source_path"] for snapshot in snapshots} == {str(resource_sequence), str(point_sequence)}
    for snapshot in snapshots:
        assert snapshot["sha256"]
        assert snapshot["artifact_path"]
        copied = store.run_path / snapshot["artifact_path"]
        assert copied.exists()
        assert copied.read_text(encoding="utf-8") in {
            resource_sequence.read_text(encoding="utf-8"),
            point_sequence.read_text(encoding="utf-8"),
        }


def test_runtime_load_is_rebound_to_archived_sequence_bytes(tmp_path: Path) -> None:
    sequence = tmp_path / "live.json"
    original = '[{"channel_name":"Trigger","pbn":0,"pulses":[]}]\n'
    sequence.write_text(original, encoding="utf-8")
    config = {
        "name": "frozen",
        "resources": {"asg": {"adapter": "mock_asg", "sequence_file": str(sequence)}},
        "setup": [{"call": "asg.load_sequence", "args": {"sequence_file": str(sequence)}}],
        "procedure": [],
        "cleanup": [],
    }
    parsed = parse_experiment_config(config)
    store = RunStore(root=tmp_path / "runs", experiment_name="frozen", config=config)
    store.open()
    sequence.write_text('[{"channel_name":"Changed","pbn":1,"pulses":[]}]\n', encoding="utf-8")

    _bind_frozen_sequence_artifacts(parsed, store)

    frozen_path = Path(parsed.procedure.setup[0].kwargs["sequence_file"])
    assert frozen_path.read_text(encoding="utf-8") == original
    assert parsed.context.resources["asg"].sequence_file == str(frozen_path)
    store.close()
