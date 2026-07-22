"""Stable errors and validation diagnostics for analysis modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AnalysisValidationIssue:
    severity: str
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {"severity": self.severity, "code": self.code, "message": self.message}
        if self.context:
            result["context"] = dict(self.context)
        return result


class AnalysisError(Exception):
    def __init__(self, code: str, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or {}

    def as_issue(self, severity: str = "error") -> AnalysisValidationIssue:
        return AnalysisValidationIssue(severity, self.code, self.message, dict(self.context))
