"""Validation and deterministic Cartesian sampling for sequence plans."""

from __future__ import annotations

import itertools
import math
from typing import Any, Mapping

from qulab.core import ScanValues

from .errors import SequenceGenerationError
from .models import ParameterValuePlan, PlanPoint, SequenceFamilySpec, SequenceSweepPlan


def _coerce(value: Any, dtype: str, name: str) -> Any:
    try:
        if dtype == "float":
            if isinstance(value, bool):
                raise ValueError
            result = float(value)
            if not math.isfinite(result):
                raise ValueError
            return result
        if dtype == "int":
            if isinstance(value, bool) or int(value) != float(value):
                raise ValueError
            return int(value)
        if dtype == "bool":
            if not isinstance(value, bool):
                raise ValueError
            return value
        if dtype == "str":
            if not isinstance(value, str):
                raise ValueError
            return value
    except (TypeError, ValueError):
        pass
    else:
        raise SequenceGenerationError("unsupported_parameter_dtype", f"Unsupported dtype '{dtype}' for '{name}'")
    raise SequenceGenerationError("sequence_parameter_invalid", f"Invalid {dtype} value for sequence parameter '{name}'")


def normalize_parameter_values(plan: SequenceSweepPlan, spec: SequenceFamilySpec) -> dict[str, tuple[Any, ...]]:
    specs = {item.name: item for item in spec.parameters}
    unknown = sorted(set(plan.parameters) - set(specs))
    if unknown and not spec.dynamic_parameters:
        raise SequenceGenerationError("sequence_parameter_unknown", f"Unknown sequence parameter(s): {', '.join(unknown)}")
    result: dict[str, tuple[Any, ...]] = {}
    items = list(spec.parameters)
    if spec.dynamic_parameters:
        from .models import SequenceParameterSpec
        items.extend(SequenceParameterSpec(name, name, "float", value.unit or "s", value.value if value.value is not None else 0.0)
                     for name, value in plan.parameters.items() if name not in specs)
    for item in items:
        if item.name not in plan.parameters and item.default is None:
            raise SequenceGenerationError("sequence_parameter_missing", f"Missing required sequence parameter '{item.name}'")
        value_plan = plan.parameters.get(item.name, ParameterValuePlan(mode="fixed", value=item.default))
        if value_plan.unit is not None and item.unit is not None and value_plan.unit != item.unit:
            raise SequenceGenerationError("sequence_parameter_unit_invalid", f"Parameter '{item.name}' expects unit {item.unit!r}")
        if value_plan.swept and not item.sweepable:
            raise SequenceGenerationError("parameter_not_sweepable", f"Parameter '{item.name}' is not sweepable")
        if value_plan.mode == "fixed":
            raw_values = [item.default if value_plan.value is None else value_plan.value]
        elif value_plan.mode == "linspace":
            if value_plan.start is None or value_plan.stop is None or not isinstance(value_plan.points, int) or value_plan.points < 1:
                raise SequenceGenerationError("invalid_sampling", f"linspace parameter '{item.name}' requires start, stop, points >= 1")
            raw_values = list(ScanValues.linspace(float(value_plan.start), float(value_plan.stop), value_plan.points))
        elif value_plan.mode == "range":
            if value_plan.start is None or value_plan.stop is None or value_plan.step is None:
                raise SequenceGenerationError("invalid_sampling", f"range parameter '{item.name}' requires start, stop, step")
            raw_values = list(ScanValues.range(float(value_plan.start), float(value_plan.stop), float(value_plan.step)))
        elif value_plan.mode == "explicit":
            if not value_plan.values:
                raise SequenceGenerationError("invalid_sampling", f"explicit parameter '{item.name}' requires non-empty values")
            raw_values = list(value_plan.values)
        else:
            raise SequenceGenerationError("invalid_sampling_mode", f"Unsupported sampling mode '{value_plan.mode}'")
        values = tuple(_coerce(value, item.dtype, item.name) for value in raw_values)
        for value in values:
            if item.minimum is not None and value < item.minimum:
                raise SequenceGenerationError("sequence_parameter_invalid", f"Parameter '{item.name}' is below {item.minimum}")
            if item.maximum is not None and value > item.maximum:
                raise SequenceGenerationError("sequence_parameter_invalid", f"Parameter '{item.name}' is above {item.maximum}")
            if item.choices is not None and value not in item.choices:
                raise SequenceGenerationError("sequence_parameter_invalid", f"Parameter '{item.name}' is not an allowed choice")
        result[item.name] = values
    swept = [name for name, value in plan.parameters.items() if value.swept]
    exported = [plan.parameters[name].expose_as or name for name in swept]
    if len(exported) != len(set(exported)):
        raise SequenceGenerationError("sequence_plan_name_collision", "Two swept parameters export the same coordinate name")
    if plan.sampling_mode != "cartesian":
        raise SequenceGenerationError("invalid_sampling_mode", "Only cartesian sequence sampling is supported")
    if set(plan.sampling_order) != set(swept) or len(plan.sampling_order) != len(set(plan.sampling_order)):
        raise SequenceGenerationError("invalid_sampling_order", "sampling.order must contain every swept parameter exactly once")
    return result


def enumerate_plan_points(plan: SequenceSweepPlan, values: Mapping[str, tuple[Any, ...]]) -> tuple[PlanPoint, ...]:
    order = plan.sampling_order
    combinations = itertools.product(*(values[name] for name in order)) if order else [()]
    result = []
    for index, combination in enumerate(combinations):
        parameters = {name: values[name][0] for name in values}
        parameters.update(dict(zip(order, combination)))
        coordinates = {
            (plan.parameters[name].expose_as or name): parameters[name]
            for name in order
        }
        result.append(PlanPoint(index, parameters, coordinates))
    return tuple(result)
