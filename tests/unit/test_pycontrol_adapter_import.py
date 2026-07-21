import sys
from pathlib import Path

from qulab.instruments import InstrumentRegistry
from qulab.instruments.adapters.pycontrol import (
    PycontrolASGAdapter,
    PycontrolAWGAdapter,
    PycontrolLMXAdapter,
    PycontrolNIAdapter,
    _resolve_pycontrol_path,
)


def test_importing_pycontrol_adapters_does_not_import_vendor_drivers() -> None:
    forbidden = {
        "PulseGenerator.driver",
        "DataAcquisition.driver",
        "SignalGenerator.driver",
        "AWG.driver",
        "nidaqmx",
        "pyvisa",
        "serial",
    }

    assert forbidden.isdisjoint(sys.modules)


def test_default_registry_registers_pycontrol_factories_without_connecting() -> None:
    registry = InstrumentRegistry(register_defaults=True)

    mw = registry.create("mw", {"adapter": "pycontrol_lmx", "port": "COM5"})
    asg = registry.create("asg", {"adapter": "pycontrol_asg", "address": "auto"})
    daq = registry.create("daq", {"adapter": "pycontrol_ni", "device": "Dev2"})
    awg = registry.create("awg", {"adapter": "pycontrol_awg", "address": "TCPIP0::127.0.0.1::inst0::INSTR"})

    assert isinstance(mw, PycontrolLMXAdapter)
    assert isinstance(asg, PycontrolASGAdapter)
    assert isinstance(daq, PycontrolNIAdapter)
    assert isinstance(awg, PycontrolAWGAdapter)
    assert all(not resource.connected for resource in [mw, asg, daq, awg])


def test_pycontrol_path_defaults_to_project_drivers_tree() -> None:
    path = _resolve_pycontrol_path({})

    assert path == Path(__file__).resolve().parents[2] / "drivers" / "pycontrol"
    assert (path / "DataAcquisition" / "driver.py").exists()
    assert (path / "DataAcquisition" / "sync_driver.py").exists()


def test_pycontrol_asg_load_sequence_accepts_sequence_file(tmp_path: Path) -> None:
    sequence = tmp_path / "scope.seq"
    sequence.write_text("channel 5 gate\n", encoding="utf-8")
    asg = PycontrolASGAdapter("asg", {"adapter": "pycontrol_asg", "simulation": False})

    result = asg.load_sequence(sequence_file=str(sequence))

    assert result["sequence_file"] == str(sequence)
    assert result["sequence"] == "channel 5 gate\n"
    assert asg.sequence_snapshot()["compiled"] is True
