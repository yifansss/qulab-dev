import json
from pathlib import Path

from qulab.config.runner import run_dry_config
from qulab.gui.controller import OperatorController
from qulab.sequence_bundles import load_sequence_bundle
from examples.generate_rabi_sequence_bundle import build_bundle


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "dry_run_rabi_sequence_bundle.yaml"


def test_canonical_rabi_bundle_dry_run_is_reconstructable(tmp_path: Path) -> None:
    result = run_dry_config(CONFIG, tmp_path)

    assert result.executor_state == "completed"
    selected = [event for event in result.events if event.type == "SequenceSelected"]
    assert [(event.coords["tau_s"], event.entry_id) for event in selected] == [
        (20e-9, "tau_20ns"),
        (40e-9, "tau_40ns"),
        (60e-9, "tau_60ns"),
    ]
    records = [
        json.loads(line)
        for line in (result.run_path / "sequence_selections.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 3
    for record in records:
        assert (result.run_path / record["artifact_path"]).is_file()
        assert record["point_id"]
        assert record["source_path"]
        assert record["sha256"]
    metadata = json.loads((result.run_path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["sequence_selection_count"] == 3
    assert metadata["status"] == "completed"


def test_operator_controller_can_prepare_and_run_bundle_yaml(tmp_path: Path) -> None:
    controller = OperatorController(run_root=tmp_path)
    controller.load_config(CONFIG)

    preflight = controller.prepare()
    assert preflight.ok
    events = []
    result = controller.start_dry_run(event_callback=events.append)

    assert result.status == "completed"
    assert len([event for event in events if event.type == "SequenceSelected"]) == 3
    assert (Path(result.run_path) / "sequence_selections.jsonl").is_file()


def test_offline_generator_example_produces_directly_loadable_bundle(tmp_path: Path) -> None:
    manifest = build_bundle(tmp_path / "generated_bundle", [20e-9, 40e-9, 60e-9])

    bundle = load_sequence_bundle(manifest)

    assert bundle.resolve({"tau_s": 40e-9}).entry_id == "point_0001_tau_40ns"
    assert all(entry.sha256 for entry in bundle.entries)
