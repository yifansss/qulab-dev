"""Helpers for integrating analysis diagnostics with existing preflight."""

from __future__ import annotations

from typing import Iterable

from qulab.core import ActionStep, Procedure


def collect_known_raw_keys(procedure: Procedure) -> set[str]:
    keys: set[str] = set()
    for step in _walk([*procedure.setup, *procedure.body, *procedure.cleanup]):
        if isinstance(step, ActionStep) and step.save_as:
            keys.add(step.save_as)
    return keys


def _walk(steps: Iterable[object]):
    for step in steps:
        yield step
        body = getattr(step, "body", None)
        if body:
            yield from _walk(body)
