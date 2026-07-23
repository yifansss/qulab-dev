"""pycontrol hardware adapters.

The adapters in this module deliberately avoid importing pycontrol at module
import time. Driver imports and SDK loading happen only in ``connect()``.
"""

from __future__ import annotations

import importlib
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from qulab.paths import project_root, resolve_project_path
from qulab.sequence_generation.asg_script import compile_asg_sequence_json, is_asg_sequence_json
from qulab.instruments import capabilities as caps
from qulab.instruments.base import (
    InstrumentAdapter,
    InstrumentConfigurationError,
    InstrumentConnectionError,
    InstrumentUnsupportedOperation,
)


def _bool_config(config: dict[str, Any], key: str, default: bool = False) -> bool:
    value = config.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _resolve_pycontrol_path(config: dict[str, Any]) -> Path | None:
    raw_path = config.get("pycontrol_path") or os.environ.get("QULAB_PYCONTROL_PATH")
    if not raw_path:
        for candidate in _default_pycontrol_paths():
            if candidate.exists():
                return candidate
        return None
    return resolve_project_path(raw_path)


def _project_root() -> Path:
    return project_root()


def _default_pycontrol_paths() -> tuple[Path, ...]:
    root = _project_root()
    return (
        root / "drivers" / "pycontrol",
    )


def _resolve_project_file(path: str | Path) -> Path:
    resolved = resolve_project_path(path)
    if resolved is None:
        raise InstrumentConfigurationError(f"File path is empty: {path!r}")
    return resolved


@contextmanager
def _pycontrol_import_path(path: Path | None) -> Iterator[None]:
    if path is None:
        yield
        return
    if not path.exists():
        raise InstrumentConnectionError(
            f"pycontrol path does not exist: {path}. Set resource pycontrol_path or QULAB_PYCONTROL_PATH."
        )
    text = str(path)
    inserted = text not in sys.path
    if inserted:
        sys.path.insert(0, text)
    try:
        yield
    finally:
        if inserted:
            try:
                sys.path.remove(text)
            except ValueError:
                pass


def _load_driver(config: dict[str, Any], module_name: str, class_name: str) -> type[Any]:
    path = _resolve_pycontrol_path(config)
    try:
        with _pycontrol_import_path(path):
            module = importlib.import_module(module_name)
            return getattr(module, class_name)
    except InstrumentConnectionError:
        raise
    except Exception as exc:  # noqa: BLE001 - preserve original vendor import error context.
        hint = (
            "Qulab first checks resource pycontrol_path, then QULAB_PYCONTROL_PATH, "
            "then drivers/pycontrol under the project root."
        )
        raise InstrumentConnectionError(f"Could not import pycontrol driver {module_name}.{class_name}: {exc}. {hint}") from exc


def _split_driver_class(dotted: str) -> tuple[str, str]:
    module_name, separator, class_name = dotted.rpartition(".")
    if not separator or not module_name or not class_name:
        raise InstrumentConfigurationError(f"driver_class must be a dotted class path, got: {dotted!r}")
    return module_name, class_name


def _require_success(result: Any, action: str) -> None:
    if result is False:
        raise InstrumentConnectionError(f"pycontrol action failed: {action}")


class _PycontrolAdapterBase(InstrumentAdapter):
    adapter_name = "pycontrol"
    vendor = "pycontrol"
    model = "hardware"
    capability_names: set[str] = set()

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        config = dict(config or {})
        simulation = _bool_config(config, "simulation", False)
        if simulation:
            raise InstrumentConfigurationError(
                f"{self.adapter_name} resource '{name}' is hardware-only; use mock adapters for simulation"
            )
        super().__init__(name=name, adapter=self.adapter_name, simulation=False)
        self.config = config
        self._driver: Any = None
        self._last_error: str | None = None

    def capabilities(self) -> set[str]:
        return set(self.capability_names)

    def health_check(self) -> dict[str, Any]:
        return {
            "ok": self.connected and self._driver is not None,
            "connected": self.connected,
            "simulation": self.simulation,
            "last_error": self._last_error,
        }

    def disconnect(self) -> None:
        if self._driver is not None:
            disconnect = getattr(self._driver, "disconnect", None)
            if callable(disconnect):
                disconnect()
        self.connected = False

    def snapshot(self) -> dict[str, Any]:
        payload = super().snapshot()
        payload.update({"vendor": self.vendor, "model": self.model})
        payload["pycontrol_path"] = str(_resolve_pycontrol_path(self.config)) if _resolve_pycontrol_path(self.config) else None
        payload["settings"] = self._settings_snapshot()
        return payload

    def _settings_snapshot(self) -> dict[str, Any]:
        return {}


class PycontrolLMXAdapter(_PycontrolAdapterBase):
    adapter_name = "pycontrol_lmx"
    vendor = "Peking University"
    model = "LMX2572 RF6G"
    capability_names = {caps.MICROWAVE_SOURCE}

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config)
        self.port = self.config.get("port")
        self.baudrate = int(self.config.get("baudrate", 921600))
        self.output_type = str(self.config.get("output_type", "RFH"))
        self.frequency_hz: float | None = self.config.get("frequency_hz")
        self.power_dbm: float | None = self.config.get("power_dbm")
        self.output_enabled = False

    def connect(self) -> None:
        if not self.port:
            raise InstrumentConfigurationError(f"Resource '{self.name}' requires serial port for pycontrol_lmx")
        driver_cls = _load_driver(self.config, "SignalGenerator.driver", "LMX2572Driver")
        try:
            self._driver = driver_cls(output_type=self.output_type, verbose=_bool_config(self.config, "verbose", False))
            _require_success(self._driver.connect(str(self.port), self.baudrate), "LMX2572.connect")
            self.connected = True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            raise InstrumentConnectionError(f"Failed to connect pycontrol LMX resource '{self.name}': {exc}") from exc

    def set_frequency(self, freq_hz: float) -> float:
        self._ensure_connected()
        _require_success(self._driver.set_frequency(float(freq_hz)), "LMX2572.set_frequency")
        self.frequency_hz = float(freq_hz)
        return self.frequency_hz

    def set_power(self, power_dbm: float) -> float:
        """Set the pycontrol LMX power level.

        The RF6G pycontrol driver accepts integer amplitude levels, not
        calibrated dBm. Qulab keeps the capability name for template
        compatibility and records the unit caveat in snapshots.
        """

        self._ensure_connected()
        _require_success(self._driver.set_power(float(power_dbm)), "LMX2572.set_power")
        self.power_dbm = float(power_dbm)
        return self.power_dbm

    def output_on(self) -> bool:
        self._ensure_connected()
        _require_success(self._driver.set_output(True), "LMX2572.set_output(True)")
        self.output_enabled = True
        return True

    def output_off(self) -> bool:
        self._ensure_connected()
        _require_success(self._driver.set_output(False), "LMX2572.set_output(False)")
        self.output_enabled = False
        return False

    def _ensure_connected(self) -> None:
        if not self.connected or self._driver is None:
            raise InstrumentConnectionError(f"pycontrol LMX resource '{self.name}' is not connected")

    def _settings_snapshot(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "baudrate": self.baudrate,
            "output_type": self.output_type,
            "frequency_hz": self.frequency_hz,
            "power_dbm": self.power_dbm,
            "power_unit_note": "pycontrol LMX uses board amplitude level, not calibrated dBm",
            "output": self.output_enabled,
        }


class PycontrolASGAdapter(_PycontrolAdapterBase):
    adapter_name = "pycontrol_asg"
    vendor = "CIQTEK"
    model = "ASG24100"
    capability_names = {caps.PULSE_SEQUENCER, caps.TRIGGER_SOURCE}

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config)
        self.address = self.config.get("address")
        self.sequence: Any = None
        self.sequence_path: str | None = None
        self.sequence_params: dict[str, Any] = {}
        self.trigger_config: dict[str, Any] = {}
        self.armed = False
        self.running = False
        self.compiled_code: str | None = None
        self.output_channels: list[int] = []

    def connect(self) -> None:
        driver_cls = _load_driver(self.config, "PulseGenerator.driver", "ASG24100Driver")
        try:
            self._driver = driver_cls(verbose=_bool_config(self.config, "verbose", False), force_simulation=False)
            address = None if self.address in (None, "", "auto") else str(self.address)
            _require_success(self._driver.connect(address), "ASG24100.connect")
            self.connected = True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            raise InstrumentConnectionError(f"Failed to connect pycontrol ASG resource '{self.name}': {exc}") from exc

    def load_sequence(
        self,
        path: str | None = None,
        sequence_file: str | None = None,
        sequence: Any = None,
        code: str | None = None,
    ) -> dict[str, Any]:
        selected_path = sequence_file or path or self.config.get("sequence_file")
        if selected_path:
            resolved_path = _resolve_project_file(str(selected_path))
            self.sequence_path = str(resolved_path)
            code = resolved_path.read_text(encoding="utf-8")
        self.sequence = sequence if sequence is not None else code
        self.compiled_code = code if code is not None else (str(sequence) if sequence is not None else None)
        return {"path": self.sequence_path, "sequence_file": self.sequence_path, "sequence": self.sequence}

    def set_sequence_param(self, name: str, value: Any) -> Any:
        self.sequence_params[str(name)] = value
        return value

    def compile_sequence(self) -> str | None:
        if self.compiled_code and is_asg_sequence_json(self.compiled_code):
            self.compiled_code = compile_asg_sequence_json(self.compiled_code)
        return self.compiled_code

    def configure_trigger(self, **kwargs: Any) -> dict[str, Any]:
        self.trigger_config.update(kwargs)
        if self.connected and self._driver is not None and hasattr(self._driver, "configure_free_mode"):
            _require_success(self._driver.configure_free_mode(**kwargs), "ASG24100.configure_free_mode")
        return dict(self.trigger_config)

    def configure_trigger_output(self, channel: str, mode: str, edge: str | None = None, level: Any = None) -> dict[str, Any]:
        self.trigger_config.update({"channel": channel, "mode": mode, "edge": edge, "level": level})
        return dict(self.trigger_config)

    def trigger_snapshot(self) -> dict[str, Any]:
        return dict(self.trigger_config)

    def arm(self) -> bool:
        self._ensure_connected()
        self.compile_sequence()
        if self.compiled_code and hasattr(self._driver, "upload_and_run"):
            self.output_channels = sorted(
                {int(channel) for channel in re.findall(r"ASG_OUT\s*\[\s*(\d+)\s*\]", self.compiled_code)}
            )
            configure_outputs = getattr(self._driver, "configure_output_channels", None)
            if self.output_channels and callable(configure_outputs):
                _require_success(
                    configure_outputs(
                        channel_limit=max(self.output_channels),
                        voltage_level=int(self.config.get("voltage_level", 0)),
                        impedance=int(self.config.get("impedance", 0)),
                        configure_childcards=_bool_config(self.config, "configure_childcards", False),
                    ),
                    "ASG24100.configure_output_channels",
                )
            _require_success(
                self._driver.upload_and_run(
                    self.compiled_code,
                    loop=int(self.config.get("loop", 1)),
                    arm_only=True,
                    configure_mode=_bool_config(self.config, "configure_playback_mode", False),
                ),
                "ASG24100.upload_and_run(arm_only)",
            )
        self.armed = True
        return True

    def start(self) -> bool:
        self._ensure_connected()
        _require_success(self._driver.start(), "ASG24100.start")
        self.running = True
        self.armed = False
        return True

    def stop(self) -> bool:
        if self._driver is not None and self.connected:
            safe_stop = getattr(self._driver, "safe_stop", None)
            if callable(safe_stop):
                _require_success(safe_stop(self.output_channels or None), "ASG24100.safe_stop")
            else:
                _require_success(self._driver.stop(), "ASG24100.stop")
        self.running = False
        self.armed = False
        return False

    def disconnect(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
        super().disconnect()

    def sequence_snapshot(self) -> dict[str, Any]:
        return {
            "path": self.sequence_path,
            "params": dict(self.sequence_params),
            "compiled": self.compiled_code is not None,
        }

    def _ensure_connected(self) -> None:
        if not self.connected or self._driver is None:
            raise InstrumentConnectionError(f"pycontrol ASG resource '{self.name}' is not connected")

    def _settings_snapshot(self) -> dict[str, Any]:
        status = None
        if self.connected and self._driver is not None and hasattr(self._driver, "status"):
            try:
                status = self._driver.status()
            except Exception as exc:  # noqa: BLE001
                status = {"error": str(exc)}
        return {
            "address": self.address,
            "sequence": self.sequence_snapshot(),
            "trigger": dict(self.trigger_config),
            "output_channels": list(self.output_channels),
            "voltage_level": int(self.config.get("voltage_level", 0)),
            "impedance": int(self.config.get("impedance", 0)),
            "armed": self.armed,
            "running": self.running,
            "status": status,
        }


class PycontrolNIAdapter(_PycontrolAdapterBase):
    adapter_name = "pycontrol_ni"
    vendor = "National Instruments"
    model = "NI-DAQmx"
    capability_names = {caps.DAQ_COUNTER, caps.ANALOG_INPUT, caps.ANALOG_OUTPUT, caps.TRIGGER_RECEIVER}

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config)
        self.device = str(self.config.get("device", "Dev2"))
        self.counter_config: dict[str, Any] = {}
        self.ai_config: dict[str, Any] = {}
        self.trigger_config: dict[str, Any] = {}
        self.outputs: dict[str, float] = {}
        self.armed = False
        self.driver_mode = str(self.config.get("driver", "legacy"))

    def connect(self) -> None:
        module_name, class_name = self._driver_target()
        driver_cls = _load_driver(self.config, module_name, class_name)
        try:
            if self._uses_sync_driver(module_name, class_name):
                self._driver = driver_cls(
                    verbose=_bool_config(self.config, "verbose", False),
                    strict_hardware=_bool_config(self.config, "strict_hardware", True),
                )
            else:
                self._driver = driver_cls(verbose=_bool_config(self.config, "verbose", False))
            _require_success(self._driver.connect(self.device), "NIDAQ.connect")
            self.connected = True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            raise InstrumentConnectionError(f"Failed to connect pycontrol NI resource '{self.name}': {exc}") from exc

    def _driver_target(self) -> tuple[str, str]:
        explicit = self.config.get("driver_class")
        if explicit:
            module_name, class_name = _split_driver_class(str(explicit))
            self.driver_mode = "custom"
            return module_name, class_name
        if str(self.config.get("driver", "legacy")).lower() == "sync":
            self.driver_mode = "sync"
            return "DataAcquisition.sync_driver", "NISyncDAQDriver"
        self.driver_mode = "legacy"
        return "DataAcquisition.driver", "NIDAQDriver"

    def _uses_sync_driver(self, module_name: str | None = None, class_name: str | None = None) -> bool:
        if self.driver_mode == "sync":
            return True
        if module_name is not None and class_name is not None:
            return module_name == "DataAcquisition.sync_driver" and class_name == "NISyncDAQDriver"
        return self._driver is not None and hasattr(self._driver, "configure_counter_external_clock")

    def configure_counter(
        self,
        sample_rate: float | None = None,
        samples: int | None = None,
        source: str | None = None,
        trigger: str | None = None,
    ) -> dict[str, Any]:
        self.counter_config = {"sample_rate": sample_rate, "samples": samples, "source": source, "trigger": trigger}
        return dict(self.counter_config)

    def configure_counter_external_clock(
        self,
        counter_channel: str = "ctr0",
        count_source: str = "PFI0",
        sample_clock: str = "PFI1",
        samples: int = 1000,
        sample_rate: float | None = None,
        start_trigger: str | None = None,
        edge: str = "rising",
    ) -> dict[str, Any]:
        self._ensure_connected()
        method = getattr(self._driver, "configure_counter_external_clock", None)
        if not callable(method):
            self._unsupported_sync("configure_counter_external_clock")
        self.counter_config = method(
            counter_channel=counter_channel,
            count_source=count_source,
            sample_clock=sample_clock,
            samples=samples,
            sample_rate=sample_rate,
            start_trigger=start_trigger,
            edge=edge,
        )
        return dict(self.counter_config)

    def configure_ai(
        self,
        channels: list[str] | str,
        sample_rate: float | None = None,
        samples: int | None = None,
        terminal_config: str | None = None,
    ) -> dict[str, Any]:
        self.ai_config = {
            "channels": [channels] if isinstance(channels, str) else list(channels),
            "sample_rate": sample_rate,
            "samples": samples,
            "terminal_config": terminal_config,
        }
        return dict(self.ai_config)

    def configure_ai_external_trigger(
        self,
        channels: list[str] | str,
        sample_rate: float,
        samples: int,
        start_trigger: str,
        sample_clock: str | None = None,
        edge: str = "rising",
        terminal_config: str = "DIFF",
        trigger_count: int = 1,
    ) -> dict[str, Any]:
        self._ensure_connected()
        method = getattr(self._driver, "configure_ai_external_trigger", None)
        if not callable(method):
            self._unsupported_sync("configure_ai_external_trigger")
        self.ai_config = method(
            channels=channels,
            sample_rate=sample_rate,
            samples=samples,
            start_trigger=start_trigger,
            sample_clock=sample_clock,
            edge=edge,
            terminal_config=terminal_config,
            trigger_count=trigger_count,
        )
        return dict(self.ai_config)

    def configure_ao_ai_sync(self, **kwargs: Any) -> dict[str, Any]:
        self._ensure_connected()
        method = getattr(self._driver, "configure_ao_ai_sync", None)
        if not callable(method):
            self._unsupported_sync("configure_ao_ai_sync")
        self.ai_config = method(**kwargs)
        return dict(self.ai_config)

    def configure_ao_ai_step_and_sample(self, **kwargs: Any) -> dict[str, Any]:
        self._ensure_connected()
        method = getattr(self._driver, "configure_ao_ai_step_and_sample", None)
        if not callable(method):
            self._unsupported_sync("configure_ao_ai_step_and_sample")
        self.ai_config = method(**kwargs)
        return dict(self.ai_config)

    def configure_trigger_input(self, channel: str, edge: str = "rising") -> dict[str, Any]:
        self.trigger_config = {"channel": channel, "edge": edge}
        return dict(self.trigger_config)

    def trigger_snapshot(self) -> dict[str, Any]:
        return dict(self.trigger_config)

    def arm(self) -> bool:
        self._ensure_connected()
        driver_arm = getattr(self._driver, "arm", None)
        if callable(driver_arm):
            _require_success(driver_arm(), "NIDAQ.arm")
        self.armed = True
        return True

    def read_counts(self, timeout: float | None = None) -> Any:
        self._ensure_connected()
        if self._uses_sync_driver():
            method = getattr(self._driver, "read_counts_binned", None)
            if callable(method):
                self.armed = False
                return method(timeout=timeout)
        sample_rate = float(self.counter_config.get("sample_rate") or self.config.get("sample_rate") or 1e6)
        samples = int(self.counter_config.get("samples") or self.config.get("samples") or 1000)
        source = self.counter_config.get("source") or self.config.get("source") or "PFI0"
        data = self._driver.get_photon_counts(sample_rate=sample_rate, num_samples=samples, source_terminal=source)
        self.armed = False
        return data.tolist() if hasattr(data, "tolist") else list(data)

    def read_counts_binned(self, timeout: float | None = None) -> Any:
        return self.read_counts(timeout=timeout)

    def read_analog(self, timeout: float | None = None) -> Any:
        self._ensure_connected()
        if self._uses_sync_driver():
            method = getattr(self._driver, "read_analog_trace", None)
            if callable(method):
                result = method(timeout=timeout)
                self.armed = False
                if isinstance(result, dict):
                    data = result.get("data")
                    if isinstance(data, dict) and "analog_trace" in data:
                        return data["analog_trace"]
                return result
        channels = self.ai_config.get("channels") or self.config.get("ai_channels") or ["ai0"]
        sample_rate = float(self.ai_config.get("sample_rate") or self.config.get("ai_sample_rate") or 1e3)
        samples = int(self.ai_config.get("samples") or self.config.get("ai_samples") or 100)
        data = self._driver.read_analog(channels, sample_rate, samples)
        self.armed = False
        return [item.tolist() if hasattr(item, "tolist") else item for item in data]

    def read_analog_traces(self, timeout: float | None = None) -> Any:
        """Read one finite AI record for each configured start trigger."""
        self._ensure_connected()
        if not self._uses_sync_driver():
            self._unsupported_sync("read_analog_traces")
        method = getattr(self._driver, "read_analog_trace", None)
        if not callable(method):
            self._unsupported_sync("read_analog_traces")
        result = method(timeout=timeout)
        self.armed = False
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, dict) and "analog_traces" in data:
                return data["analog_traces"]
        raise RuntimeError("NI sync driver did not return analog_traces")

    def read(self, timeout: float | None = None) -> Any:
        self._ensure_connected()
        method = getattr(self._driver, "read", None)
        if not callable(method):
            if self.counter_config:
                return self.read_counts(timeout=timeout)
            if self.ai_config:
                return self.read_analog(timeout=timeout)
            self._unsupported_sync("read")
        self.armed = False
        return method(timeout=timeout)

    def set_voltage(self, channel: str, voltage: float) -> float:
        self._ensure_connected()
        _require_success(self._driver.set_constant_voltage(channel, float(voltage)), "NIDAQ.set_constant_voltage")
        self.outputs[str(channel)] = float(voltage)
        return float(voltage)

    def set_ao_static(self, channel: str, voltage: float) -> bool:
        self._ensure_connected()
        method = getattr(self._driver, "set_ao_static", None)
        if callable(method):
            _require_success(method(channel, float(voltage)), "NIDAQ.set_ao_static")
        else:
            _require_success(self._driver.set_constant_voltage(channel, float(voltage)), "NIDAQ.set_constant_voltage")
        self.outputs[str(channel)] = float(voltage)
        return True

    def wait_settle(self, seconds: float) -> bool:
        self._ensure_connected()
        method = getattr(self._driver, "wait_settle", None)
        if callable(method):
            return bool(method(float(seconds)))
        import time

        time.sleep(float(seconds))
        return True

    def stop(self) -> bool:
        if self._driver is not None and hasattr(self._driver, "stop"):
            self._driver.stop()
        self.armed = False
        return False

    def _ensure_connected(self) -> None:
        if not self.connected or self._driver is None:
            raise InstrumentConnectionError(f"pycontrol NI resource '{self.name}' is not connected")

    def _unsupported_sync(self, method: str) -> None:
        raise InstrumentUnsupportedOperation(
            f"{method} requires pycontrol NI sync driver. Configure resource with driver: sync "
            "or driver_class: DataAcquisition.sync_driver.NISyncDAQDriver."
        )

    def _settings_snapshot(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "driver": self.driver_mode,
            "driver_class": None if self._driver is None else f"{self._driver.__class__.__module__}.{self._driver.__class__.__name__}",
            "counter": dict(self.counter_config),
            "ai": dict(self.ai_config),
            "trigger": dict(self.trigger_config),
            "outputs": dict(self.outputs),
            "armed": self.armed,
        }


class PycontrolAWGAdapter(_PycontrolAdapterBase):
    adapter_name = "pycontrol_awg"
    vendor = "Rigol"
    model = "DG5504 Pro"
    capability_names = {caps.WAVEFORM_GENERATOR, caps.TRIGGER_RECEIVER}

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(name, config)
        self.address = self.config.get("address")
        self.waveforms: dict[str, dict[str, Any]] = {}
        self.current_waveform: str | None = None
        self.trigger_config: dict[str, Any] = {}
        self.running = False

    def connect(self) -> None:
        driver_cls = _load_driver(self.config, "AWG.driver", "RigolDG5504Driver")
        try:
            self._driver = driver_cls(verbose=_bool_config(self.config, "verbose", False))
            _require_success(self._driver.connect(self.address), "RigolDG5504.connect")
            self.connected = True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            raise InstrumentConnectionError(f"Failed to connect pycontrol AWG resource '{self.name}': {exc}") from exc

    def upload_waveform(self, name: str, data: Any, sample_rate: float | None = None) -> dict[str, Any]:
        self._ensure_connected()
        _require_success(self._driver.upload_waveform({"name": name, "data": data}), "RigolDG5504.upload_waveform")
        self.waveforms[name] = {"sample_rate": sample_rate, "points": len(data) if hasattr(data, "__len__") else None}
        return dict(self.waveforms[name])

    def play(self, name: str) -> bool:
        self._ensure_connected()
        if name not in self.waveforms:
            raise InstrumentConfigurationError(f"Waveform '{name}' has not been uploaded to resource '{self.name}'")
        _require_success(self._driver.start(), "RigolDG5504.start")
        self.current_waveform = name
        self.running = True
        return True

    def stop(self) -> bool:
        if self.connected and self._driver is not None:
            _require_success(self._driver.stop(), "RigolDG5504.stop")
        self.running = False
        return False

    def configure_trigger_input(self, channel: str, edge: str = "rising") -> dict[str, Any]:
        self.trigger_config = {"channel": channel, "edge": edge}
        return dict(self.trigger_config)

    def arm(self) -> bool:
        self._ensure_connected()
        return True

    def trigger_snapshot(self) -> dict[str, Any]:
        return dict(self.trigger_config)

    def _ensure_connected(self) -> None:
        if not self.connected or self._driver is None:
            raise InstrumentConnectionError(f"pycontrol AWG resource '{self.name}' is not connected")

    def _settings_snapshot(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "waveforms": dict(self.waveforms),
            "current_waveform": self.current_waveform,
            "trigger": dict(self.trigger_config),
            "running": self.running,
        }


__all__ = [
    "PycontrolASGAdapter",
    "PycontrolAWGAdapter",
    "PycontrolLMXAdapter",
    "PycontrolNIAdapter",
]
