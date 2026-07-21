"""Stable sequence-generation errors and validation issues."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SequenceGenerationIssue:
    severity: str
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "context": _safe(self.context),
        }


class SequenceGenerationError(ValueError):
    """Fail-closed error with a stable machine-readable code."""

    def __init__(self, code: str, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})

    def as_issue(self) -> SequenceGenerationIssue:
        return SequenceGenerationIssue("error", self.code, str(self), self.context)


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
