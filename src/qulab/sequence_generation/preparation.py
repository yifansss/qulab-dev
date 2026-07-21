"""Public side-effect boundary for sequence generation and config compilation."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from qulab.paths import resolve_project_path

from .compiler import compile_sequence_sweeps
from .errors import SequenceGenerationError
from .materializer import materialize_sequence_plan
from .models import MaterializePolicy, ParameterValuePlan, SequenceGenerationRecord, SequencePreparationResult, SequenceSweepPlan
from .registry import DEFAULT_PROVIDER_REGISTRY, SequenceProviderRegistry


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_PARAMETER_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SequenceGenerationError("invalid_sequence_plan", f"{location} must be a mapping")
    return value


def parse_sequence_plans(config: Mapping[str, Any]) -> dict[str, SequenceSweepPlan]:
    raw_plans = config.get("sequence_plans", {})
    if raw_plans in (None, {}):
        return {}
    raw_plans = _mapping(raw_plans, "sequence_plans")
    resources = _mapping(config.get("resources", {}), "resources")
    result = {}
    for plan_id, raw in raw_plans.items():
        if not isinstance(plan_id, str) or not _IDENTIFIER.fullmatch(plan_id):
            raise SequenceGenerationError("invalid_sequence_plan_id", f"Invalid sequence plan id: {plan_id!r}")
        raw = _mapping(raw, f"sequence_plans.{plan_id}")
        resource = raw.get("resource")
        if resource not in resources:
            raise SequenceGenerationError("sequence_plan_resource_not_found", f"Plan '{plan_id}' references missing resource '{resource}'")
        resource_config = _mapping(resources[resource], f"resources.{resource}")
        capabilities = resource_config.get("capabilities", [])
        if "pulse_sequencer" not in capabilities:
            raise SequenceGenerationError("sequence_plan_resource_capability", f"Resource '{resource}' must declare pulse_sequencer capability")
        family = _mapping(raw.get("family"), f"sequence_plans.{plan_id}.family")
        provider = family.get("provider")
        if not isinstance(provider, str) or not provider:
            raise SequenceGenerationError("sequence_provider_not_found", f"Plan '{plan_id}' requires family.provider")
        raw_parameters = _mapping(raw.get("parameters", {}), f"sequence_plans.{plan_id}.parameters")
        parameters = {}
        for name, value in raw_parameters.items():
            if not isinstance(name, str) or not _PARAMETER_IDENTIFIER.fullmatch(name):
                raise SequenceGenerationError("invalid_parameter_name", f"Invalid sequence parameter name: {name!r}")
            parameters[name] = ParameterValuePlan.from_mapping(_mapping(value, f"sequence_plans.{plan_id}.parameters.{name}"))
            exposed = parameters[name].expose_as
            if exposed is not None and (not isinstance(exposed, str) or not _PARAMETER_IDENTIFIER.fullmatch(exposed)):
                raise SequenceGenerationError("invalid_parameter_name", f"Invalid exported coordinate name: {exposed!r}")
        sampling = _mapping(raw.get("sampling", {}), f"sequence_plans.{plan_id}.sampling")
        materialize = _mapping(raw.get("materialize", {}), f"sequence_plans.{plan_id}.materialize")
        template = raw.get("template")
        template_path = resolve_project_path(template) if template is not None else None
        if template is not None and (template_path is None or not template_path.is_file()):
            raise SequenceGenerationError("sequence_template_not_found", f"Sequence template not found: {template}")
        result[plan_id] = SequenceSweepPlan(
            id=plan_id, resource=str(resource), provider=provider,
            provider_version=None if family.get("version") is None else str(family["version"]),
            parameters=parameters, sampling_mode=str(sampling.get("mode", "cartesian")),
            sampling_order=tuple(sampling.get("order", ())), template=template_path,
            materialize=MaterializePolicy(bool(materialize.get("cache", True)), int(materialize.get("max_points", 10_000))),
            targets=dict(raw.get("targets", {})) if isinstance(raw.get("targets", {}), Mapping) else {},
            groups=dict(raw.get("groups", {})) if isinstance(raw.get("groups", {}), Mapping) else {},
            constraints=tuple(raw.get("constraints", ())) if isinstance(raw.get("constraints", ()), (list, tuple)) else (),
            options=dict(raw.get("options", {})) if isinstance(raw.get("options", {}), Mapping) else {},
        )
    return result


def prepare_sequence_config(config: Mapping[str, Any], *, cache_root: Path | None = None,
                            registry: SequenceProviderRegistry | None = None) -> SequencePreparationResult:
    authoring = deepcopy(dict(config))
    selected_root = Path(cache_root) if cache_root is not None else Path(".qulab/cache/sequence_bundles")
    try:
        plans = parse_sequence_plans(authoring)
        if not plans:
            return SequencePreparationResult(authoring, deepcopy(authoring), cache_root=selected_root)
        materialized = {}
        records = []
        provider_registry = registry or DEFAULT_PROVIDER_REGISTRY
        for plan_id, plan in plans.items():
            provider, identity = provider_registry.load(plan.provider, plan.provider_version)
            bundle = materialize_sequence_plan(plan, provider, cache_root=selected_root, source_identity=identity)
            materialized[plan_id] = bundle
            records.append(SequenceGenerationRecord(
                plan_id, bundle.plan_hash, identity.provider, identity.version, identity.source_sha256,
                bundle.template_sha256, bundle.bundle_id, str(bundle.manifest_path), bundle.manifest_sha256,
                bundle.point_count, bundle.cache_hit,
            ))
        compiled, parameters = compile_sequence_sweeps(authoring, plans, materialized)
        return SequencePreparationResult(authoring, compiled, plans, materialized, tuple(records), parameters,
                                         cache_root=selected_root)
    except SequenceGenerationError as exc:
        return SequencePreparationResult(authoring, deepcopy(authoring), issues=(exc.as_issue(),), cache_root=selected_root)


def prepare_and_parse_experiment_config(config: Mapping[str, Any], *, cache_root: Path | None = None,
                                        registry: SequenceProviderRegistry | None = None, instrument_registry: Any = None):
    from qulab.config.parser import parse_experiment_config

    prepared = prepare_sequence_config(config, cache_root=cache_root, registry=registry)
    if not prepared.ok:
        issue = next(item for item in prepared.issues if item.severity == "error")
        raise SequenceGenerationError(issue.code, issue.message, context=issue.context)
    parsed = parse_experiment_config(prepared.compiled_config, registry=instrument_registry)
    parsed.config = deepcopy(prepared.authoring_config)
    parsed.sequence_preparation = prepared
    return parsed
