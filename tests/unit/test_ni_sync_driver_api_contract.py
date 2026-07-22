from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYCONTROL = ROOT / "drivers" / "pycontrol"


class _Device:
    name = "Dev2"


class _System:
    @staticmethod
    def local():
        return types.SimpleNamespace(devices=[_Device()])


class _Constants:
    AcquisitionType = types.SimpleNamespace(FINITE="FINITE")
    Edge = types.SimpleNamespace(RISING="RISING", FALLING="FALLING")
    TerminalConfiguration = types.SimpleNamespace(DIFF="DIFF", RSE="RSE", NRSE="NRSE")
    FrequencyUnits = types.SimpleNamespace(HZ="HZ")
    Level = types.SimpleNamespace(LOW="LOW")


class _ChannelList(list):
    def add_ci_count_edges_chan(self, channel, **kwargs):
        item = types.SimpleNamespace(channel=channel, kwargs=kwargs, ci_count_edges_term=None)
        self.append(item)
        return item

    def add_ai_voltage_chan(self, channel, **kwargs):
        item = types.SimpleNamespace(channel=channel, kwargs=kwargs)
        self.append(item)
        return item

    def add_ao_voltage_chan(self, channel, **kwargs):
        item = types.SimpleNamespace(channel=channel, kwargs=kwargs)
        self.append(item)
        return item


class _Timing:
    def __init__(self):
        self.sample_clock = None

    def cfg_samp_clk_timing(self, **kwargs):
        self.sample_clock = kwargs


class _StartTrigger:
    def __init__(self):
        self.config = None
        self.retriggerable = False

    def cfg_dig_edge_start_trig(self, **kwargs):
        self.config = kwargs


class _Task:
    def __init__(self):
        self.ci_channels = _ChannelList()
        self.ai_channels = _ChannelList()
        self.ao_channels = _ChannelList()
        self.timing = _Timing()
        self.triggers = types.SimpleNamespace(start_trigger=_StartTrigger())
        self.started = False
        self.start_count = 0
        self.writes = []

    def start(self):
        self.started = True
        self.start_count += 1

    def stop(self):
        self.started = False

    def close(self):
        pass

    def write(self, data, auto_start=False):
        self.writes.append((data, auto_start))

    def read(self, number_of_samples_per_channel, timeout):
        if self.ai_channels:
            return [list(range(number_of_samples_per_channel)) for _ in self.ai_channels]
        return list(range(number_of_samples_per_channel))


def _install_fake_nidaqmx(monkeypatch):
    fake = types.ModuleType("nidaqmx")
    fake.Task = _Task
    fake.constants = _Constants
    fake.system = types.SimpleNamespace(System=_System)
    constants = types.ModuleType("nidaqmx.constants")
    constants.AcquisitionType = _Constants.AcquisitionType
    constants.Edge = _Constants.Edge
    constants.TerminalConfiguration = _Constants.TerminalConfiguration
    constants.FrequencyUnits = _Constants.FrequencyUnits
    constants.Level = _Constants.Level
    system = types.ModuleType("nidaqmx.system")
    system.System = _System
    monkeypatch.setitem(sys.modules, "nidaqmx", fake)
    monkeypatch.setitem(sys.modules, "nidaqmx.constants", constants)
    monkeypatch.setitem(sys.modules, "nidaqmx.system", system)


def _load_driver(monkeypatch):
    _install_fake_nidaqmx(monkeypatch)
    monkeypatch.syspath_prepend(str(PYCONTROL))
    sys.modules.pop("DataAcquisition.sync_driver", None)
    return importlib.import_module("DataAcquisition.sync_driver").NISyncDAQDriver


def _cleanup_pycontrol_imports() -> None:
    for name in [
        "DataAcquisition.driver",
        "DataAcquisition.sync_driver",
        "DataAcquisition",
        "nidaqmx",
        "nidaqmx.constants",
        "nidaqmx.system",
    ]:
        sys.modules.pop(name, None)


def test_sync_driver_import_does_not_import_nidaqmx(monkeypatch) -> None:
    try:
        monkeypatch.syspath_prepend(str(PYCONTROL))
        _cleanup_pycontrol_imports()

        importlib.import_module("DataAcquisition.sync_driver")

        assert "nidaqmx" not in sys.modules
    finally:
        _cleanup_pycontrol_imports()


def test_counter_external_clock_returns_binned_counts(monkeypatch) -> None:
    try:
        driver_cls = _load_driver(monkeypatch)
        driver = driver_cls(verbose=False)
        assert driver.connect("Dev2")

        config = driver.configure_counter_external_clock(
            counter_channel="ctr0",
            count_source="PFI0",
            sample_clock="PFI1",
            samples=4,
            sample_rate=1000,
            start_trigger="PFI2",
        )
        result = driver.read()

        assert config["count_source"] == "/Dev2/PFI0"
        assert config["sample_clock"] == "/Dev2/PFI1"
        assert result["kind"] == "counter_bins"
        assert result["data"]["photon_bins"] == [1.0, 1.0, 1.0, 1.0]
        assert driver.snapshot()["tasks"]["counter"]["kind"] == "counter_external_clock"
    finally:
        _cleanup_pycontrol_imports()


def test_terminal_normalization_accepts_lowercase_device_and_pfi(monkeypatch) -> None:
    try:
        driver_cls = _load_driver(monkeypatch)
        driver = driver_cls(verbose=False)
        driver.connect("dev2")

        config = driver.configure_counter_external_clock(
            counter_channel="CTR0",
            count_source="dev2/pfi0",
            sample_clock="/dev2/pfi1",
            samples=4,
            sample_rate=1000,
            start_trigger="pfi2",
        )

        assert driver.snapshot()["device"] == "Dev2"
        assert config["counter_channel"] == "Dev2/ctr0"
        assert config["count_source"] == "/Dev2/PFI0"
        assert config["sample_clock"] == "/Dev2/PFI1"
        assert config["start_trigger"] == "/Dev2/PFI2"
    finally:
        _cleanup_pycontrol_imports()


def test_ai_external_trigger_preserves_channel_metadata(monkeypatch) -> None:
    try:
        driver_cls = _load_driver(monkeypatch)
        driver = driver_cls(verbose=False)
        driver.connect("Dev2")

        driver.configure_ai_external_trigger(
            channels=["ai0", "ai1"],
            sample_rate=2_000_000,
            samples=3,
            start_trigger="PFI0",
            sample_clock="PFI1",
        )
        result = driver.read()

        assert result["kind"] == "analog_trace"
        assert result["data"]["analog_channels"] == ["ai0", "ai1"]
        assert result["data"]["analog_trace"] == [[0.0, 1.0, 2.0], [0.0, 1.0, 2.0]]
        assert result["data"]["analog_traces"] == [[[0.0, 1.0, 2.0], [0.0, 1.0, 2.0]]]
    finally:
        _cleanup_pycontrol_imports()


def test_ai_retriggerable_returns_one_record_per_trigger(monkeypatch) -> None:
    try:
        driver_cls = _load_driver(monkeypatch)
        driver = driver_cls(verbose=False)
        driver.connect("Dev2")

        config = driver.configure_ai_external_trigger(
            channels=["ai2"],
            sample_rate=1_000_000,
            samples=3,
            start_trigger="PFI1",
            trigger_count=2,
        )
        task = driver._tasks["ai"]
        result = driver.read()

        assert config["trigger_count"] == 2
        assert config["retriggerable"] is True
        assert task.triggers.start_trigger.retriggerable is True
        assert result["kind"] == "analog_traces"
        assert result["data"]["analog_traces"] == [
            [[0.0, 1.0, 2.0]],
            [[3.0, 4.0, 5.0]],
        ]
        assert result["data"]["time_axis_s"] == [0.0, 1e-06, 2e-06]
    finally:
        _cleanup_pycontrol_imports()


def test_ai_external_trigger_normalizes_channels_and_omits_null_sample_clock(monkeypatch) -> None:
    try:
        driver_cls = _load_driver(monkeypatch)
        driver = driver_cls(verbose=False)
        driver.connect("dev2")

        config = driver.configure_ai_external_trigger(
            channels=["AI1"],
            sample_rate=1_000_000,
            samples=3,
            start_trigger="dev2/pfi0",
            sample_clock="null",
        )
        ai_task = driver._tasks["ai"]

        assert config["channels"] == ["AI1"]
        assert config["physical_channels"] == ["Dev2/ai1"]
        assert config["start_trigger"] == "/Dev2/PFI0"
        assert config["sample_clock"] is None
        assert "source" not in ai_task.timing.sample_clock
    finally:
        _cleanup_pycontrol_imports()


def test_arm_starts_external_trigger_task_before_read_and_start_is_idempotent(monkeypatch) -> None:
    try:
        driver_cls = _load_driver(monkeypatch)
        driver = driver_cls(verbose=False)
        driver.connect("Dev2")
        driver.configure_ai_external_trigger(
            channels=["ai1"],
            sample_rate=1_000_000,
            samples=3,
            start_trigger="PFI1",
        )
        ai_task = driver._tasks["ai"]

        assert ai_task.started is False
        driver.arm()
        assert ai_task.started is True
        assert driver.snapshot()["started"] is True

        driver.start()
        assert ai_task.started is True
        assert ai_task.start_count == 1
    finally:
        _cleanup_pycontrol_imports()


def test_reconfigure_rearms_a_fresh_external_trigger_task(monkeypatch) -> None:
    try:
        driver_cls = _load_driver(monkeypatch)
        driver = driver_cls(verbose=False)
        driver.connect("Dev2")

        for _ in range(2):
            driver.configure_ai_external_trigger(
                channels=["ai1"],
                sample_rate=1_000_000,
                samples=3,
                start_trigger="PFI1",
            )
            ai_task = driver._tasks["ai"]
            driver.arm()
            assert ai_task.started is True
            assert ai_task.start_count == 1
            driver.read()
    finally:
        _cleanup_pycontrol_imports()


def test_step_and_sample_returns_one_trace_per_ao_point(monkeypatch) -> None:
    try:
        driver_cls = _load_driver(monkeypatch)
        driver = driver_cls(verbose=False)
        driver.connect("Dev2")

        driver.configure_ao_ai_step_and_sample(
            ao_channels=["ao0"],
            ai_channels=["ai0"],
            ao_waveform=[0.1, 0.2],
            ai_rate=1000,
            ai_samples_per_ao_point=2,
            settle_time=0,
        )
        result = driver.read()

        assert result["kind"] == "ao_ai_step_and_sample"
        assert result["data"]["ao_points"] == [[0.1, 0.2]]
        assert len(result["data"]["analog_traces"]) == 2
    finally:
        _cleanup_pycontrol_imports()
