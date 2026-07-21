"""Deterministic mock instrument adapters for dry-run experiments."""

from __future__ import annotations

from typing import Any

from qulab.instruments import capabilities as caps
from qulab.instruments.base import InstrumentAdapter


class MockMicrowaveSource(InstrumentAdapter):
    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, adapter="mock_microwave", simulation=True)
        config = config or {}
        self.frequency_hz = float(config.get("frequency_hz", 2.87e9))
        self.power_dbm = float(config.get("power_dbm", -10.0))
        self.output_enabled = bool(config.get("output", False))

    def set_frequency(self, freq_hz: float) -> float:
        self.frequency_hz = float(freq_hz)
        return self.frequency_hz

    def set_power(self, power_dbm: float) -> float:
        self.power_dbm = float(power_dbm)
        return self.power_dbm

    def output_on(self) -> bool:
        self.output_enabled = True
        return self.output_enabled

    def output_off(self) -> bool:
        self.output_enabled = False
        return self.output_enabled

    def capabilities(self) -> set[str]:
        return {caps.MICROWAVE_SOURCE}

    def snapshot(self) -> dict[str, Any]:
        payload = super().snapshot()
        payload["settings"] = {
            "frequency_hz": self.frequency_hz,
            "power_dbm": self.power_dbm,
            "output": self.output_enabled,
        }
        return payload


class MockPulseSequencer(InstrumentAdapter):
    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, adapter="mock_pulse_sequencer", simulation=True)
        config = config or {}
        self.sequence = config.get("sequence")
        self.sequence_file = config.get("sequence_file") or config.get("sequence_path")
        self.sequence_params: dict[str, Any] = {}
        self.trigger_config: dict[str, Any] = {}
        self.armed = False
        self.running = False
        self.compiled = False

    def load_sequence(
        self,
        sequence_file: str | None = None,
        path: str | None = None,
        sequence: Any = None,
    ) -> dict[str, Any]:
        new_sequence_file = sequence_file or path
        if new_sequence_file is not None:
            self.sequence_file = new_sequence_file
        if sequence is not None:
            self.sequence = sequence
        self.compiled = False
        return {"sequence_file": self.sequence_file, "sequence": sequence}

    def set_sequence_param(self, name: str, value: Any) -> Any:
        self.sequence_params[str(name)] = value
        return value

    def compile_sequence(self) -> str:
        self.compiled = True
        return "mock_sequence"

    def configure_trigger(self, **kwargs: Any) -> dict[str, Any]:
        self.trigger_config.update(kwargs)
        return dict(self.trigger_config)

    def arm(self) -> bool:
        self.armed = True
        return self.armed

    def start(self) -> bool:
        self.running = True
        self.armed = False
        return self.running

    def stop(self) -> bool:
        self.running = False
        self.armed = False
        return self.running

    def capabilities(self) -> set[str]:
        return {caps.PULSE_SEQUENCER, caps.TRIGGER_SOURCE}

    def snapshot(self) -> dict[str, Any]:
        payload = super().snapshot()
        payload["settings"] = {
            "sequence_file": self.sequence_file,
            "sequence_params": dict(self.sequence_params),
            "trigger": dict(self.trigger_config),
            "armed": self.armed,
            "running": self.running,
            "compiled": self.compiled,
        }
        return payload


class MockDAQCounter(InstrumentAdapter):
    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, adapter="mock_daq_counter", simulation=True)
        self.counter_config: dict[str, Any] = {}
        self.armed = False
        self.read_index = 0

    def configure_counter(
        self,
        sample_rate: float | None = None,
        samples: int | None = None,
        source: str | None = None,
        trigger: str | None = None,
    ) -> dict[str, Any]:
        self.counter_config = {
            "sample_rate": sample_rate,
            "samples": samples,
            "source": source,
            "trigger": trigger,
        }
        return dict(self.counter_config)

    def arm(self) -> bool:
        self.armed = True
        return self.armed

    def read_counts(self, timeout: float | None = None) -> dict[str, Any]:
        self.read_index += 1
        base = 1000 + self.read_index
        self.armed = False
        return {"counts_mean": float(base), "photon_bins": [base - 1, base, base + 1], "timeout": timeout}

    def read_counts_binned(self, bins: int = 4) -> list[int]:
        self.read_index += 1
        return [100 + self.read_index + index for index in range(bins)]

    def read_counts_trace(self, bins: int = 4) -> dict[str, Any]:
        photon_bins = self.read_counts_binned(bins=bins)
        return {
            "counts_mean": float(sum(photon_bins) / len(photon_bins)) if photon_bins else 0.0,
            "photon_bins": photon_bins,
        }

    def read_analog(self, timeout: float | None = None) -> list[list[float]]:
        return [[0.0, 0.1], [0.2, 0.3]]

    def stop(self) -> bool:
        self.armed = False
        return self.armed

    def capabilities(self) -> set[str]:
        return {caps.DAQ_COUNTER, caps.ANALOG_INPUT, caps.TRIGGER_RECEIVER}

    def snapshot(self) -> dict[str, Any]:
        payload = super().snapshot()
        payload["settings"] = {
            "counter": dict(self.counter_config),
            "armed": self.armed,
            "read_index": self.read_index,
        }
        return payload


class MockAnalogIO(InstrumentAdapter):
    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name=name, adapter="mock_analog_io", simulation=True)
        self.ai_config: dict[str, Any] = {}
        self.outputs: dict[str, float] = {}
        self.waveforms: dict[str, dict[str, Any]] = {}

    def configure_ai(
        self,
        channels: list[str] | str,
        sample_rate: float | None = None,
        samples: int | None = None,
        terminal_config: str | None = None,
    ) -> dict[str, Any]:
        self.ai_config = {
            "channels": channels,
            "sample_rate": sample_rate,
            "samples": samples,
            "terminal_config": terminal_config,
        }
        return dict(self.ai_config)

    def read_analog(self, timeout: float | None = None) -> list[list[float]]:
        return [[0.0, 0.1], [0.2, 0.3]]

    def set_voltage(self, channel: str, voltage: float) -> float:
        self.outputs[channel] = float(voltage)
        return self.outputs[channel]

    def set_waveform(self, channel: str, waveform: list[float], sample_rate: float | None = None) -> dict[str, Any]:
        self.waveforms[channel] = {"waveform": list(waveform), "sample_rate": sample_rate}
        return dict(self.waveforms[channel])

    def capabilities(self) -> set[str]:
        return {caps.ANALOG_INPUT, caps.ANALOG_OUTPUT}

    def snapshot(self) -> dict[str, Any]:
        payload = super().snapshot()
        payload["settings"] = {
            "ai": dict(self.ai_config),
            "outputs": dict(self.outputs),
            "waveforms": dict(self.waveforms),
        }
        return payload
