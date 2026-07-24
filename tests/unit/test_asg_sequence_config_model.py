import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from qulab.config import load_experiment_config, parse_experiment_config
from qulab.core import ActionStep, ExperimentContext, Procedure
from qulab.gui.controller import OperatorController


ROOT = Path(__file__).resolve().parents[2]


def test_controller_updates_asg_sequence_file_and_preflight_snapshot(tmp_path: Path) -> None:
    sequence = tmp_path / "rabi.seq"
    sequence.write_text("channel 5 gate ${tau_s}\n", encoding="utf-8")
    controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")

    controller.update_sequence_file("asg", str(sequence))
    controller.update_sequence_param("asg", "tau_s", "${tau_s}")
    view = controller.prepare()

    assert "asg" in controller.sequence_resource_names()
    assert view.sequence_snapshots
    snapshot = next(item for item in view.sequence_snapshots if item.resource == "asg")
    assert snapshot.exists is True
    assert snapshot.sha256 is not None
    assert snapshot.parameters == ("tau_s",)
    assert snapshot.channels == ("ch5",)
    assert snapshot.sequence_params == {"tau_s": "${tau_s}"}
    parse_experiment_config(controller.current_config)


def test_sequence_file_round_trips_through_saved_yaml(tmp_path: Path) -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    config["resources"]["asg"]["sequence_file"] = "configs/sequences/rabi.seq"
    config["resources"]["asg"]["sequence_params"] = {"tau_s": "${tau_s}"}
    controller = OperatorController(tmp_path / "runs")
    path = tmp_path / "sequence_config.yaml"
    from qulab.gui.yaml_editor import save_config_yaml

    save_config_yaml(config, path)
    controller.load_config(path)

    assert controller.get_sequence_file("asg") == "configs/sequences/rabi.seq"
    assert controller.get_sequence_params("asg") == {"tau_s": "${tau_s}"}


def test_sequence_inspection_does_not_create_missing_asg_resource(tmp_path: Path) -> None:
    controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs" / "experiments" / "bench_01_pse_ai1_dark_trace.template.yaml")

    assert controller.sequence_resource_names() == []

    snapshot = controller.inspect_sequence_resource("asg")
    view = controller.prepare()

    assert snapshot.resource == "asg"
    assert "asg" not in controller.current_config["resources"]
    assert view.ok
    assert {resource.name for resource in view.resources} == {"daq"}


def test_controller_hardware_run_connects_and_disconnects_resources(tmp_path: Path) -> None:
    calls: list[str] = []

    class HardwareLikeResource:
        simulation = False
        connected = False

        def connect(self):
            calls.append("connect")
            self.connected = True

        def disconnect(self):
            calls.append("disconnect")
            self.connected = False

        def start(self):
            if not self.connected:
                raise RuntimeError("not connected")
            calls.append("start")
            return True

    controller = OperatorController(tmp_path / "runs")
    resource = HardwareLikeResource()
    controller.parsed = SimpleNamespace(
        name="hardware_like",
        config={"name": "hardware_like"},
        resolved_config={"name": "hardware_like"},
        validation=SimpleNamespace(ok=True, errors=[], issues=[]),
        procedure=Procedure(name="hardware_like", body=[ActionStep(name="start", action="asg.start")]),
        context=ExperimentContext(resources={"asg": resource}),
    )

    result = controller.start_hardware_run()

    assert result.status == "completed"
    assert calls == ["connect", "start", "disconnect"]
    assert resource.connected is False


def test_controller_cleans_resource_that_fails_during_connect_and_records_error(tmp_path: Path) -> None:
    calls: list[str] = []

    class FailingResource:
        simulation = False
        connected = False

        def connect(self):
            calls.append("connect")
            self.connected = True
            raise RuntimeError("device is busy")

        def disconnect(self):
            calls.append("disconnect")
            self.connected = False

        def stop(self):
            calls.append("stop")

    controller = OperatorController(tmp_path / "runs")
    resource = FailingResource()
    controller.parsed = SimpleNamespace(
        name="connect_failure",
        config={"name": "connect_failure"},
        resolved_config={"name": "connect_failure"},
        validation=SimpleNamespace(ok=True, errors=[], issues=[]),
        procedure=Procedure(name="connect_failure"),
        context=ExperimentContext(resources={"asg": resource}),
    )

    with pytest.raises(RuntimeError, match="device is busy"):
        controller.start_hardware_run()

    assert calls.count("disconnect") >= 1
    assert resource.connected is False
    run_path = next((tmp_path / "runs").glob("*/*_connect_failure"))
    events = [json.loads(line) for line in (run_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(
        event["type"] == "ErrorRaised"
        and event["step_id"] == "hardware_startup"
        and "device is busy" in event["message"]
        for event in events
    )


def test_controller_reparses_each_run_so_resource_instances_are_not_reused(tmp_path: Path) -> None:
    controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")

    first = controller.start_dry_run()
    assert controller.parsed is not None
    first_asg = controller.parsed.context.resources["asg"]
    second = controller.start_dry_run()

    assert first.run_path != second.run_path
    assert controller.parsed is not None
    assert controller.parsed.context.resources["asg"] is not first_asg


def test_preflight_sequence_snapshots_include_workflow_load_sequence_files(tmp_path: Path) -> None:
    resource_sequence = tmp_path / "resource.json"
    workflow_sequence = tmp_path / "workflow.json"
    resource_sequence.write_text('[{"channel_name": "Channel 1", "pulses": []}]', encoding="utf-8")
    workflow_sequence.write_text('[{"channel_name": "Channel 2", "pulses": []}]', encoding="utf-8")
    controller = OperatorController(tmp_path / "runs")
    controller.load_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    controller.update_sequence_file("asg", str(resource_sequence))
    assert controller.config is not None
    controller.config["setup"].append({"call": "asg.load_sequence", "args": {"sequence_file": str(workflow_sequence)}})

    view = controller.prepare()

    paths = {snapshot.sequence_file for snapshot in view.sequence_snapshots}
    assert str(resource_sequence) in paths
    assert str(workflow_sequence) in paths
