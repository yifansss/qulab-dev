import json
from pathlib import Path

from qulab.storage import RunStore


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
