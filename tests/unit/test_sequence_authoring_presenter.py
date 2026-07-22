from pathlib import Path

import pytest

from qulab.config import load_experiment_config
from qulab.gui.controller import OperatorController
from qulab.gui.sequence_authoring import AUTHORING_STEPS

ROOT = Path(__file__).resolve().parents[2]


def test_controller_guided_state_and_commands_share_config(tmp_path: Path) -> None:
    controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs/experiments/dry_run_rabi_sequence_family.yaml")
    state = controller.get_guided_sequence_state("rabi", include_previews=True)
    assert state.selected_plan == "rabi" and len(state.steps) == len(AUTHORING_STEPS)
    assert state.previews is not None and state.previews[0].pulses
    controller.update_sequence_plan_parameter("rabi", "tau_s", {"mode": "linspace", "start": 20e-9, "stop": 60e-9, "points": 3, "unit": "s"})
    updated = controller.get_guided_sequence_state("rabi")
    assert updated.point_count == 3 and updated.revision != state.revision
    assert controller.current_config["sequence_plans"]["rabi"]["parameters"]["tau_s"]["mode"] == "linspace"


def test_guided_create_macro_prepare_and_provenance(tmp_path: Path) -> None:
    path = tmp_path / "base.yaml"
    path.write_text("""name: guided\nresources:\n  asg: {adapter: mock_asg, capabilities: [pulse_sequencer, trigger_source]}\n  daq: {adapter: mock_daq, capabilities: [daq_counter, trigger_receiver]}\nprocedure: []\ncleanup: [{call: asg.stop}, {call: daq.stop}]\n""", encoding="utf-8")
    controller = OperatorController(tmp_path / "runs"); assert controller.load_config(path).activated
    controller.create_guided_sequence_plan("rabi_gui", "asg", "curated", provider="rabi")
    controller.update_sequence_plan_parameter("rabi_gui", "tau_s", {"mode": "explicit", "values": [20e-9, 40e-9, 60e-9], "unit": "s"})
    macro_path = controller.insert_sequence_macro("rabi_gui")
    assert macro_path == ("procedure", 0)
    assert controller.workflow_tree().children[1].children[0].kind == "unknown"  # macro remains authoring-only until Prepare
    revision = controller.get_guided_sequence_state("rabi_gui").revision
    view = controller.prepare_sequence_plan("rabi_gui", expected_revision=revision)
    assert view.ok
    state = controller.get_guided_sequence_state("rabi_gui")
    assert state.prepared_state == "prepared" and state.plan_hash
    provenance = controller.get_sequence_provenance("rabi_gui")
    assert provenance and provenance["point_count"] == 3 and provenance["manifest_sha256"]


def test_mode_migration_preview_and_cancel_is_non_mutating(tmp_path: Path) -> None:
    controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs/experiments/dry_run_rabi_sequence_family.yaml")
    before = controller.current_config
    preview = controller.preview_sequence_mode_change("rabi", "generic")
    assert preview.old_mode == "curated" and preview.removed_paths
    assert controller.current_config == before


def test_resource_change_uses_capability_filtered_facade(tmp_path: Path) -> None:
    controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs/experiments/dry_run_rabi_sequence_family.yaml")
    controller.config["resources"]["asg_backup"] = dict(controller.config["resources"]["asg"])
    state = controller.change_sequence_resource("rabi", "asg_backup")
    assert next(item for item in state.plans if item.id == "rabi").resource == "asg_backup"
    with pytest.raises(ValueError, match="pulse_sequencer"):
        controller.change_sequence_resource("rabi", "daq")
