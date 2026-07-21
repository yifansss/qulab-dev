"""Compile sequence_sweep authoring macros to canonical Qulab workflow nodes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .errors import SequenceGenerationError
from .models import MaterializedSequenceBundle, SequenceSweepPlan


def compile_sequence_sweeps(config: Mapping[str, Any], plans: Mapping[str, SequenceSweepPlan],
                            bundles: Mapping[str, MaterializedSequenceBundle]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    compiled = deepcopy(dict(config))
    declarations = compiled.setdefault("sequence_bundles", {})
    if not isinstance(declarations, dict):
        raise SequenceGenerationError("sequence_plan_name_collision", "sequence_bundles must be a mapping")
    for plan_id, bundle in bundles.items():
        if bundle.bundle_id in declarations:
            raise SequenceGenerationError("sequence_plan_name_collision", f"Generated bundle id '{bundle.bundle_id}' already exists")
        declarations[bundle.bundle_id] = {"manifest": str(bundle.manifest_path), "resource": bundle.plan.resource,
                                          "match": {"mode": "exact"}}
    parameter_defs = compiled.setdefault("parameters", {})
    if not isinstance(parameter_defs, dict):
        raise SequenceGenerationError("sequence_plan_name_collision", "parameters must be a mapping")
    generated_defs: dict[str, dict[str, Any]] = {}
    for plan_id, bundle in bundles.items():
        specs = {item.name: item for item in bundle.family_spec.parameters}
        for name, values in bundle.normalized_values.items():
            value_plan = plans[plan_id].parameters.get(name)
            exported = (value_plan.expose_as if value_plan else None) or name
            definition = {"unit": specs[name].unit if name in specs else (value_plan.unit if value_plan else None), "role": "sequence_coordinate" if value_plan and value_plan.swept else "sequence_parameter", "plan": plan_id}
            if not value_plan or not value_plan.swept:
                definition["value"] = values[0]
            if exported in parameter_defs and parameter_defs[exported] != definition:
                raise SequenceGenerationError("sequence_plan_name_collision", f"Parameter '{exported}' conflicts with a sequence plan parameter")
            parameter_defs[exported] = definition
            generated_defs[exported] = definition

    def compile_steps(raw: Any, location: str) -> list[Any]:
        if not isinstance(raw, list):
            raise SequenceGenerationError("sequence_macro_invalid", f"{location} must be a list")
        output = []
        for index, step in enumerate(raw):
            if not isinstance(step, dict):
                output.append(deepcopy(step)); continue
            if "sequence_sweep" in step:
                macro = step["sequence_sweep"]
                if not isinstance(macro, dict):
                    raise SequenceGenerationError("sequence_macro_invalid", f"{location}[{index}].sequence_sweep must be a mapping")
                plan_id = macro.get("plan")
                if plan_id not in bundles:
                    raise SequenceGenerationError("sequence_plan_not_found", f"Unknown sequence plan '{plan_id}'")
                body = macro.get("body", [])
                if not isinstance(body, list) or len(body) != 1 or not isinstance(body[0], dict) or "measurement" not in body[0]:
                    raise SequenceGenerationError("sequence_macro_invalid", "sequence_sweep body must contain exactly one top-level measurement")
                measurement = deepcopy(body[0])
                measurement_config = measurement["measurement"]
                measurement_body = measurement_config.setdefault("body", [])
                plan = plans[plan_id]
                coordinates = {(plan.parameters[name].expose_as or name): "${" + (plan.parameters[name].expose_as or name) + "}" for name in plan.sampling_order}
                measurement_body.insert(0, {"call": f"{plan.resource}.load_sequence_from_bundle",
                                            "args": {"bundle": bundles[plan_id].bundle_id, "coordinates": coordinates}})
                node: dict[str, Any] = measurement
                for name in reversed(plan.sampling_order):
                    exported = plan.parameters[name].expose_as or name
                    node = {"scan": {"name": exported, "values": list(bundles[plan_id].normalized_values[name]), "body": [node]}}
                output.append(node)
            else:
                copied = deepcopy(step)
                for key, child_key in (("scan", "body"), ("average", "body"), ("measurement", "body"), ("run", "steps"), ("cleanup", "steps")):
                    if key in copied and isinstance(copied[key], dict) and child_key in copied[key]:
                        copied[key][child_key] = compile_steps(copied[key][child_key], f"{location}[{index}].{key}.{child_key}")
                output.append(copied)
        return output
    for section in ("setup", "procedure", "cleanup"):
        if section in compiled:
            compiled[section] = compile_steps(compiled[section], section)
    compiled.pop("sequence_plans", None)
    return compiled, generated_defs
