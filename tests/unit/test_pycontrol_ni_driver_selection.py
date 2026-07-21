from __future__ import annotations

from pathlib import Path

import pytest

from qulab.instruments.adapters.pycontrol import PycontrolNIAdapter
from qulab.instruments.base import InstrumentUnsupportedOperation


def _clear_data_acquisition_modules() -> None:
    import sys

    for name in ["DataAcquisition.driver", "DataAcquisition.sync_driver", "DataAcquisition"]:
        sys.modules.pop(name, None)


def _write_pycontrol_stub(root: Path) -> None:
    package = root / "DataAcquisition"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "driver.py").write_text(
        """
class NIDAQDriver:
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.connected = False
    def connect(self, device):
        self.connected = True
        self.device = device
        return True
    def get_photon_counts(self, sample_rate, num_samples, source_terminal='PFI0'):
        return list(range(num_samples))
    def read_analog(self, channels, sample_rate, samples):
        return [[0] * samples for _ in channels]
    def set_constant_voltage(self, channel, voltage):
        return True
    def stop(self):
        return False
""",
        encoding="utf-8",
    )
    (package / "sync_driver.py").write_text(
        """
class NISyncDAQDriver:
    def __init__(self, verbose=False, strict_hardware=True):
        self.verbose = verbose
        self.strict_hardware = strict_hardware
        self.configured = None
    def connect(self, device):
        self.device = device
        return True
    def configure_counter_external_clock(self, **kwargs):
        self.configured = dict(kwargs)
        return dict(kwargs)
    def arm(self):
        return True
    def read(self, timeout=None):
        return {'kind': 'counter_bins', 'data': {'photon_bins': [1, 2]}, 'metadata': {'timeout': timeout}}
    def read_counts_binned(self, timeout=None):
        return self.read(timeout)
    def set_ao_static(self, channel, voltage):
        return True
    def wait_settle(self, seconds):
        return True
    def stop(self):
        return False
""",
        encoding="utf-8",
    )


def test_pycontrol_ni_defaults_to_legacy_driver(tmp_path) -> None:
    try:
        _write_pycontrol_stub(tmp_path)
        _clear_data_acquisition_modules()
        adapter = PycontrolNIAdapter("daq", {"device": "Dev2", "pycontrol_path": str(tmp_path)})

        adapter.connect()

        assert adapter.driver_mode == "legacy"
        assert adapter.snapshot()["settings"]["driver"] == "legacy"
        with pytest.raises(InstrumentUnsupportedOperation):
            adapter.configure_counter_external_clock(sample_clock="PFI1")
    finally:
        _clear_data_acquisition_modules()


def test_pycontrol_ni_can_select_sync_driver(tmp_path) -> None:
    try:
        _write_pycontrol_stub(tmp_path)
        _clear_data_acquisition_modules()
        adapter = PycontrolNIAdapter(
            "daq",
            {
                "device": "Dev2",
                "pycontrol_path": str(tmp_path),
                "driver": "sync",
                "strict_hardware": False,
            },
        )

        adapter.connect()
        config = adapter.configure_counter_external_clock(sample_clock="PFI1", samples=2)
        adapter.arm()
        result = adapter.read(timeout=1.5)

        assert adapter.driver_mode == "sync"
        assert config["sample_clock"] == "PFI1"
        assert result["kind"] == "counter_bins"
        assert result["metadata"]["timeout"] == 1.5
    finally:
        _clear_data_acquisition_modules()


def test_pycontrol_ni_stop_accepts_false_return_as_stopped(tmp_path) -> None:
    try:
        _write_pycontrol_stub(tmp_path)
        _clear_data_acquisition_modules()
        adapter = PycontrolNIAdapter(
            "daq",
            {
                "device": "Dev2",
                "pycontrol_path": str(tmp_path),
                "driver": "sync",
                "strict_hardware": False,
            },
        )

        adapter.connect()

        assert adapter.stop() is False
    finally:
        _clear_data_acquisition_modules()


def test_pycontrol_ni_can_select_explicit_driver_class(tmp_path) -> None:
    try:
        _write_pycontrol_stub(tmp_path)
        _clear_data_acquisition_modules()
        adapter = PycontrolNIAdapter(
            "daq",
            {
                "device": "Dev2",
                "pycontrol_path": str(tmp_path),
                "driver_class": "DataAcquisition.sync_driver.NISyncDAQDriver",
                "strict_hardware": False,
            },
        )

        adapter.connect()

        assert adapter.driver_mode == "custom"
        assert adapter.snapshot()["settings"]["driver_class"].endswith(".NISyncDAQDriver")
    finally:
        _clear_data_acquisition_modules()
