"""Instrument adapter registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .adapters.mock import MockAnalogIO, MockDAQCounter, MockMicrowaveSource, MockPulseSequencer
from .adapters.pycontrol import PycontrolASGAdapter, PycontrolAWGAdapter, PycontrolLMXAdapter, PycontrolNIAdapter
from .base import InstrumentConfigurationError


class InstrumentRegistry:
    """Create named resources from config mappings."""

    def __init__(self, register_defaults: bool = True) -> None:
        self._factories: dict[str, Callable[[str, dict[str, Any]], Any]] = {}
        if register_defaults:
            self.register_defaults()

    def register(self, adapter_name: str, factory: Callable[[str, dict[str, Any]], Any]) -> None:
        self._factories[adapter_name] = factory

    def register_defaults(self) -> None:
        self.register("mock_microwave", MockMicrowaveSource)
        self.register("mock_microwave_source", MockMicrowaveSource)
        self.register("mock_pulse_sequencer", MockPulseSequencer)
        self.register("mock_asg", MockPulseSequencer)
        self.register("mock_daq_counter", MockDAQCounter)
        self.register("mock_daq", MockDAQCounter)
        self.register("mock_analog_io", MockAnalogIO)
        self.register("pycontrol_asg", PycontrolASGAdapter)
        self.register("pycontrol_ni", PycontrolNIAdapter)
        self.register("pycontrol_lmx", PycontrolLMXAdapter)
        self.register("pycontrol_awg", PycontrolAWGAdapter)

    def create(self, resource_name: str, config: dict[str, Any]) -> Any:
        adapter_name = config.get("adapter") or config.get("adaptor")
        if not adapter_name:
            raise InstrumentConfigurationError(f"Resource '{resource_name}' is missing adapter")
        if adapter_name not in self._factories:
            raise InstrumentConfigurationError(f"Unknown adapter '{adapter_name}' for resource '{resource_name}'")
        return self._factories[adapter_name](resource_name, config)
