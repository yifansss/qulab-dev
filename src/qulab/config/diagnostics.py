"""Structured, GUI-independent diagnostics for experiment configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


ConfigPathPart = str | int
ConfigPath = tuple[ConfigPathPart, ...]
Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class ConfigDiagnostic:
    severity: Severity
    code: str
    message: str
    config_path: ConfigPath = ()
    workflow_path: ConfigPath | None = None
    source_file: str | None = None
    line: int | None = None
    column: int | None = None
    hint: str | None = None
    related_paths: tuple[ConfigPath, ...] = ()
    excerpt: str | None = None

    @property
    def location(self) -> str:
        path = _format_path(self.config_path)
        source = self.source_file or ""
        if self.line is not None:
            source += f":{self.line}"
            if self.column is not None:
                source += f":{self.column}"
        return " · ".join(part for part in (source, path) if part)


@dataclass(frozen=True)
class ConfigLoadResult:
    candidate_path: Path
    candidate_config: dict[str, Any] | None
    parsed: Any | None
    diagnostics: tuple[ConfigDiagnostic, ...] = field(default_factory=tuple)
    activated: bool = False

    @property
    def errors(self) -> tuple[ConfigDiagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == "error")

    @property
    def warnings(self) -> tuple[ConfigDiagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == "warning")

    @property
    def ok(self) -> bool:
        return not self.errors


def _format_path(path: ConfigPath) -> str:
    result = ""
    for part in path:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += ("." if result else "") + part
    return result
