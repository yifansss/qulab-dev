from pathlib import Path

import pytest

from analysis_modules.two_trace_ratio import TwoTraceMeanRatio
from qulab.analysis import ComputePoint
from qulab.config import load_experiment_config
from qulab.core import ActionStep, MeasurementStep, ScanStep
from qulab.gui.operator_parameters import discover_operator_parameters
from qulab.gui.controller import OperatorController
from qulab.gui.workflow_model import build_workflow_tree
from qulab.sequence_generation import prepare_and_parse_experiment_config


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/experiments/rabi_pse_ai2_channel1_pfi1.yaml"


def test_rabi_hardware_config_prepares_channel1_sweep_and_pfi1_ai2() -> None:
    config = load_experiment_config(CONFIG)
    parsed = prepare_and_parse_experiment_config(config)
    tau_scan = parsed.procedure.body[0]
    assert isinstance(tau_scan, ScanStep) and len(tau_scan.values) == 21
    measurement = tau_scan.body[0]
    assert isinstance(measurement, MeasurementStep)
    calls = [step for step in measurement.body if isinstance(step, ActionStep)]
    configure = next(step for step in calls if step.action == "daq.configure_ai_external_trigger")
    assert configure.kwargs["channels"] == ["ai2"]
    assert configure.kwargs["start_trigger"] == "PFI1"
    assert configure.kwargs["sample_clock"] is None
    assert configure.kwargs["trigger_count"] == 2
    bundle = parsed.sequence_preparation.materialized["rabi_channel1"]
    assert bundle.point_count == 21
    assert bundle.plan.options["trigger_channels"] == ["ch2"]


def test_fluorescence_ratio_uses_two_independent_ai2_records() -> None:
    module = TwoTraceMeanRatio()
    module.setup({"channel_index": 0, "signal_record": 0, "reference_record": 1,
                  "signal_sample_start": 0, "signal_sample_stop": 2,
                  "reference_sample_start": 1, "reference_sample_stop": 3,
                  "denominator_epsilon": 1e-12}, {})
    result = module.process_point(ComputePoint("p1", {"tau_s": 20e-9},
                                               {"fluorescence_traces": [[[2.0, 4.0, 100.0]], [[100.0, 1.0, 2.0]]]}, {}, ""))
    assert result.data["fluorescence_signal_mean"] == pytest.approx(3.0)
    assert result.data["fluorescence_reference_mean"] == pytest.approx(1.5)
    assert result.data["fluorescence_ratio"] == pytest.approx(2.0)


def test_fluorescence_ratio_accepts_legacy_singleton_trace_wrapper() -> None:
    module = TwoTraceMeanRatio()
    module.setup({"signal_sample_stop": 2, "reference_sample_stop": 2}, {})

    result = module.process_point(
        ComputePoint(
            "p1",
            {},
            {"fluorescence_traces": [[[[2.0, 4.0]]], [[[1.0, 2.0]]]]},
            {},
            "",
        )
    )

    assert result.data["fluorescence_signal_mean"] == pytest.approx(3.0)
    assert result.data["fluorescence_reference_mean"] == pytest.approx(1.5)


def test_rabi_operator_parameters_resolve_inside_sequence_sweep() -> None:
    config = load_experiment_config(CONFIG)
    specs = {item.name: item for item in discover_operator_parameters(build_workflow_tree(config), config)}
    assert specs["ai_start_trigger"].value == "PFI1"
    assert specs["ai_read_timeout"].value == 5.0
    assert specs["ai_trigger_count"].value == 2
    assert specs["ai_samples"].path is not None
    assert specs["signal_sample_stop"].value == 1000
    assert specs["reference_sample_start"].path is not None
    assert not any(spec.warning for spec in specs.values())


def test_guided_tau_update_preserves_two_trigger_measurement_body(tmp_path: Path) -> None:
    controller = OperatorController(tmp_path / "runs")
    assert controller.load_config(CONFIG).activated
    body = controller.current_config["procedure"][0]["sequence_sweep"]["body"]
    original = repr(body)
    target = next(
        item for item in controller.workflow_composer().list_scan_targets()
        if item.kind == "sequence" and item.path[-1] == "tau_s"
    )
    controller.configure_guided_scan(
        target.id, "tau_s", {"start": 40e-9, "stop": 800e-9, "points": 31}
    )
    assert repr(controller.current_config["procedure"][0]["sequence_sweep"]["body"]) == original
    assert sum("sequence_sweep" in step for step in controller.current_config["procedure"]) == 1
    tau = controller.current_config["sequence_plans"]["rabi_channel1"]["parameters"]["tau_s"]
    assert tau["points"] == 31 and tau["stop"] == pytest.approx(800e-9)
