import json
from pathlib import Path

from qulab.core import SequenceSelected
from qulab.sequence_bundles import load_sequence_bundle
from qulab.storage import RunStore


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "configs" / "sequences" / "examples" / "rabi_tau_bundle" / "manifest.yaml"


def _event(bundle, point_id: str = "p000001") -> SequenceSelected:
    selection = bundle.resolve({"tau_s": 20e-9})
    return SequenceSelected(
        point_id=point_id,
        coords={"tau_s": 20e-9},
        resource="asg",
        bundle_id=bundle.id,
        entry_id=selection.entry_id,
        requested_coordinates=dict(selection.requested_coordinates),
        entry_coordinates=dict(selection.entry_coordinates),
        manifest_path=str(selection.manifest_path),
        manifest_sha256=selection.manifest_sha256,
        sequence_file=str(selection.sequence_file),
        sequence_sha256=selection.sequence_sha256,
        metadata=dict(selection.metadata),
    )


def test_runstore_copies_manifest_deduplicates_artifact_and_keeps_each_selection(tmp_path: Path) -> None:
    bundle = load_sequence_bundle(MANIFEST)
    store = RunStore(
        root=tmp_path,
        experiment_name="bundle_store",
        run_id="bundle_store",
        sequence_bundles={bundle.id: bundle},
    )
    store.open()
    store.handle_event(_event(bundle, "p000001"))
    store.handle_event(_event(bundle, "p000002"))
    store.close()

    bundle_dir = store.run_path / "artifacts" / "sequences" / "rabi_tau"
    assert (bundle_dir / "manifest.yaml").read_bytes() == MANIFEST.read_bytes()
    sequence_artifacts = list(bundle_dir.glob("tau_20ns__*.json"))
    assert len(sequence_artifacts) == 1

    selections = [
        json.loads(line)
        for line in (store.run_path / "sequence_selections.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [item["point_id"] for item in selections] == ["p000001", "p000002"]
    assert selections[0]["artifact_path"] == selections[1]["artifact_path"]
    assert selections[0]["sha256"] == bundle.entries[0].sha256

    metadata = json.loads((store.run_path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["sequence_selection_count"] == 2
    assert metadata["sequence_selection_table"] == "sequence_selections.jsonl"
    assert metadata["sequence_bundles"][0]["entry_count"] == 3
    assert metadata["sequence_bundles"][0]["coordinates"] == ["tau_s"]
