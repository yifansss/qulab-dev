"""Parse experiment config mappings into executable objects."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from qulab.core import (
    ActionStep,
    AverageStep,
    ExperimentContext,
    MeasurementStep,
    Procedure,
    RunStep,
    ScanStep,
    ScanValues,
    Step,
    WaitStep,
)
from qulab.analysis import AnalysisExecutionPlan, load_analysis_plan
from qulab.analysis.validation import collect_known_raw_keys
from qulab.instruments import InstrumentRegistry, build_context_from_resources
from qulab.sequence_bundles import SequenceBundle, SequenceBundleError, load_sequence_bundle
from qulab.sequence_preflight import SequenceBundlePreflightValidator
from qulab.sync import ExecutionOrder, SyncPlan, SyncValidationIssue, SyncValidationResult, SyncValidator, TriggerEdge

from .errors import ConfigLoadError
from .refs import resolve_parameter_refs


@dataclass
class ParsedExperiment:
    name: str
    config: dict[str, Any]
    resolved_config: dict[str, Any]
    procedure: Procedure
    context: ExperimentContext
    sync_plan: SyncPlan | None
    validation: SyncValidationResult
    sequence_bundles: dict[str, SequenceBundle]
    analysis_plan: AnalysisExecutionPlan | None = None
    sequence_preparation: Any = None


def parse_experiment_config(
    config: dict[str, Any],
    registry: InstrumentRegistry | None = None,
) -> ParsedExperiment:
    """Build context, procedure, sync plan, and validation result from config."""

    if not isinstance(config, dict):
        raise ConfigLoadError("Experiment config must be a mapping")
    name = str(config.get("name") or "experiment")
    resolved_config = resolve_parameter_refs(deepcopy(config))
    resources_config = _mapping(resolved_config.get("resources", {}), "resources")
    context = build_context_from_resources(resources_config, registry or InstrumentRegistry())
    _initialize_parameters(resolved_config.get("parameters"), context)
    sequence_bundles = _parse_sequence_bundles(resolved_config.get("sequence_bundles"), resources_config, context)
    context.sequence_bundles = sequence_bundles
    sync_plan = _parse_sync_plan(resolved_config.get("sync"))
    procedure = Procedure(
        name=name,
        setup=_parse_steps(resolved_config.get("setup", []), "setup"),
        body=_parse_steps(resolved_config.get("procedure", []), "procedure"),
        cleanup=_parse_steps(resolved_config.get("cleanup", []), "cleanup"),
        metadata={
            "schema_version": resolved_config.get("schema_version"),
            "description": resolved_config.get("description"),
            "tags": resolved_config.get("tags", []),
            "plot": resolved_config.get("plot", []),
            "storage": resolved_config.get("storage", {}),
        },
    )
    validation = SyncValidator().validate(sync_plan, context, procedure)
    validation.issues.extend(SequenceBundlePreflightValidator().validate(sync_plan, context, procedure))
    analysis_plan, analysis_issues = load_analysis_plan(
        resolved_config.get("analysis"),
        known_raw_keys=collect_known_raw_keys(procedure),
    )
    validation.issues.extend(
        SyncValidationIssue(issue.severity, issue.code, issue.message) for issue in analysis_issues
    )
    return ParsedExperiment(
        name=name,
        config=deepcopy(config),
        resolved_config=resolved_config,
        procedure=procedure,
        context=context,
        sync_plan=sync_plan,
        validation=validation,
        sequence_bundles=sequence_bundles,
        analysis_plan=analysis_plan,
    )


def _parse_sequence_bundles(
    raw_bundles: Any,
    resources_config: dict[str, Any],
    context: ExperimentContext,
) -> dict[str, SequenceBundle]:
    if raw_bundles in (None, {}):
        return {}
    bundles_config = _mapping(raw_bundles, "sequence_bundles")
    bundles: dict[str, SequenceBundle] = {}
    for declared_id, raw_bundle in bundles_config.items():
        if not isinstance(declared_id, str) or not declared_id:
            raise ConfigLoadError("sequence_bundles keys must be non-empty strings")
        location = f"sequence_bundles.{declared_id}"
        bundle_config = _mapping(raw_bundle, location)
        manifest = bundle_config.get("manifest")
        if not isinstance(manifest, (str, bytes)) and not hasattr(manifest, "__fspath__"):
            raise ConfigLoadError(f"{location}.manifest is required")
        declared_resource = bundle_config.get("resource")
        if declared_resource is not None and not isinstance(declared_resource, str):
            raise ConfigLoadError(f"{location}.resource must be a string")
        try:
            bundle = load_sequence_bundle(
                manifest,
                declared_id=declared_id,
                declared_resource=declared_resource,
                match=_mapping(bundle_config.get("match", {}), f"{location}.match"),
            )
        except SequenceBundleError as exc:
            raise ConfigLoadError(f"Invalid {location}: {exc}") from exc
        if bundle.resource not in resources_config:
            raise ConfigLoadError(
                f"{location} references missing resource '{bundle.resource}'"
            )
        resource_config = _mapping(resources_config[bundle.resource], f"resources.{bundle.resource}")
        declared_capabilities = resource_config.get("capabilities")
        if declared_capabilities is not None:
            if not isinstance(declared_capabilities, list):
                raise ConfigLoadError(f"resources.{bundle.resource}.capabilities must be a list")
            if "pulse_sequencer" not in declared_capabilities:
                raise ConfigLoadError(
                    f"{location} resource '{bundle.resource}' must declare pulse_sequencer capability"
                )
        resource = context.resources.get(bundle.resource)
        capabilities = resource.capabilities() if resource is not None and hasattr(resource, "capabilities") else set()
        if capabilities and "pulse_sequencer" not in capabilities:
            raise ConfigLoadError(
                f"{location} resource '{bundle.resource}' does not support pulse_sequencer capability"
            )
        if declared_capabilities is None and not capabilities:
            raise ConfigLoadError(
                f"{location} cannot confirm capabilities for resource '{bundle.resource}'; "
                "declare pulse_sequencer in the resource capabilities list"
            )
        bundles[declared_id] = bundle
    return bundles


def _parse_steps(raw_steps: Any, location: str) -> list[Step]:
    if raw_steps is None:
        return []
    if not isinstance(raw_steps, list):
        raise ConfigLoadError(f"{location} must be a list")
    return [_parse_step(raw_step, f"{location}[{index}]") for index, raw_step in enumerate(raw_steps)]


def _parse_step(raw_step: Any, location: str) -> Step:
    if not isinstance(raw_step, dict):
        raise ConfigLoadError(f"{location} must be a mapping")
    enabled = bool(raw_step.get("enabled", True))
    if "sequence_sweep" in raw_step:
        raise ConfigLoadError(
            f"Unprepared sequence_sweep macro at {location}; call "
            "qulab.sequence_generation.prepare_sequence_config() before parse_experiment_config()"
        )
    if "call" in raw_step:
        action = raw_step["call"]
        if not isinstance(action, str) or "." not in action:
            raise ConfigLoadError(f"{location}.call must be resource.method")
        return ActionStep(
            name=str(raw_step.get("name") or action),
            enabled=enabled,
            action=action,
            args=list(raw_step.get("args_list", [])),
            kwargs=_mapping(raw_step.get("args", {}), f"{location}.args"),
            save_as=raw_step.get("save_as"),
        )
    if "scan" in raw_step:
        scan = _mapping(raw_step["scan"], f"{location}.scan")
        name = scan.get("name")
        if not isinstance(name, str) or not name:
            raise ConfigLoadError(f"{location}.scan.name is required")
        return ScanStep(
            name=name,
            enabled=enabled,
            values=_parse_scan_values(scan.get("values"), f"{location}.scan.values"),
            body=_parse_steps(scan.get("body", []), f"{location}.scan.body"),
        )
    if "average" in raw_step:
        average = _mapping(raw_step["average"], f"{location}.average")
        count = average.get("count", 1)
        if not isinstance(count, int):
            raise ConfigLoadError(f"{location}.average.count must be a literal integer")
        return AverageStep(
            name=str(average.get("name") or "avg"),
            enabled=enabled,
            count=count,
            body=_parse_steps(average.get("body", []), f"{location}.average.body"),
        )
    if "measurement" in raw_step:
        measurement = _mapping(raw_step["measurement"], f"{location}.measurement")
        return MeasurementStep(
            name=str(measurement.get("name") or "measurement"),
            enabled=enabled,
            body=_parse_steps(measurement.get("body", []), f"{location}.measurement.body"),
        )
    if "run" in raw_step:
        run = _mapping(raw_step["run"], f"{location}.run")
        return RunStep(
            name=str(run.get("name") or "run"),
            enabled=enabled,
            timeout_s=run.get("timeout_s"),
            body=_parse_steps(run.get("steps", run.get("body", [])), f"{location}.run.steps"),
        )
    if "wait" in raw_step:
        wait = raw_step["wait"]
        if isinstance(wait, (int, float)):
            duration_s = float(wait)
            name = str(raw_step.get("name") or "wait")
            reason = None
        else:
            wait_config = _mapping(wait, f"{location}.wait")
            duration_s = float(wait_config.get("duration_s", wait_config.get("seconds", 0.0)))
            name = str(wait_config.get("name") or raw_step.get("name") or "wait")
            reason = wait_config.get("reason")
        return WaitStep(name=name, enabled=enabled, duration_s=duration_s, reason=reason)
    if "cleanup" in raw_step:
        cleanup = _mapping(raw_step["cleanup"], f"{location}.cleanup")
        from qulab.core import CleanupStep

        return CleanupStep(
            name=str(cleanup.get("name") or "cleanup"),
            enabled=enabled,
            body=_parse_steps(cleanup.get("steps", cleanup.get("body", [])), f"{location}.cleanup.steps"),
        )

    keys = ", ".join(raw_step)
    raise ConfigLoadError(f"Unsupported step at {location}: {keys}")


def _initialize_parameters(raw_parameters: Any, context: ExperimentContext) -> None:
    if raw_parameters in (None, {}):
        return
    parameters = _mapping(raw_parameters, "parameters")
    for name, raw in parameters.items():
        if not isinstance(name, str) or not name:
            raise ConfigLoadError("parameters keys must be non-empty strings")
        definition = _mapping(raw, f"parameters.{name}")
        if "value" in definition:
            context.set_parameter(name, definition["value"], definition.get("unit"))


def _parse_scan_values(raw_values: Any, location: str) -> ScanValues:
    if isinstance(raw_values, list):
        return ScanValues.explicit(raw_values)
    if isinstance(raw_values, dict):
        if {"start", "stop", "points"} <= set(raw_values):
            return ScanValues.linspace(float(raw_values["start"]), float(raw_values["stop"]), int(raw_values["points"]))
        if {"start", "stop", "step"} <= set(raw_values):
            return ScanValues.range(float(raw_values["start"]), float(raw_values["stop"]), float(raw_values["step"]))
    raise ConfigLoadError(f"{location} must be a list, {{start, stop, points}}, or {{start, stop, step}}")


def _parse_sync_plan(raw_sync: Any) -> SyncPlan | None:
    if raw_sync in (None, {}):
        return None
    sync = _mapping(raw_sync, "sync")
    raw_order = sync.get("order")
    order = None
    if raw_order is not None:
        order_map = _mapping(raw_order, "sync.order")
        order = ExecutionOrder(
            configure=list(order_map.get("configure", [])),
            arm=list(order_map.get("arm", [])),
            start=list(order_map.get("start", [])),
            read=list(order_map.get("read", [])),
        )
    return SyncPlan(
        master=sync.get("master"),
        triggers=[
            TriggerEdge(
                source=str(trigger.get("source")),
                target=str(trigger.get("target")),
                edge=str(trigger.get("edge", "rising")),
                purpose=trigger.get("purpose"),
            )
            for trigger in _list(sync.get("triggers", []), "sync.triggers")
            if isinstance(trigger, dict)
        ],
        order=order,
    )


def _mapping(value: Any, location: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigLoadError(f"{location} must be a mapping")
    return value


def _list(value: Any, location: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigLoadError(f"{location} must be a list")
    return value
