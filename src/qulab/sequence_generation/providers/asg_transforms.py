"""Deterministic target transforms, propagation, and anchor constraints."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import SequenceGenerationError
from ..models import SequenceSweepPlan
from .asg_model import AsgSequence, PulseSelector, PulseView


@dataclass(frozen=True)
class PreviewPulse:
    alias: str | None
    selector: Mapping[str, Any]
    start_s: float
    end_s: float
    level: int = 1
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"alias": self.alias, "selector": dict(self.selector), "start_s": self.start_s,
                "end_s": self.end_s, "level": self.level, "label": self.label}


@dataclass(frozen=True)
class PreviewChannel:
    name: str
    pbn: int
    pulses: tuple[PreviewPulse, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "pbn": self.pbn, "pulses": [item.to_dict() for item in self.pulses]}


@dataclass(frozen=True)
class SequencePreview:
    channels: tuple[PreviewChannel, ...]
    total_duration_s: float
    warnings: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"channels": [item.to_dict() for item in self.channels], "total_duration_s": self.total_duration_s,
                "warnings": [dict(item) for item in self.warnings]}


def resolve_targets(model: AsgSequence, plan: SequenceSweepPlan) -> dict[str, PulseSelector]:
    result = {}
    seen = set()
    for alias, raw in plan.targets.items():
        if alias in seen or not isinstance(raw, Mapping):
            raise SequenceGenerationError("sequence_target_ambiguous", f"Duplicate or invalid target alias '{alias}'")
        seen.add(alias)
        selector = PulseSelector(str(raw.get("channel", "")), raw.get("pulse"))
        view = model.pulse_view(selector)
        saved = raw.get("fingerprint")
        if saved is not None and saved != view.fingerprint:
            raise SequenceGenerationError("sequence_target_stale", f"Target '{alias}' fingerprint no longer matches template")
        result[str(alias)] = selector
    return result


def _edge(view: PulseView, edge: str) -> float:
    if edge == "start": return view.start_s
    if edge == "end": return view.end_s
    raise SequenceGenerationError("sequence_property_unsupported", f"Unsupported target edge '{edge}'")


def _split_reference(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or "." not in value:
        raise SequenceGenerationError("sequence_target_missing", f"Invalid target reference {value!r}")
    alias, edge = value.rsplit(".", 1)
    return alias, edge


def transform_sequence(base: AsgSequence, plan: SequenceSweepPlan, parameters: Mapping[str, Any]) -> AsgSequence:
    model = base.clone()
    targets = resolve_targets(base, plan)
    writes: dict[tuple[str, str], tuple[str, float, Mapping[str, Any]]] = {}
    for parameter_name in sorted(plan.parameters):
        value_plan = plan.parameters[parameter_name]
        transform = value_plan.transform
        if not transform:
            continue
        alias = transform.get("target"); prop = str(transform.get("property", ""))
        if alias not in targets:
            raise SequenceGenerationError("sequence_target_missing", f"Transform target '{alias}' does not exist")
        if prop not in {"start", "duration", "end", "shift", "gap_after"}:
            raise SequenceGenerationError("sequence_property_unsupported", f"Unsupported transform property '{prop}'")
        if parameter_name not in parameters:
            raise SequenceGenerationError("sequence_parameter_missing", f"Missing point parameter '{parameter_name}'")
        value = float(parameters[parameter_name])
        if not math.isfinite(value):
            raise SequenceGenerationError("sequence_parameter_invalid", f"Parameter '{parameter_name}' must be finite")
        physical_property = "start" if prop in {"start", "shift", "gap_after"} else "end"
        key = (str(alias), physical_property)
        if key in writes:
            raise SequenceGenerationError("sequence_transform_conflict", f"Multiple transforms write {key[0]}.{key[1]}")
        writes[key] = (prop, value, transform)
    changed_boundaries: list[tuple[str, float, float, Mapping[str, Any]]] = []
    for (alias, _), (prop, value, transform) in sorted(writes.items()):
        selector = targets[alias]; before = base.pulse_view(selector); old_boundary = before.end_s
        if prop == "start": model.set_start(selector, value)
        elif prop == "duration": model.set_duration(selector, value)
        elif prop == "end": model.set_duration(selector, value - model.pulse_view(selector).start_s)
        elif prop == "shift": model.set_start(selector, before.start_s + value)
        else:
            reference_alias = transform.get("reference")
            if reference_alias not in targets:
                raise SequenceGenerationError("sequence_target_missing", f"gap_after reference '{reference_alias}' does not exist")
            reference = model.pulse_view(targets[reference_alias])
            model.set_start(selector, reference.end_s + value)
        after = model.pulse_view(selector); changed_boundaries.append((alias, old_boundary, after.end_s, transform))

    shifted: dict[tuple[int, int], float] = {}
    for alias, old_boundary, new_boundary, transform in changed_boundaries:
        propagation = transform.get("propagation", {})
        if not isinstance(propagation, Mapping):
            raise SequenceGenerationError("sequence_transform_conflict", "propagation must be a mapping")
        mode = propagation.get("mode", "none"); delta = new_boundary - old_boundary
        if mode in {"none", "constraints"} or abs(delta) < 1e-18:
            continue
        source = base.pulse_view(targets[alias])
        selected: list[PulseSelector] = []
        if mode == "shift_after":
            scope = propagation.get("scope", "same_channel")
            if scope not in {"same_channel", "all_channels"}:
                raise SequenceGenerationError("sequence_property_unsupported", f"Unsupported propagation scope '{scope}'")
            for view in base.views():
                if view.channel_index == source.channel_index and view.pulse_index == source.pulse_index:
                    continue
                if scope == "same_channel" and view.channel_index != source.channel_index:
                    continue
                # Inclusive threshold: pulses starting exactly at the old target end move.
                if view.start_s >= old_boundary - 1e-15:
                    selected.append(PulseSelector(view.channel, view.pulse_index))
        elif mode == "shift_group":
            group = propagation.get("group")
            members = plan.groups.get(group)
            if not isinstance(members, (list, tuple)) or len(set(members)) != len(members):
                raise SequenceGenerationError("sequence_target_missing", f"Invalid target group '{group}'")
            for member in members:
                if member not in targets:
                    raise SequenceGenerationError("sequence_target_missing", f"Group member '{member}' does not exist")
                if member != alias:
                    selected.append(targets[member])
        else:
            raise SequenceGenerationError("sequence_property_unsupported", f"Unsupported propagation mode '{mode}'")
        for selector in selected:
            view = model.pulse_view(selector); key = (view.channel_index, view.pulse_index)
            if key in shifted and not math.isclose(shifted[key], delta, abs_tol=1e-15):
                raise SequenceGenerationError("sequence_transform_conflict", "Two propagations shift one pulse by different deltas")
            if key not in shifted:
                model.set_start(selector, view.start_s + delta); shifted[key] = delta

    _apply_constraints(model, plan, targets, writes)
    model.validate(allow_overlap=bool(plan.options.get("allow_overlap", False)))
    return model


def _apply_constraints(model: AsgSequence, plan: SequenceSweepPlan, targets: Mapping[str, PulseSelector],
                       direct_writes: Mapping[tuple[str, str], Any]) -> None:
    constraints = []
    writers = set(direct_writes)
    for raw in plan.constraints:
        if raw.get("type") != "anchor":
            raise SequenceGenerationError("sequence_property_unsupported", f"Unsupported constraint type '{raw.get('type')}'")
        target_alias, target_edge = _split_reference(raw.get("target")); ref_alias, ref_edge = _split_reference(raw.get("reference"))
        if target_alias not in targets or ref_alias not in targets:
            raise SequenceGenerationError("sequence_target_missing", "Anchor target/reference does not exist")
        key = (target_alias, target_edge)
        if key in writers or (target_edge == "start" and (target_alias, "start") in writers):
            raise SequenceGenerationError("sequence_transform_conflict", f"Multiple writers for {target_alias}.{target_edge}")
        writers.add(key); constraints.append((target_alias, target_edge, ref_alias, ref_edge, float(raw.get("offset_s", 0.0))))
    pending = list(constraints); completed = set()
    while pending:
        progress = False
        target_names = {(item[0], item[1]) for item in pending}
        for item in list(pending):
            ta, te, ra, re, offset = item
            if (ra, re) in target_names and (ra, re) not in completed:
                continue
            reference_value = _edge(model.pulse_view(targets[ra]), re) + offset
            current = model.pulse_view(targets[ta])
            if te == "start": model.set_start(targets[ta], reference_value)
            elif te == "end": model.set_duration(targets[ta], reference_value - current.start_s)
            else: raise SequenceGenerationError("sequence_property_unsupported", f"Unsupported anchor edge '{te}'")
            pending.remove(item); completed.add((ta, te)); progress = True
        if not progress:
            cycle = [f"{item[0]}.{item[1]}" for item in pending]
            raise SequenceGenerationError("sequence_constraint_cycle", f"Anchor constraint cycle: {' -> '.join(cycle)}",
                                          context={"cycle": cycle})


def preview_from_model(model: AsgSequence, targets: Mapping[str, PulseSelector]) -> SequencePreview:
    reverse = {(model.pulse_view(selector).channel_index, model.pulse_view(selector).pulse_index): alias for alias, selector in targets.items()}
    channels = []
    for ci, channel in enumerate(model.channels):
        pulses = []
        for pi, _ in enumerate(channel.get("pulses", [])):
            view = model.pulse_view(PulseSelector(str(channel.get("channel_name", f"Channel {ci + 1}")), pi))
            pulses.append(PreviewPulse(reverse.get((ci, pi)), {"channel": view.channel, "pulse": pi}, view.start_s, view.end_s,
                                       label=reverse.get((ci, pi))))
        channels.append(PreviewChannel(str(channel.get("channel_name", f"Channel {ci + 1}")), int(channel.get("pbn", ci)), tuple(pulses)))
    total = max((view.block_end_s for view in model.views()), default=0.0)
    return SequencePreview(tuple(channels), total)
