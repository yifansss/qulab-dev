"""Operator-facing parameter discovery and update helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .models import parse_parameter_value, update_config_value


PathPart = str | int


@dataclass(frozen=True)
class OperatorParameterSpec:
    name: str
    label: str
    source: str
    value: object
    unit: str | None = None
    widget: str = "auto"
    minimum: float | None = None
    maximum: float | None = None
    choices: list[object] | None = None
    readonly: bool = False
    warning: str | None = None
    path: tuple[PathPart, ...] | None = field(default=None, repr=False, compare=False)


def discover_operator_parameters(workflow_model: Any, raw_config: dict[str, Any]) -> list[OperatorParameterSpec]:
    """Discover quick-edit parameters from explicit declarations and common config fields."""

    specs: list[OperatorParameterSpec] = []
    seen_sources: set[str] = set()
    for declaration in _explicit_declarations(raw_config):
        spec = _spec_from_declaration(declaration, raw_config)
        specs.append(spec)
        seen_sources.add(spec.source)

    for spec in _auto_specs(raw_config):
        if spec.source in seen_sources:
            continue
        specs.append(spec)
        seen_sources.add(spec.source)
    return specs


def apply_operator_parameter(
    workflow_model: Any,
    raw_config: dict[str, Any],
    spec_name: str,
    value: object,
) -> None:
    """Apply an operator parameter update to the same raw config used by the workflow tree."""

    specs = discover_operator_parameters(workflow_model, raw_config)
    by_name = {spec.name: spec for spec in specs}
    spec = by_name.get(spec_name)
    if spec is None:
        raise KeyError(f"Unknown operator parameter: {spec_name}")
    if spec.path is None:
        raise KeyError(f"Operator parameter source cannot be resolved: {spec.source}")
    if spec.readonly:
        raise ValueError(f"Operator parameter is read-only: {spec.name}")
    update_config_value(raw_config, spec.path, _coerce_value(spec, value))
    if hasattr(workflow_model, "config"):
        workflow_model.config = raw_config


def _explicit_declarations(raw_config: dict[str, Any]) -> list[dict[str, Any]]:
    declarations = raw_config.get("operator_parameters") or []
    return [item for item in declarations if isinstance(item, dict)]


def _spec_from_declaration(declaration: dict[str, Any], raw_config: dict[str, Any]) -> OperatorParameterSpec:
    source = str(declaration.get("source") or "")
    path, warning = _resolve_source(raw_config, source)
    value = _get_path(raw_config, path) if path is not None and _path_exists(raw_config, path) else ""
    return OperatorParameterSpec(
        name=str(declaration.get("name") or _source_name(source)),
        label=str(declaration.get("label") or _source_label(source)),
        source=source,
        value=value,
        unit=declaration.get("unit"),
        widget=str(declaration.get("widget") or "auto"),
        minimum=declaration.get("minimum", declaration.get("min")),
        maximum=declaration.get("maximum", declaration.get("max")),
        choices=list(declaration["choices"]) if isinstance(declaration.get("choices"), list) else None,
        readonly=bool(declaration.get("readonly", False)),
        warning=warning or declaration.get("warning"),
        path=path,
    )


def _auto_specs(raw_config: dict[str, Any]) -> list[OperatorParameterSpec]:
    specs: list[OperatorParameterSpec] = []
    specs.extend(_auto_sequence_plan_specs(raw_config))
    specs.extend(_auto_scan_specs(raw_config))
    specs.extend(_auto_average_specs(raw_config))
    specs.extend(_auto_call_arg_specs(raw_config))
    specs.extend(_auto_sequence_load_specs(raw_config))
    specs.extend(_auto_resource_sequence_specs(raw_config))
    specs.extend(_auto_storage_specs(raw_config))
    return _dedupe_names(specs)


def _auto_sequence_plan_specs(raw_config: dict[str, Any]) -> list[OperatorParameterSpec]:
    plans = raw_config.get("sequence_plans", {})
    if not isinstance(plans, dict):
        return []
    output = []
    for plan_id, plan in plans.items():
        parameters = plan.get("parameters", {}) if isinstance(plan, dict) else {}
        if not isinstance(parameters, dict):
            continue
        for name, parameter in parameters.items():
            if not isinstance(parameter, dict):
                continue
            mode = str(parameter.get("mode", "fixed"))
            fields = ("value",) if mode == "fixed" else ("start", "stop", "points") if mode == "linspace" else ("start", "stop", "step") if mode == "range" else ("values",)
            for field_name in fields:
                if field_name not in parameter:
                    continue
                value = parameter[field_name]
                path = ("sequence_plans", plan_id, "parameters", name, field_name)
                output.append(OperatorParameterSpec(
                    name=_snake(f"{plan_id}_{name}_{field_name}"), label=f"{plan_id} · {name} {field_name}",
                    source=".".join(path), value=value, unit=parameter.get("unit"),
                    widget="integer" if field_name == "points" else "string" if isinstance(value, list) else "number",
                    minimum=1 if field_name == "points" else None, path=path,
                ))
    return output


def _auto_scan_specs(raw_config: dict[str, Any]) -> list[OperatorParameterSpec]:
    specs: list[OperatorParameterSpec] = []
    for path, scan in _iter_named_steps(raw_config, "scan"):
        name = str(scan.get("name") or "scan")
        values = scan.get("values")
        values_path = (*path, "scan", "values")
        if isinstance(values, dict):
            for key in ("start", "stop", "points", "step"):
                if key not in values:
                    continue
                source = f"procedure.scan[{name}].values.{key}"
                specs.append(
                    OperatorParameterSpec(
                        name=_snake(f"{name}_{key}"),
                        label=f"{name} {key}",
                        source=source,
                        value=values[key],
                        widget="integer" if key == "points" else "number",
                        minimum=1 if key == "points" else None,
                        path=(*values_path, key),
                    )
                )
        elif isinstance(values, list):
            specs.append(
                OperatorParameterSpec(
                    name=_snake(f"{name}_values"),
                    label=f"{name} values",
                    source=f"procedure.scan[{name}].values",
                    value=values,
                    widget="string",
                    path=values_path,
                )
            )
    return specs


def _auto_average_specs(raw_config: dict[str, Any]) -> list[OperatorParameterSpec]:
    specs: list[OperatorParameterSpec] = []
    for path, average in _iter_named_steps(raw_config, "average"):
        name = str(average.get("name") or "average")
        if "count" in average:
            specs.append(
                OperatorParameterSpec(
                    name=_snake(name if name.endswith("count") else f"{name}_count"),
                    label=f"{name} count",
                    source=f"procedure.average[{name}].count",
                    value=average["count"],
                    widget="integer",
                    minimum=1,
                    path=(*path, "average", "count"),
                )
            )
    return specs


def _auto_call_arg_specs(raw_config: dict[str, Any]) -> list[OperatorParameterSpec]:
    specs: list[OperatorParameterSpec] = []
    for path, step, section in _iter_call_steps(raw_config):
        action = str(step.get("call") or "")
        args = step.get("args")
        if not action or not isinstance(args, dict):
            continue
        for arg_name, value in args.items():
            if _is_sequence_loader_arg(action, str(arg_name)):
                continue
            if not _is_supported_scalar(value):
                continue
            source = f"{section}.call[{action}].args.{arg_name}"
            specs.append(
                OperatorParameterSpec(
                    name=_snake(f"{action.split('.')[0]}_{arg_name}"),
                    label=f"{action} {arg_name}",
                    source=source,
                    value=value,
                    widget=_widget_for_value(value),
                    path=(*path, "args", arg_name),
                )
            )
    return specs


def _auto_resource_sequence_specs(raw_config: dict[str, Any]) -> list[OperatorParameterSpec]:
    resources = raw_config.get("resources", {})
    specs: list[OperatorParameterSpec] = []
    if not isinstance(resources, dict):
        return specs
    for name, resource in resources.items():
        if not isinstance(resource, dict):
            continue
        capabilities = tuple(str(item) for item in resource.get("capabilities", ()))
        adapter = str(resource.get("adapter") or "")
        if "sequence_file" not in resource and "pulse_sequencer" not in capabilities and "asg" not in adapter.lower():
            continue
        specs.append(
            OperatorParameterSpec(
                name=_snake(f"{name}_sequence_file"),
                label=f"{name} sequence file",
                source=f"resources.{name}.sequence_file",
                value=resource.get("sequence_file", ""),
                widget="file_picker",
                path=("resources", name, "sequence_file"),
            )
        )
    return specs


def _auto_sequence_load_specs(raw_config: dict[str, Any]) -> list[OperatorParameterSpec]:
    specs: list[OperatorParameterSpec] = []
    occurrence = 0
    for path, step, section in _iter_call_steps(raw_config):
        action = str(step.get("call") or "")
        resource, _, method = action.partition(".")
        if method != "load_sequence" or "asg" not in resource.lower():
            continue
        args = step.get("args")
        if not isinstance(args, dict):
            continue
        sequence_file = args.get("sequence_file") or args.get("path") or args.get("sequence_path")
        if not sequence_file:
            continue
        occurrence += 1
        path_label = "_".join(str(part) for part in path)
        location = "/".join(str(part) for part in path)
        specs.append(
            OperatorParameterSpec(
                name=_snake(f"{resource}_load_sequence_{occurrence}_{path_label}_file"),
                label=f"{resource}.load_sequence #{occurrence} file - {location}",
                source=f"workflow.{section}.{'/'.join(str(part) for part in path)}.call[{action}].args.sequence_file",
                value=sequence_file,
                widget="file_picker",
                path=(*path, "args", "sequence_file"),
            )
        )
    return specs


def _auto_storage_specs(raw_config: dict[str, Any]) -> list[OperatorParameterSpec]:
    storage = raw_config.get("storage", {})
    if not isinstance(storage, dict):
        return []
    if "backends" in storage:
        value = storage.get("backends")
        return [
            OperatorParameterSpec(
                name="storage_backends",
                label="storage backends",
                source="storage.backends",
                value=value,
                widget="string",
                path=("storage", "backends"),
            )
        ]
    if "backend" in storage:
        return [
            OperatorParameterSpec(
                name="storage_backend",
                label="storage backend",
                source="storage.backend",
                value=storage.get("backend"),
                widget="string",
                path=("storage", "backend"),
            )
        ]
    return [
        OperatorParameterSpec(
            name="storage_backends",
            label="storage backends",
            source="storage.backends",
            value=[],
            widget="string",
            path=("storage", "backends"),
        )
    ]


def _resolve_source(raw_config: dict[str, Any], source: str) -> tuple[tuple[PathPart, ...] | None, str | None]:
    if not source:
        return None, "Missing operator parameter source."
    if source in {"storage.backend", "storage.backends"}:
        path = tuple(source.split("."))
        return path, None if _path_exists(raw_config, path) else f"Source does not exist yet: {source}"
    if source.startswith("resources."):
        path = tuple(source.split("."))
        return path, None if _path_exists(raw_config, path) else f"Source does not exist yet: {source}"
    if source.startswith("sequence_plans."):
        path = tuple(source.split("."))
        return path, None if _path_exists(raw_config, path) else f"Sequence plan source not found: {source}"
    match = re.fullmatch(r"(setup|procedure|cleanup)\.call\[([^\]]+)\]\.args\.([A-Za-z_][A-Za-z0-9_]*)", source)
    if match:
        section, action, arg = match.groups()
        for path, step, step_section in _iter_call_steps(raw_config):
            if step_section == section and step.get("call") == action and isinstance(step.get("args"), dict) and arg in step["args"]:
                return (*path, "args", arg), None
        return None, f"Call argument source not found: {source}"
    match = re.fullmatch(r"procedure\.scan\[([^\]]+)\]\.values(?:\.([A-Za-z_][A-Za-z0-9_]*))?", source)
    if match:
        scan_name, field_name = match.groups()
        for path, scan in _iter_named_steps(raw_config, "scan"):
            if str(scan.get("name") or "scan") == scan_name:
                resolved = (*path, "scan", "values", field_name) if field_name else (*path, "scan", "values")
                return resolved, None if _path_exists(raw_config, resolved) else f"Scan source not found: {source}"
        return None, f"Scan source not found: {source}"
    match = re.fullmatch(r"procedure\.average\[([^\]]+)\]\.count", source)
    if match:
        average_name = match.group(1)
        for path, average in _iter_named_steps(raw_config, "average"):
            if str(average.get("name") or "average") == average_name:
                return (*path, "average", "count"), None
        return None, f"Average source not found: {source}"
    return None, f"Unsupported operator parameter source: {source}"


def _iter_named_steps(raw_config: dict[str, Any], kind: str):
    for path, step, _section in _iter_steps(raw_config):
        payload = step.get(kind)
        if isinstance(payload, dict):
            yield path, payload


def _iter_call_steps(raw_config: dict[str, Any]):
    for path, step, section in _iter_steps(raw_config):
        if "call" in step:
            yield path, step, section


def _iter_steps(raw_config: dict[str, Any]):
    for section in ("setup", "procedure", "cleanup"):
        steps = raw_config.get(section, [])
        if isinstance(steps, list):
            yield from _walk_steps(steps, (section,), section)


def _walk_steps(steps: list[Any], path: tuple[PathPart, ...], section: str):
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        step_path = (*path, index)
        yield step_path, step, section
        for kind in ("scan", "average", "measurement"):
            payload = step.get(kind)
            if isinstance(payload, dict) and isinstance(payload.get("body"), list):
                yield from _walk_steps(payload["body"], (*step_path, kind, "body"), section)
        run = step.get("run")
        if isinstance(run, dict):
            child_steps = run.get("steps", run.get("body", []))
            if isinstance(child_steps, list):
                yield from _walk_steps(child_steps, (*step_path, "run", "steps"), section)
        cleanup = step.get("cleanup")
        if isinstance(cleanup, dict):
            child_steps = cleanup.get("steps", cleanup.get("body", []))
            if isinstance(child_steps, list):
                yield from _walk_steps(child_steps, (*step_path, "cleanup", "steps"), section)


def _coerce_value(spec: OperatorParameterSpec, value: object) -> object:
    if not isinstance(value, str):
        if spec.source == "storage.backends" and isinstance(value, tuple):
            return list(value)
        return value
    if spec.source == "storage.backends":
        return [item.strip() for item in value.split(",") if item.strip()]
    if spec.widget == "integer":
        return parse_parameter_value(value, "int")
    if spec.widget == "number":
        return parse_parameter_value(value, "number")
    if spec.widget == "bool":
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(spec.value, list):
        return parse_parameter_value(value, "list")
    if isinstance(spec.value, bool):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(spec.value, int) and not isinstance(spec.value, bool):
        return parse_parameter_value(value, "int")
    if isinstance(spec.value, float):
        return parse_parameter_value(value, "number")
    return value.strip()


def _get_path(config: dict[str, Any], path: tuple[PathPart, ...]) -> Any:
    target: Any = config
    for part in path:
        target = target[part]
    return target


def _path_exists(config: dict[str, Any], path: tuple[PathPart, ...]) -> bool:
    try:
        _get_path(config, path)
        return True
    except (KeyError, IndexError, TypeError):
        return False


def _is_supported_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _is_sequence_loader_arg(action: str, arg_name: str) -> bool:
    resource, _, method = action.partition(".")
    if method != "load_sequence":
        return False
    if "asg" not in resource.lower():
        return False
    return arg_name in {"sequence", "path", "sequence_path", "sequence_file"}


def _widget_for_value(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def _dedupe_names(specs: list[OperatorParameterSpec]) -> list[OperatorParameterSpec]:
    counts: dict[str, int] = {}
    output: list[OperatorParameterSpec] = []
    for spec in specs:
        count = counts.get(spec.name, 0)
        counts[spec.name] = count + 1
        if count == 0:
            output.append(spec)
        else:
            output.append(
                OperatorParameterSpec(
                    name=f"{spec.name}_{count + 1}",
                    label=spec.label,
                    source=spec.source,
                    value=spec.value,
                    unit=spec.unit,
                    widget=spec.widget,
                    minimum=spec.minimum,
                    maximum=spec.maximum,
                    choices=spec.choices,
                    readonly=spec.readonly,
                    warning=spec.warning,
                    path=spec.path,
                )
            )
    return output


def _source_name(source: str) -> str:
    return _snake(source.replace("[", "_").replace("]", "").replace(".", "_"))


def _source_label(source: str) -> str:
    return source.replace(".", " ")


def _snake(text: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return value or "parameter"
