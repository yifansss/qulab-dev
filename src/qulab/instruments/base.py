"""Base adapter classes and instrument errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class InstrumentError(RuntimeError):
    """Base class for adapter errors."""


class InstrumentConfigurationError(InstrumentError):
    """Raised when an adapter config is invalid."""


class InstrumentConnectionError(InstrumentError):
    """Raised when an adapter cannot connect to hardware."""


class InstrumentSafetyError(InstrumentError):
    """Raised when a requested hardware action is blocked by safety policy."""


class InstrumentTimeoutError(InstrumentError):
    """Raised when hardware does not respond within the expected time."""


class InstrumentUnsupportedOperation(InstrumentError):
    """Raised when a capability method is unavailable."""


@dataclass
class InstrumentAdapter:
    """Minimal common adapter interface."""

    name: str
    adapter: str
    simulation: bool = True
    connected: bool = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "connected": self.connected, "simulation": self.simulation}

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "adapter": self.adapter,
            "connected": self.connected,
            "simulation": self.simulation,
            "capabilities": sorted(self.capabilities()),
            "settings": {},
        }

    def capabilities(self) -> set[str]:
        return set()
