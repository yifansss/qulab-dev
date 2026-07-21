"""Procedure tree view model generation for configs and parsed procedures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProcedureTreeNode:
    label: str
    kind: str
    details: str = ""
    children: tuple["ProcedureTreeNode", ...] = field(default_factory=tuple)


def build_procedure_tree(config: dict[str, Any]) -> list[ProcedureTreeNode]:
    """Build a display tree with setup, procedure, and cleanup groups."""

    return [
        ProcedureTreeNode("setup", "setup", children=tuple(_steps_to_nodes(config.get("setup", [])))),
        ProcedureTreeNode("procedure", "procedure", children=tuple(_steps_to_nodes(config.get("procedure", [])))),
        ProcedureTreeNode("cleanup", "cleanup", children=tuple(_steps_to_nodes(config.get("cleanup", [])))),
    ]


def _steps_to_nodes(raw_steps: Any) -> list[ProcedureTreeNode]:
    if not isinstance(raw_steps, list):
        return []
    nodes: list[ProcedureTreeNode] = []
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            continue
        nodes.append(_step_to_node(raw_step))
    return nodes


def _step_to_node(raw_step: dict[str, Any]) -> ProcedureTreeNode:
    if "call" in raw_step:
        save_as = raw_step.get("save_as")
        details = f"-> {save_as}" if save_as else ""
        return ProcedureTreeNode(str(raw_step["call"]), "call", details)
    if "scan" in raw_step and isinstance(raw_step["scan"], dict):
        scan = raw_step["scan"]
        name = str(scan.get("name") or "scan")
        return ProcedureTreeNode(
            f"scan {name}",
            "scan",
            _scan_values_summary(scan.get("values")),
            tuple(_steps_to_nodes(scan.get("body", []))),
        )
    if "average" in raw_step and isinstance(raw_step["average"], dict):
        average = raw_step["average"]
        name = str(average.get("name") or "average")
        return ProcedureTreeNode(
            f"average {name}",
            "average",
            f"count={average.get('count', 1)}",
            tuple(_steps_to_nodes(average.get("body", []))),
        )
    if "measurement" in raw_step and isinstance(raw_step["measurement"], dict):
        measurement = raw_step["measurement"]
        name = str(measurement.get("name") or "measurement")
        return ProcedureTreeNode(
            f"measurement {name}",
            "measurement",
            "",
            tuple(_steps_to_nodes(measurement.get("body", []))),
        )
    if "run" in raw_step and isinstance(raw_step["run"], dict):
        run = raw_step["run"]
        name = str(run.get("name") or "run")
        details = f"timeout={run['timeout_s']}s" if "timeout_s" in run else ""
        return ProcedureTreeNode(
            f"run {name}",
            "run",
            details,
            tuple(_steps_to_nodes(run.get("steps", run.get("body", [])))),
        )
    if "cleanup" in raw_step and isinstance(raw_step["cleanup"], dict):
        cleanup = raw_step["cleanup"]
        name = str(cleanup.get("name") or "cleanup")
        return ProcedureTreeNode(
            f"cleanup {name}",
            "cleanup",
            "",
            tuple(_steps_to_nodes(cleanup.get("steps", cleanup.get("body", [])))),
        )
    return ProcedureTreeNode("unsupported", "unknown", ", ".join(raw_step))


def _scan_values_summary(values: Any) -> str:
    if isinstance(values, dict):
        if {"start", "stop", "points"} <= set(values):
            return f"{values['start']} -> {values['stop']}, points={values['points']}"
        if {"start", "stop", "step"} <= set(values):
            return f"{values['start']} -> {values['stop']}, step={values['step']}"
        return ", ".join(f"{key}={value}" for key, value in values.items())
    if isinstance(values, list):
        preview = ", ".join(str(item) for item in values[:4])
        suffix = ", ..." if len(values) > 4 else ""
        return f"[{preview}{suffix}] ({len(values)} values)"
    return ""
