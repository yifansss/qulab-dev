from pathlib import Path

from qulab.config.loader import load_experiment_config


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/experiments/esr_pse_ai2_lmx_com12.yaml"


def test_esr_lmx_com12_declares_outer_sequence_and_inner_frequency_scan() -> None:
    # rabi.json intentionally lives on the lab PC, so this verifies the
    # portable declaration without requiring that physical sequence artifact.
    config = load_experiment_config(CONFIG)
    assert config["resources"]["mw"]["port"] == "COM12"
    assert config["resources"]["mw"]["output_type"] == "RFH"
    assert config["resources"]["daq"]["device"] == "Dev2"
    assert config["sync"]["triggers"][0]["target"] == "daq.PFI1"
    assert config["sequence_plans"]["esr_readout"]["template"] == "configs/sequences/rabi.json"
    outer = config["procedure"][0]["sequence_sweep"]
    assert outer["plan"] == "esr_readout"
    scan = outer["body"][0]["measurement"]["body"][0]["scan"]
    assert scan["name"] == "mw_freq_hz"
    point_body = scan["body"][0]["measurement"]["body"]
    configure = next(step for step in point_body if step.get("call") == "daq.configure_ai_external_trigger")
    assert configure["args"]["channels"] == ["ai1"]
    assert configure["args"]["trigger_count"] == 2
