"""Transactional, offline-only candidate configuration validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import yaml

from qulab.instruments.registry import InstrumentRegistry
from qulab.paths import resolve_project_path
from qulab.sequence_generation import SequenceGenerationError, prepare_and_parse_experiment_config

from .diagnostics import ConfigDiagnostic, ConfigLoadResult, ConfigPath
from .loader import _convert_numeric_strings
from .parser import parse_experiment_config
from .source_map import SourceLocation, compose_source_map, nearest_location


_STEP_KINDS = {"call", "scan", "average", "measurement", "run", "wait", "cleanup", "sequence_sweep"}
_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def validate_config_candidate(path: str | Path, *, registry: InstrumentRegistry | None = None) -> ConfigLoadResult:
    candidate_path = Path(path)
    resolved = resolve_project_path(candidate_path) or candidate_path
    diagnostics: list[ConfigDiagnostic] = []
    try:
        raw = resolved.read_bytes()
    except (OSError, PermissionError) as exc:
        return ConfigLoadResult(candidate_path, None, None, (_diagnostic(
            "error", "yaml_file_unreadable", f"Cannot read configuration: {exc}", (), str(resolved), None,
            "Check that the file exists and is readable.",
        ),), False)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return ConfigLoadResult(candidate_path, None, None, (_diagnostic(
            "error", "yaml_encoding_error", "Configuration is not valid UTF-8.", (), str(resolved),
            SourceLocation(exc.start + 1, 1), "Save the file as UTF-8.",
        ),), False)
    if not text.strip():
        return ConfigLoadResult(candidate_path, None, None, (_diagnostic(
            "error", "yaml_empty", "Configuration file is empty.", (), str(resolved), SourceLocation(1, 1),
            "Add a top-level YAML mapping.",
        ),), False)
    try:
        source_map, duplicates = compose_source_map(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = SourceLocation(mark.line + 1, mark.column + 1) if mark is not None else None
        excerpt = _excerpt(text, location.line if location else None)
        message = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        return ConfigLoadResult(candidate_path, None, None, (_diagnostic(
            "error", "yaml_syntax_error", f"Invalid YAML: {message}", (), str(resolved), location,
            "Fix the YAML syntax near this location.", excerpt=excerpt,
        ),), False)
    for duplicate in duplicates:
        diagnostics.append(_diagnostic(
            "error", "yaml_duplicate_key", f"Duplicate mapping key {duplicate.key!r}.", duplicate.path,
            str(resolved), duplicate.location, "Remove or rename one of the duplicate keys.",
        ))
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:  # compose above normally catches this; keep the boundary fail-closed.
        loaded = None
    if loaded is None:
        diagnostics.append(_diagnostic("error", "yaml_empty", "Configuration contains no YAML document.", (),
                                       str(resolved), SourceLocation(1, 1), "Add a top-level YAML mapping."))
        return ConfigLoadResult(candidate_path, None, None, tuple(diagnostics), False)
    if not isinstance(loaded, dict):
        diagnostics.append(_at("error", "config_top_level_type", "Top level must be a mapping.", (), resolved,
                               source_map, "Use named sections such as resources and procedure."))
        return ConfigLoadResult(candidate_path, None, None, tuple(diagnostics), False)
    config = _convert_numeric_strings(loaded)
    instrument_registry = registry or InstrumentRegistry()
    _validate_structure(config, resolved, source_map, diagnostics)
    _validate_references(config, instrument_registry, resolved, source_map, diagnostics)
    parsed = None
    if not any(item.severity == "error" for item in diagnostics):
        try:
            if config.get("sequence_plans"):
                parsed = prepare_and_parse_experiment_config(config, instrument_registry=instrument_registry)
            else:
                parsed = parse_experiment_config(config, registry=instrument_registry)
            for issue in parsed.validation.issues:
                diagnostics.append(_at(issue.severity, issue.code, issue.message, (), resolved, source_map, None))
        except SequenceGenerationError as exc:
            diagnostics.append(_at("error", exc.code, str(exc), ("sequence_plans",), resolved, source_map,
                                   "Review the sequence plan and provider settings."))
        except Exception as exc:
            diagnostics.append(_at("error", _exception_code(exc), str(exc), _path_from_message(str(exc)),
                                   resolved, source_map, "Correct the indicated configuration value."))
    return ConfigLoadResult(candidate_path, config, parsed, tuple(_dedupe(diagnostics)), False)


def _validate_structure(config: dict[str, Any], source: Path, locations: dict[ConfigPath, SourceLocation], out: list[ConfigDiagnostic]) -> None:
    for section in ("resources", "parameters", "sequence_bundles", "sequence_plans", "sync", "analysis", "storage"):
        value = config.get(section)
        if value is not None and not isinstance(value, dict):
            out.append(_at("error", "config_section_type", f"{section} must be a mapping.", (section,), source, locations,
                           "Replace this value with a YAML mapping."))
    resources = config.get("resources", {})
    if isinstance(resources, dict):
        for name, value in resources.items():
            if not isinstance(value, dict):
                out.append(_at("error", "config_section_type", f"Resource '{name}' must be a mapping.",
                               ("resources", name), source, locations, "Declare adapter and resource options as keys."))
    for section in ("setup", "procedure", "cleanup"):
        steps = config.get(section, [])
        if steps is None:
            continue
        if not isinstance(steps, list):
            out.append(_at("error", "config_section_type", f"{section} must be a list.", (section,), source, locations,
                           "Use '-' entries for workflow steps."))
            continue
        _validate_steps(steps, (section,), source, locations, out)


def _validate_steps(steps: list[Any], path: ConfigPath, source: Path, locations: dict[ConfigPath, SourceLocation], out: list[ConfigDiagnostic]) -> None:
    for index, step in enumerate(steps):
        step_path = (*path, index)
        if not isinstance(step, dict):
            out.append(_at("error", "workflow_step_type", "Workflow step must be a mapping.", step_path, source, locations,
                           "Use a call, scan, average, measurement, run, wait, cleanup, or sequence_sweep mapping."))
            continue
        kinds = [key for key in _STEP_KINDS if key in step]
        if len(kinds) > 1:
            out.append(_at("error", "workflow_step_ambiguous", f"Step declares multiple kinds: {', '.join(sorted(kinds))}.",
                           step_path, source, locations, "Split these into separate workflow steps."))
            continue
        if not kinds:
            out.append(_at("error", "workflow_step_unknown", f"Unknown workflow step keys: {', '.join(map(str, step))}.",
                           step_path, source, locations, "Choose one supported step kind."))
            continue
        if "enabled" in step and not isinstance(step["enabled"], bool):
            out.append(_at("error", "workflow_field_type", "enabled must be a boolean.", (*step_path, "enabled"), source, locations,
                           "Use true or false."))
        kind = kinds[0]
        payload = step[kind]
        if kind == "call":
            if not isinstance(payload, str) or payload.count(".") != 1:
                out.append(_at("error", "workflow_value_invalid", "call must be resource.method.", (*step_path, "call"), source, locations,
                               "For example: daq.read_counts"))
            if "args" in step and not isinstance(step["args"], dict):
                out.append(_at("error", "workflow_field_type", "call args must be a mapping.", (*step_path, "args"), source, locations,
                               "Use argument-name: value pairs."))
            if "args_list" in step and not isinstance(step["args_list"], list):
                out.append(_at("error", "workflow_field_type", "args_list must be a list.", (*step_path, "args_list"), source, locations, None))
            if "save_as" in step and not isinstance(step["save_as"], str):
                out.append(_at("error", "workflow_field_type", "save_as must be a string.", (*step_path, "save_as"), source, locations, None))
        elif kind == "wait":
            duration = payload if isinstance(payload, (int, float)) and not isinstance(payload, bool) else payload.get("duration_s", payload.get("seconds")) if isinstance(payload, dict) else None
            if not isinstance(duration, (int, float)) or isinstance(duration, bool):
                out.append(_at("error", "workflow_field_type", "wait duration_s must be numeric.", (*step_path, "wait"), source, locations, "Provide a duration in seconds."))
            elif duration <= 0:
                out.append(_at("error", "workflow_value_invalid", "wait duration must be greater than zero.", (*step_path, "wait"), source, locations, None))
        else:
            if not isinstance(payload, dict):
                out.append(_at("error", "workflow_field_type", f"{kind} must be a mapping.", (*step_path, kind), source, locations, None))
                continue
            child_key = "steps" if kind in {"run", "cleanup"} and "steps" in payload else "body"
            if kind == "scan":
                if not isinstance(payload.get("name"), str) or not payload.get("name"):
                    out.append(_at("error", "workflow_field_missing", "scan.name is required.", (*step_path, kind, "name"), source, locations, None))
                _validate_scan_values(payload.get("values"), (*step_path, kind, "values"), source, locations, out)
            if kind == "average":
                count = payload.get("count", 1)
                if not isinstance(count, int) or isinstance(count, bool):
                    out.append(_at("error", "workflow_field_type", "average.count must be an integer.", (*step_path, kind, "count"), source, locations, None))
                elif count <= 0:
                    out.append(_at("error", "workflow_value_invalid", "average.count must be greater than zero.", (*step_path, kind, "count"), source, locations, None))
            if kind == "run" and "timeout_s" in payload:
                timeout = payload["timeout_s"]
                if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
                    out.append(_at("error", "workflow_field_type", "run.timeout_s must be numeric.", (*step_path, kind, "timeout_s"), source, locations, None))
                elif timeout <= 0:
                    out.append(_at("error", "workflow_value_invalid", "run.timeout_s must be greater than zero.", (*step_path, kind, "timeout_s"), source, locations, None))
            children = payload.get(child_key, [])
            if not isinstance(children, list):
                out.append(_at("error", "workflow_field_type", f"{kind}.{child_key} must be a list.", (*step_path, kind, child_key), source, locations, None))
            else:
                _validate_steps(children, (*step_path, kind, child_key), source, locations, out)


def _validate_scan_values(value: Any, path: ConfigPath, source: Path, locations: dict[ConfigPath, SourceLocation], out: list[ConfigDiagnostic]) -> None:
    valid = False
    if isinstance(value, list):
        valid = bool(value)
    elif isinstance(value, dict):
        if {"start", "stop", "points"} <= value.keys():
            valid = isinstance(value["points"], int) and not isinstance(value["points"], bool) and value["points"] > 0
        elif {"start", "stop", "step"} <= value.keys():
            valid = isinstance(value["step"], (int, float)) and not isinstance(value["step"], bool) and value["step"] != 0
    if not valid:
        out.append(_at("error", "workflow_value_invalid", "scan.values must be a non-empty list, positive-point linspace, or non-zero-step range.", path, source, locations, None))


def _validate_references(config: dict[str, Any], registry: InstrumentRegistry, source: Path, locations: dict[ConfigPath, SourceLocation], out: list[ConfigDiagnostic]) -> None:
    resources = config.get("resources", {}) if isinstance(config.get("resources", {}), dict) else {}
    for name, raw in resources.items():
        if not isinstance(raw, dict):
            continue
        adapter = raw.get("adapter") or raw.get("adaptor")
        if not adapter:
            out.append(_at("error", "resource_missing_adapter", f"Resource '{name}' is missing adapter.", ("resources", name), source, locations, None))
        elif not registry.has_adapter(str(adapter)):
            out.append(_at("error", "resource_adapter_unknown", f"Unknown adapter '{adapter}' for resource '{name}'.", ("resources", name, "adapter"), source, locations, None))
    parameters = set(config.get("parameters", {})) if isinstance(config.get("parameters"), dict) else set()
    for section in ("setup", "procedure", "cleanup"):
        steps = config.get(section, [])
        if isinstance(steps, list):
            _validate_step_refs(steps, (section,), resources, parameters, registry, source, locations, out)


def _validate_step_refs(steps: list[Any], path: ConfigPath, resources: dict[str, Any], scope: set[str], registry: InstrumentRegistry, source: Path, locations: dict[ConfigPath, SourceLocation], out: list[ConfigDiagnostic]) -> None:
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        step_path = (*path, index)
        call = step.get("call")
        if isinstance(call, str) and "." in call:
            resource, method = call.split(".", 1)
            if resource not in resources:
                out.append(_at("error", "action_resource_unknown", f"Action references unknown resource '{resource}'.", (*step_path, "call"), source, locations, None))
            else:
                raw = resources[resource]
                adapter = raw.get("adapter") if isinstance(raw, dict) else None
                adapter_type = registry.adapter_type(str(adapter)) if adapter and registry.has_adapter(str(adapter)) else None
                capabilities = raw.get("capabilities", ()) if isinstance(raw, dict) else ()
                is_bundle_runtime_action = (
                    method == "load_sequence_from_bundle" and "pulse_sequencer" in capabilities
                )
                if adapter_type is not None and not is_bundle_runtime_action and not callable(getattr(adapter_type, method, None)):
                    out.append(_at("error", "action_method_unknown", f"Adapter '{adapter}' does not declare callable method '{method}'.", (*step_path, "call"), source, locations, None))
            for arg, value in (step.get("args") or {}).items() if isinstance(step.get("args", {}), dict) else ():
                _check_refs(value, (*step_path, "args", arg), scope, source, locations, out)
        for kind in ("scan", "average", "measurement", "run", "cleanup"):
            payload = step.get(kind)
            if isinstance(payload, dict):
                child_scope = set(scope)
                if kind == "scan" and isinstance(payload.get("name"), str):
                    child_scope.add(payload["name"])
                key = "steps" if kind in {"run", "cleanup"} and "steps" in payload else "body"
                children = payload.get(key, [])
                if isinstance(children, list):
                    _validate_step_refs(children, (*step_path, kind, key), resources, child_scope, registry, source, locations, out)


def _check_refs(value: Any, path: ConfigPath, scope: set[str], source: Path, locations: dict[ConfigPath, SourceLocation], out: list[ConfigDiagnostic]) -> None:
    if isinstance(value, str) and value.startswith("${"):
        match = _REF.fullmatch(value)
        if not match or match.group(1) not in scope:
            out.append(_at("error", "parameter_reference_unresolved", f"Unresolved or out-of-scope parameter reference: {value}", path, source, locations, "Choose a parameter visible in this workflow scope."))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_refs(item, (*path, index), scope, source, locations, out)
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_refs(item, (*path, key), scope, source, locations, out)


def _at(severity: str, code: str, message: str, path: ConfigPath, source: Path, locations: dict[ConfigPath, SourceLocation], hint: str | None) -> ConfigDiagnostic:
    return _diagnostic(severity, code, message, path, str(source), nearest_location(locations, path), hint,
                       workflow_path=path if path and path[0] in {"setup", "procedure", "cleanup"} else None)


def _diagnostic(severity: str, code: str, message: str, path: ConfigPath, source: str, location: SourceLocation | None, hint: str | None, *, workflow_path: ConfigPath | None = None, excerpt: str | None = None) -> ConfigDiagnostic:
    return ConfigDiagnostic(severity, code, message, path, workflow_path, source,
                            location.line if location else None, location.column if location else None, hint, (), excerpt)  # type: ignore[arg-type]


def _exception_code(exc: Exception) -> str:
    message = str(exc).lower()
    if "missing adapter" in message:
        return "resource_missing_adapter"
    if "unknown adapter" in message:
        return "resource_adapter_unknown"
    if "must be" in message:
        return "workflow_value_invalid"
    return "config_preflight_error"


def _path_from_message(message: str) -> ConfigPath:
    match = re.search(r"\b(setup|procedure|cleanup)(?:\[(\d+)\])?", message)
    if not match:
        return ()
    return (match.group(1),) + ((int(match.group(2)),) if match.group(2) is not None else ())


def _excerpt(text: str, line: int | None) -> str | None:
    if line is None:
        return None
    lines = text.splitlines()
    return lines[line - 1].strip()[:160] if 0 < line <= len(lines) else None


def _dedupe(items: Iterable[ConfigDiagnostic]) -> list[ConfigDiagnostic]:
    result: list[ConfigDiagnostic] = []
    seen: set[tuple[Any, ...]] = set()
    for item in items:
        key = (item.severity, item.code, item.config_path, item.message)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
