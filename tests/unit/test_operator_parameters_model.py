from copy import deepcopy
from pathlib import Path

from qulab.config import load_experiment_config, parse_experiment_config
from qulab.gui.operator_parameters import apply_operator_parameter, discover_operator_parameters
from qulab.gui.workflow_model import WorkflowDocument


ROOT = Path(__file__).resolve().parents[2]


def test_auto_discovery_finds_scan_average_call_sequence_and_storage() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")

    specs = discover_operator_parameters(None, config)
    by_name = {spec.name: spec for spec in specs}

    assert by_name["tau_s_start"].source == "procedure.scan[tau_s].values.start"
    assert by_name["tau_s_points"].widget == "integer"
    assert by_name["avg_count"].source == "procedure.average[avg].count"
    assert by_name["mw_freq_hz"].source == "setup.call[mw.set_frequency].args.freq_hz"
    assert by_name["mw_power_dbm"].source == "setup.call[mw.set_power].args.power_dbm"
    assert by_name["storage_backends"].source == "storage.backends"
    assert "asg_sequence_file" not in by_name
    assert "asg_sequence" not in by_name
    assert not any("load_sequence" in spec.name for spec in specs)
    assert all(spec.source != "setup.call[asg.load_sequence].args.sequence" for spec in specs)


def test_explicit_operator_parameters_keep_order_and_supplement_auto() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    config["operator_parameters"] = [
        {
            "name": "averages",
            "label": "Averages",
            "source": "procedure.average[avg].count",
            "widget": "integer",
            "min": 1,
        },
        {
            "name": "sequence_file",
            "label": "ASG sequence",
            "source": "resources.asg.sequence_file",
            "widget": "file_picker",
        },
    ]

    specs = discover_operator_parameters(None, config)

    assert [spec.name for spec in specs[:2]] == ["averages", "sequence_file"]
    assert specs[1].warning
    assert sum(1 for spec in specs if spec.source == "procedure.average[avg].count") == 1
    assert any(spec.name == "tau_s_points" for spec in specs)


def test_apply_operator_parameter_updates_raw_config_and_workflow_document() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    document = WorkflowDocument.from_config(config)

    apply_operator_parameter(document, config, "tau_s_points", "7")
    apply_operator_parameter(document, config, "avg_count", "3")
    apply_operator_parameter(document, config, "mw_power_dbm", "-6")
    apply_operator_parameter(document, config, "storage_backends", "csv,zarr")

    reparsed = parse_experiment_config(deepcopy(config))

    assert reparsed.validation.ok
    assert config["procedure"][0]["scan"]["values"]["points"] == 7
    assert config["procedure"][0]["scan"]["body"][0]["measurement"]["body"][1]["average"]["count"] == 3
    assert config["setup"][1]["args"]["power_dbm"] == -6
    assert "sequence_file" not in config["resources"]["asg"]
    assert config["storage"]["backends"] == ["csv", "zarr"]
    assert document.config is config


def test_load_sequence_calls_get_file_picker_parameters() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "dry_run_rabi.yaml")
    config["procedure"][0]["scan"]["body"][0]["measurement"]["body"].insert(
        0,
        {"call": "asg.load_sequence", "args": {"sequence_file": "configs/sequences/point_a.json"}},
    )

    specs = discover_operator_parameters(None, config)
    sequence_specs = [spec for spec in specs if spec.widget == "file_picker" and "load_sequence" in spec.name]

    assert sequence_specs
    assert any(spec.value == "configs/sequences/point_a.json" for spec in sequence_specs)
    assert any("#" in spec.label and "procedure/0" in spec.label for spec in sequence_specs)
    assert all(not spec.source.endswith(".args.sequence") for spec in specs)


def test_bench_05_ai_channels_are_operator_editable() -> None:
    config = load_experiment_config(
        ROOT / "configs" / "experiments" / "bench_05_pse_ai1_asg_triggered_trace.template.yaml"
    )

    specs = discover_operator_parameters(None, config)
    channel_spec = next(spec for spec in specs if spec.source.endswith("configure_ai_external_trigger].args.channels"))
    sequence_specs = [spec for spec in specs if spec.widget == "file_picker"]

    assert channel_spec.value == ["ai1"]
    assert channel_spec.path is not None
    assert len(sequence_specs) == 1
    assert sequence_specs[0].source.startswith("workflow.setup.")
    assert not any(spec.source == "resources.asg.sequence_file" for spec in specs)

    apply_operator_parameter(None, config, channel_spec.name, "[ai0, ai1]")
    assert config["procedure"][0]["average"]["body"][0]["measurement"]["body"][0]["args"]["channels"] == [
        "ai0",
        "ai1",
    ]


def test_load_sequence_picker_updates_the_original_path_argument() -> None:
    config = {
        "resources": {"pulse_main": {"adapter": "mock_asg", "capabilities": ["pulse_sequencer"]}},
        "procedure": [{"call": "pulse_main.load_sequence", "args": {"path": "one.json"}}],
    }

    spec = next(spec for spec in discover_operator_parameters(None, config) if spec.widget == "file_picker")
    apply_operator_parameter(None, config, spec.name, "two.json")

    assert config["procedure"][0]["args"] == {"path": "two.json"}
