"""Config parsing and validation exceptions."""

from __future__ import annotations


class ConfigError(ValueError):
    """Base class for invalid experiment configuration."""


class ConfigLoadError(ConfigError):
    """Raised when a YAML or dict config cannot be loaded."""


class ConfigValidationError(ConfigError):
    """Raised when a parsed config fails preflight validation."""
