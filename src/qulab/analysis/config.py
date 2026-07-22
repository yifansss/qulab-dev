"""Parse analysis YAML and build a deterministic dependency plan."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import AnalysisError, AnalysisValidationIssue
from .models import AnalysisExecutionPlan, AnalysisLiveConfig, ComputeArgumentSpec, ComputeModulePlan, json_safe
from .registry import AnalysisModuleRegistry, DEFAULT_ANALYSIS_REGISTRY

_NAME = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_POLICIES = {"warn", "skip", "fail"}


def load_analysis_plan(
    raw_analysis: Any,
    *,
    project_base: str | Path | None = None,
    registry: AnalysisModuleRegistry | None = None,
    known_raw_keys: Iterable[str] = (),
) -> tuple[AnalysisExecutionPlan | None, list[AnalysisValidationIssue]]:
    if raw_analysis is None:
        return None, []
    issues: list[AnalysisValidationIssue] = []
    if not isinstance(raw_analysis, Mapping):
        return None, [AnalysisValidationIssue("error", "analysis_config_invalid", "analysis must be a mapping")]
    live = _parse_live(raw_analysis.get("live"), issues)
    raw_modules = raw_analysis.get("modules", [])
    if raw_modules is None:
        raw_modules = []
    if not isinstance(raw_modules, list):
        issues.append(AnalysisValidationIssue("error", "analysis_config_invalid", "analysis.modules must be a list"))
        raw_modules = []
    module_registry = registry or DEFAULT_ANALYSIS_REGISTRY
    plans: list[ComputeModulePlan] = []
    names: set[str] = set()
    for index, raw in enumerate(raw_modules):
        plan = _parse_module(raw, index, live, module_registry, project_base, issues)
        if plan is None:
            continue
        if plan.instance_name in names:
            issues.append(AnalysisValidationIssue("error", "analysis_module_name_duplicate",
                                                  f"Duplicate analysis module name: {plan.instance_name}"))
        names.add(plan.instance_name)
        plans.append(plan)
    ordered, edges, raw_inputs, derived_outputs = _build_graph(plans, set(known_raw_keys), issues)
    return AnalysisExecutionPlan(live, tuple(ordered), tuple(raw_inputs), tuple(derived_outputs), tuple(edges)), issues


def _parse_live(raw: Any, issues: list[AnalysisValidationIssue]) -> AnalysisLiveConfig:
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        issues.append(AnalysisValidationIssue("error", "analysis_config_invalid", "analysis.live must be a mapping"))
        raw = {}
    policy = raw.get("fail_policy", "warn")
    if policy not in _POLICIES:
        issues.append(AnalysisValidationIssue("error", "analysis_fail_policy_invalid", f"Invalid global fail_policy: {policy}"))
        policy = "warn"
    try:
        config = AnalysisLiveConfig(
            enabled=_bool(raw.get("enabled", False), "analysis.live.enabled"),
            fail_policy=str(policy),
            save_outputs=_bool(raw.get("save_outputs", True), "analysis.live.save_outputs"),
            emit_events=_bool(raw.get("emit_events", True), "analysis.live.emit_events"),
            execution=str(raw.get("execution", "sync")),
            queue_size=int(raw.get("queue_size", 64)),
            backpressure=str(raw.get("backpressure", "skip_newest")),
            drain_on_close=_bool(raw.get("drain_on_close", True), "analysis.live.drain_on_close"),
            drain_timeout_s=float(raw.get("drain_timeout_s", 10)),
            worker_count=int(raw.get("worker_count", 1)),
            status_interval_s=float(raw.get("status_interval_s", .5)),
        )
        if config.execution not in {"sync", "async"}:
            issues.append(AnalysisValidationIssue("error", "analysis_config_invalid", "analysis.live.execution must be sync or async"))
        if config.backpressure not in {"skip_newest", "skip_oldest", "latest", "disable_module", "fail"}:
            issues.append(AnalysisValidationIssue("error", "analysis_config_invalid", f"Invalid analysis backpressure policy: {config.backpressure}"))
        if config.execution == "async" and config.queue_size < 1:
            issues.append(AnalysisValidationIssue("error", "analysis_config_invalid", "async analysis queue_size must be >= 1"))
        if config.worker_count != 1:
            issues.append(AnalysisValidationIssue("error", "analysis_config_invalid", "thread backend currently requires worker_count: 1"))
        if config.drain_timeout_s < 0 or config.status_interval_s < 0:
            issues.append(AnalysisValidationIssue("error", "analysis_config_invalid", "analysis timeouts/intervals must be nonnegative"))
        if config.execution == "async" and config.backpressure == "latest":
            issues.append(AnalysisValidationIssue("warning", "analysis_config_invalid", "latest backpressure may omit per-point derived provenance"))
        return config
    except (TypeError, ValueError, AnalysisError) as exc:
        issues.append(AnalysisValidationIssue("error", "analysis_config_invalid", str(exc)))
        return AnalysisLiveConfig(fail_policy=str(policy))


def _parse_module(raw: Any, index: int, live: AnalysisLiveConfig, registry: AnalysisModuleRegistry,
                  project_base: str | Path | None, issues: list[AnalysisValidationIssue]) -> ComputeModulePlan | None:
    loc = f"analysis.modules[{index}]"
    if not isinstance(raw, Mapping):
        issues.append(AnalysisValidationIssue("error", "analysis_config_invalid", f"{loc} must be a mapping"))
        return None
    name = raw.get("name")
    target = raw.get("module")
    class_name, function_name = raw.get("class"), raw.get("function")
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        issues.append(AnalysisValidationIssue("error", "analysis_config_invalid", f"{loc}.name must be stable snake_case"))
        return None
    if not isinstance(target, str) or not target:
        issues.append(AnalysisValidationIssue("error", "analysis_module_target_invalid", f"{loc}.module is required"))
        return None
    selected = [("class", class_name), ("function", function_name)]
    selected = [(kind, value) for kind, value in selected if value is not None]
    if len(selected) != 1 or not isinstance(selected[0][1], str) or not selected[0][1]:
        issues.append(AnalysisValidationIssue("error", "analysis_config_invalid", f"{loc} must set exactly one of class/function"))
        return None
    kind, object_name = selected[0]
    inputs = _keys(raw.get("inputs"), "analysis_inputs_invalid", f"{loc}.inputs", issues)
    outputs = _keys(raw.get("outputs"), "analysis_outputs_invalid", f"{loc}.outputs", issues)
    if inputs is None or outputs is None:
        return None
    if set(inputs) & set(outputs):
        issues.append(AnalysisValidationIssue("error", "analysis_outputs_invalid", f"{loc} output cannot also be an input"))
    namespace = raw.get("namespace")
    if namespace is not None and (not isinstance(namespace, str) or not _KEY.fullmatch(namespace)):
        issues.append(AnalysisValidationIssue("error", "analysis_outputs_invalid", f"{loc}.namespace is invalid"))
        namespace = None
    effective = tuple(f"{namespace}.{key}" if namespace else key for key in outputs)
    policy = raw.get("fail_policy", live.fail_policy)
    if policy not in _POLICIES:
        issues.append(AnalysisValidationIssue("error", "analysis_fail_policy_invalid", f"Invalid fail_policy for '{name}': {policy}"))
        policy = live.fail_policy
    try:
        enabled = _bool(raw.get("enabled", True), f"{loc}.enabled")
        run_live = _bool(raw.get("run_live", True), f"{loc}.run_live")
        run_post = _bool(raw.get("run_post", False), f"{loc}.run_post")
        show = _bool(raw.get("show", False), f"{loc}.show")
        save = _bool(raw.get("save", live.save_outputs), f"{loc}.save")
    except AnalysisError as exc:
        issues.append(exc.as_issue())
        return None
    if enabled and not run_live and not run_post:
        issues.append(AnalysisValidationIssue("warning", "analysis_config_invalid",
                                              f"Enabled module '{name}' has run_live and run_post both false"))
    if show and not save:
        issues.append(AnalysisValidationIssue("warning", "analysis_live_only_output", f"Module '{name}' outputs are live-only"))
    args = raw.get("args", {})
    if not isinstance(args, Mapping):
        issues.append(AnalysisValidationIssue("error", "analysis_args_invalid", f"{loc}.args must be a mapping"))
        args = {}
    try:
        safe_args = json_safe(args)
    except TypeError as exc:
        issues.append(AnalysisValidationIssue("error", "analysis_args_invalid", f"{loc}.args: {exc}"))
        safe_args = {}
    try:
        _, _, identity = registry.resolve(target, object_name, kind, project_base=project_base)
        requested_version = raw.get("version")
        if requested_version is not None and str(requested_version) != identity.version:
            raise AnalysisError("analysis_version_mismatch",
                                f"Module '{name}' version {identity.version!r} does not match requested {requested_version!r}")
        provisional = ComputeModulePlan(name, target, object_name, kind, enabled, run_live, run_post, show, save,
                                        str(policy), inputs, outputs, effective, safe_args, identity, namespace)
        spec = registry.describe(provisional)
        safe_args = _validate_args(safe_args, spec.argument_specs, name, issues)
        validator = getattr(registry.resolve(target, object_name, kind, project_base=project_base)[0], "validate_config", None)
        if callable(validator):
            for item in validator(safe_args) or []:
                if isinstance(item, AnalysisValidationIssue):
                    issues.append(item)
        return replace(provisional, args=safe_args)
    except AnalysisError as exc:
        issues.append(exc.as_issue())
        return None
    except Exception as exc:
        issues.append(AnalysisValidationIssue("error", "analysis_contract_invalid", f"Module '{name}' validation failed: {exc}"))
        return None


def _build_graph(plans: list[ComputeModulePlan], known_raw: set[str], issues: list[AnalysisValidationIssue]):
    enabled = [plan for plan in plans if plan.enabled]
    producers: dict[str, str] = {}
    disabled_outputs = {key for plan in plans if not plan.enabled for key in plan.effective_outputs}
    for plan in enabled:
        for key in plan.effective_outputs:
            if key in producers:
                issues.append(AnalysisValidationIssue("error", "analysis_output_collision",
                                                      f"Output '{key}' is produced by both '{producers[key]}' and '{plan.instance_name}'"))
            producers[key] = plan.instance_name
            if key in known_raw:
                issues.append(AnalysisValidationIssue("error", "analysis_output_collision", f"Derived output '{key}' collides with known raw data"))
    dependencies: dict[str, set[str]] = {plan.instance_name: set() for plan in enabled}
    raw_inputs: list[str] = []
    for plan in enabled:
        for key in plan.inputs:
            producer = producers.get(key)
            if producer == plan.instance_name:
                issues.append(AnalysisValidationIssue("error", "analysis_dependency_cycle", f"Module '{plan.instance_name}' depends on itself via '{key}'"))
            elif producer:
                dependencies[plan.instance_name].add(producer)
            elif key in disabled_outputs:
                issues.append(AnalysisValidationIssue("error", "analysis_dependency_disabled",
                                                      f"Module '{plan.instance_name}' requires '{key}' from a disabled module"))
            else:
                if key not in raw_inputs:
                    raw_inputs.append(key)
                if known_raw and key not in known_raw:
                    issues.append(AnalysisValidationIssue("warning", "analysis_input_unknown",
                                                          f"Input '{key}' for module '{plan.instance_name}' is not a known raw output"))
    order_index = {plan.instance_name: index for index, plan in enumerate(enabled)}
    pending = {name: set(deps) for name, deps in dependencies.items()}
    ordered_names: list[str] = []
    while pending:
        ready = sorted((name for name, deps in pending.items() if not deps), key=order_index.get)
        if not ready:
            cycle = ", ".join(sorted(pending, key=order_index.get))
            issues.append(AnalysisValidationIssue("error", "analysis_dependency_cycle", f"Analysis dependency cycle: {cycle}"))
            ordered_names.extend(sorted(pending, key=order_index.get))
            break
        for name in ready:
            ordered_names.append(name)
            pending.pop(name)
            for deps in pending.values():
                deps.discard(name)
    by_name = {plan.instance_name: plan for plan in plans}
    ordered_enabled = [replace(by_name[name], dependencies=tuple(sorted(dependencies[name], key=order_index.get))) for name in ordered_names]
    ordered = ordered_enabled + [plan for plan in plans if not plan.enabled]
    edges = [(dep, name) for name in ordered_names for dep in sorted(dependencies[name], key=order_index.get)]
    derived = [key for plan in ordered_enabled for key in plan.effective_outputs]
    return ordered, edges, raw_inputs, derived


def _validate_args(args: dict[str, Any], specs: tuple[ComputeArgumentSpec, ...], name: str,
                   issues: list[AnalysisValidationIssue]) -> dict[str, Any]:
    if not specs:
        return args
    output = dict(args)
    known = {spec.name: spec for spec in specs}
    for key in output:
        if key not in known:
            issues.append(AnalysisValidationIssue("error", "analysis_args_invalid", f"Unknown argument '{key}' for module '{name}'"))
    for spec in specs:
        if spec.name not in output:
            if spec.required and spec.default is None:
                issues.append(AnalysisValidationIssue("error", "analysis_args_invalid", f"Missing required argument '{spec.name}' for module '{name}'"))
                continue
            output[spec.name] = json_safe(spec.default)
        value = output.get(spec.name)
        valid_type = {"any": object, "number": (int, float), "integer": int, "float": (int, float),
                      "string": str, "boolean": bool, "list": list, "mapping": dict}.get(spec.value_type)
        if valid_type is None or (valid_type is not object and (isinstance(value, bool) and spec.value_type in {"number", "integer", "float"} or not isinstance(value, valid_type))):
            issues.append(AnalysisValidationIssue("error", "analysis_args_invalid", f"Argument '{spec.name}' for '{name}' must be {spec.value_type}"))
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if spec.minimum is not None and value < spec.minimum or spec.maximum is not None and value > spec.maximum:
                issues.append(AnalysisValidationIssue("error", "analysis_args_invalid", f"Argument '{spec.name}' for '{name}' is out of range"))
        if spec.choices and value not in spec.choices:
            issues.append(AnalysisValidationIssue("error", "analysis_args_invalid", f"Argument '{spec.name}' for '{name}' is not an allowed choice"))
    return output


def _keys(raw: Any, code: str, label: str, issues: list[AnalysisValidationIssue]) -> tuple[str, ...] | None:
    if not isinstance(raw, list) or not raw or any(not isinstance(item, str) or not _KEY.fullmatch(item) for item in raw):
        issues.append(AnalysisValidationIssue("error", code, f"{label} must be a non-empty list of valid strings"))
        return None
    if len(raw) != len(set(raw)):
        issues.append(AnalysisValidationIssue("error", code, f"{label} must contain unique keys"))
        return None
    return tuple(raw)


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise AnalysisError("analysis_config_invalid", f"{label} must be boolean")
    return value
