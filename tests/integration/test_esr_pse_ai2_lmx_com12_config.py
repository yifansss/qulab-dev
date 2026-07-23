from pathlib import Path

from qulab.gui.controller import OperatorController


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/experiments/esr_pse_ai2_lmx_com12.yaml"


def test_esr_lmx_com12_hardware_config_prepares_two_trace_frequency_scan(tmp_path) -> None:
    controller = OperatorController(tmp_path / "runs")
    result = controller.load_config(CONFIG)

    assert result.activated, [f"{item.code}: {item.message}" for item in result.diagnostics]
    config = controller.current_config
    assert config["resources"]["mw"]["port"] == "COM12"
    assert config["resources"]["mw"]["output_type"] == "RFH"
    assert config["resources"]["daq"]["device"] == "Dev2"
    assert config["sync"]["triggers"][0]["target"] == "daq.PFI1"
    assert config["procedure"][0]["scan"]["name"] == "mw_freq_hz"
    assert config["procedure"][0]["scan"]["body"][0]["measurement"]["body"][-1]["sequence_sweep"]["plan"] == "esr_readout"
