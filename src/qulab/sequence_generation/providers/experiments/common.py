"""Shared SI timing and ASG serialization for curated families.

These models define digital gates only; they do not model analog microwave
phase, power, cabling, or the physical response of an experiment.
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from ...errors import SequenceGenerationError
from ...models import GeneratedSequencePoint, SequenceFamilySpec, SequencePlanValidationResult, SequenceSweepPlan
from ..asg_model import AsgSequence, normalize_channel_name
from ..asg_transforms import preview_from_model

RESOLUTION_S = 1e-9
DEFAULT_CHANNELS = {"laser_channel": "Channel 1", "mw_gate_channel": "Channel 2",
                    "readout_gate_channel": "Channel 3", "daq_trigger_channel": "Channel 6"}


def validate_time(name: str, value: float, *, allow_zero: bool = False) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
        raise SequenceGenerationError("sequence_parameter_invalid", f"{name} must be {'non-negative' if allow_zero else 'positive'} and finite")
    steps = value / RESOLUTION_S
    if not math.isclose(steps, round(steps), rel_tol=0, abs_tol=1e-6):
        raise SequenceGenerationError("sequence_resolution_invalid", f"{name} must align to {RESOLUTION_S:g} s")
    return value


def build_model(pulses: list[tuple[str, float, float, str]], channels: Mapping[str, str], period_s: float) -> AsgSequence:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    role_by_channel = {value: key for key, value in channels.items()}
    for role, start, duration, label in pulses:
        channel = channels[role]
        grouped[channel].append({"pbn": _pbn(channel), "rise": 1, "time_on": duration * 1e6, "d": period_s * 1e6,
                                 "start_time": start * 1e6, "type": label, "phas": 0.0})
    raw = []
    for channel in sorted(grouped, key=_pbn):
        raw.append({"channel_name": channel, "delay_off": period_s * 1e6, "pbn": _pbn(channel),
                    "role": role_by_channel.get(channel), "pulses": sorted(grouped[channel], key=lambda item: item["start_time"])})
    return AsgSequence(raw)


def _pbn(channel: str) -> int:
    digits = "".join(character for character in channel if character.isdigit())
    if not digits: raise SequenceGenerationError("sequence_parameter_invalid", f"Channel '{channel}' needs a numeric ASG identity")
    return int(digits) - 1


class CuratedFamilyProvider:
    family_id = "curated"
    version = "1"

    def __init__(self) -> None: self.plan: SequenceSweepPlan | None = None
    def configure_plan(self, plan: SequenceSweepPlan) -> None: self.plan = plan
    def describe(self) -> SequenceFamilySpec: raise NotImplementedError
    def timing(self, parameters: Mapping[str, Any]) -> tuple[list[tuple[str, float, float, str]], Mapping[str, Any]]: raise NotImplementedError

    def _channels(self) -> dict[str, str]:
        channels = dict(DEFAULT_CHANNELS)
        if self.plan:
            channels.update({key: str(value) for key, value in self.plan.options.get("channels", {}).items() if key in channels})
        if len(set(channels.values())) != len(channels):
            raise SequenceGenerationError("sequence_parameter_invalid", "Curated channel roles must be distinct")
        return channels

    def validate_plan(self, plan: SequenceSweepPlan) -> SequencePlanValidationResult:
        try:
            self.configure_plan(plan); self._channels()
            policy = plan.options.get("period_policy", "fixed")
            if policy not in {"fixed", "grow_with_scan"}:
                raise SequenceGenerationError("sequence_parameter_invalid", f"Unknown period_policy '{policy}'")
        except SequenceGenerationError as exc: return SequencePlanValidationResult((exc.as_issue(),))
        return SequencePlanValidationResult()

    def _model(self, parameters: Mapping[str, Any]) -> tuple[AsgSequence, Mapping[str, Any]]:
        pulses, summary = self.timing(parameters)
        last_edge = max(start + duration for _, start, duration, _ in pulses)
        requested = validate_time("sequence_period_s", parameters["sequence_period_s"])
        policy = self.plan.options.get("period_policy", "fixed") if self.plan else "fixed"
        if policy == "fixed" and requested < last_edge:
            raise SequenceGenerationError("sequence_duration_invalid", f"sequence_period_s {requested:g} is shorter than pulse end {last_edge:g}")
        period = max(requested, last_edge) if policy == "grow_with_scan" else requested
        model = build_model(pulses, self._channels(), period); model.validate()
        return model, {**summary, "period_policy": policy, "duration_s": period}

    def generate_point(self, parameters: Mapping[str, Any], *, template: Path | None) -> GeneratedSequencePoint:
        model, summary = self._model(parameters); channels = self._channels()
        metadata = {"family": self.family_id, "provider_version": self.version, "duration_s": summary["duration_s"],
                    "required_acquisition_s": float(parameters["readout_s"]),
                    "readout_window_s": float(parameters["readout_s"]),
                    "trigger_channels": [normalize_channel_name(channels["daq_trigger_channel"])],
                    "output_channels": sorted(set(channels.values())), "channel_roles": channels,
                    "parameters": dict(parameters), "timing": dict(summary)}
        return GeneratedSequencePoint(model.to_bytes(), ".json", metadata)

    def preview_point(self, parameters: Mapping[str, Any], *, template: Path | None):
        model, _ = self._model(parameters); return preview_from_model(model, {})
