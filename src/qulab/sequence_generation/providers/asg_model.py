"""Headless model for the sequence editor's ASG JSON (all raw times are microseconds)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..errors import SequenceGenerationError

US = 1e-6


def normalize_channel_name(name: str) -> str:
    match = re.fullmatch(r"(?:channel\s*|ch)(\d+)", name.strip(), re.IGNORECASE)
    return f"ch{int(match.group(1))}" if match else name.strip().casefold()


def _number(value: Any, code: str = "sequence_template_invalid") -> float:
    if isinstance(value, bool):
        raise SequenceGenerationError(code, "ASG timing values cannot be bool")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise SequenceGenerationError(code, f"Invalid ASG timing value {value!r}") from exc
    if not math.isfinite(result):
        raise SequenceGenerationError(code, f"Non-finite ASG timing value {value!r}")
    return result


@dataclass(frozen=True)
class PulseSelector:
    channel: str
    pulse_index: int


@dataclass(frozen=True)
class PulseView:
    channel: str
    channel_index: int
    pulse_index: int
    pbn: int
    start_s: float
    duration_s: float
    end_s: float
    block_end_s: float
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class TemplateInspection:
    path: str
    template_sha256: str
    channels: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "template_sha256": self.template_sha256,
                "channels": [dict(item) for item in self.channels], "warnings": list(self.warnings)}


class AsgSequence:
    def __init__(self, channels: list[dict[str, Any]], *, template_sha256: str = "") -> None:
        self.channels = deepcopy(channels)
        self.template_sha256 = template_sha256
        self.validate()

    @classmethod
    def from_bytes(cls, data: bytes) -> "AsgSequence":
        digest = hashlib.sha256(data).hexdigest()
        try:
            raw = json.loads(data)
        except Exception as exc:
            raise SequenceGenerationError("sequence_template_invalid", f"Invalid ASG JSON: {exc}") from exc
        if not isinstance(raw, list):
            raise SequenceGenerationError("sequence_template_invalid", "ASG template root must be a channel list")
        channels = []
        for index, channel in enumerate(raw):
            if not isinstance(channel, dict):
                raise SequenceGenerationError("sequence_template_invalid", f"Channel {index} must be a mapping")
            if "pulses" in channel:
                channels.append(deepcopy(channel)); continue
            # Exact adaptation used by the standalone editor.
            channels.append({"channel_name": f"Channel {index + 1}", "delay_off": channel.get("delay_off", 0.0),
                             "pulses": [{"pbn": channel.get("pbn", index), "rise": channel.get("rise", 1),
                                          "time_on": channel.get("time_on", 1.0), "d": channel.get("dt", 10.0),
                                          "start_time": channel.get("delay_on", 0.0), "type": "notype", "phas": 0.0}]})
        return cls(channels, template_sha256=digest)

    @classmethod
    def from_path(cls, path: Path) -> "AsgSequence":
        return cls.from_bytes(Path(path).read_bytes())

    def clone(self) -> "AsgSequence":
        return AsgSequence(self.channels, template_sha256=self.template_sha256)

    def to_bytes(self) -> bytes:
        return (json.dumps(self.channels, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

    def _pulse(self, selector: PulseSelector) -> tuple[int, int, dict[str, Any]]:
        normalized = normalize_channel_name(selector.channel)
        matches = [(i, ch) for i, ch in enumerate(self.channels)
                   if normalize_channel_name(str(ch.get("channel_name", f"Channel {i + 1}"))) == normalized]
        if not matches:
            raise SequenceGenerationError("sequence_target_missing", f"Channel '{selector.channel}' was not found")
        if len(matches) > 1:
            raise SequenceGenerationError("sequence_target_ambiguous", f"Channel '{selector.channel}' is ambiguous")
        channel_index, channel = matches[0]
        pulses = channel.get("pulses", [])
        if not isinstance(selector.pulse_index, int) or selector.pulse_index < 0 or selector.pulse_index >= len(pulses):
            raise SequenceGenerationError("sequence_target_missing", f"Pulse {selector.pulse_index} was not found in '{selector.channel}'")
        return channel_index, selector.pulse_index, pulses[selector.pulse_index]

    def pulse_view(self, selector: PulseSelector, *, masked_fields: tuple[str, ...] = ()) -> PulseView:
        ci, pi, pulse = self._pulse(selector)
        start = _number(pulse.get("start_time", 0.0)) * US
        duration = _number(pulse.get("time_on")) * US
        rise = int(pulse.get("rise", 1)); spacing = _number(pulse.get("d", duration / US)) * US
        block_end = start + (rise - 1) * spacing + duration
        critical = {key: pulse.get(key) for key in sorted(pulse) if key not in set(masked_fields)}
        identity = {"template": self.template_sha256, "channel": normalize_channel_name(selector.channel),
                    "pulse": pi, "critical": critical}
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        pbn = int(pulse.get("pbn", self.channels[ci].get("pbn", ci)))
        return PulseView(str(self.channels[ci].get("channel_name", f"Channel {ci + 1}")), ci, pi, pbn,
                         start, duration, start + duration, block_end, fingerprint)

    def set_start(self, selector: PulseSelector, value_s: float) -> None:
        _, _, pulse = self._pulse(selector); pulse["start_time"] = value_s / US

    def set_duration(self, selector: PulseSelector, value_s: float) -> None:
        _, _, pulse = self._pulse(selector)
        if int(pulse.get("rise", 1)) != 1:
            raise SequenceGenerationError("sequence_property_unsupported", "duration transform requires rise == 1")
        pulse["time_on"] = value_s / US

    def views(self) -> tuple[PulseView, ...]:
        result = []
        for ci, channel in enumerate(self.channels):
            for pi, _ in enumerate(channel.get("pulses", [])):
                result.append(self.pulse_view(PulseSelector(str(channel.get("channel_name", f"Channel {ci + 1}")), pi)))
        return tuple(result)

    def validate(self, *, allow_overlap: bool = False) -> None:
        by_channel: dict[int, list[PulseView]] = {}
        for view in self.views():
            if view.start_s < 0:
                raise SequenceGenerationError("sequence_timing_negative", "ASG pulse start cannot be negative")
            if not math.isfinite(view.duration_s) or view.duration_s <= 0:
                raise SequenceGenerationError("sequence_duration_invalid", "ASG pulse duration must be positive and finite")
            by_channel.setdefault(view.channel_index, []).append(view)
        if not allow_overlap:
            for views in by_channel.values():
                ordered = sorted(views, key=lambda item: (item.start_s, item.pulse_index))
                for previous, current in zip(ordered, ordered[1:]):
                    if current.start_s < previous.block_end_s - 1e-15:
                        raise SequenceGenerationError("sequence_overlap", f"Pulses overlap on {current.channel}")


def inspect_template(path: str | Path) -> TemplateInspection:
    resolved = Path(path)
    model = AsgSequence.from_path(resolved)
    channels = []
    for index, channel in enumerate(model.channels):
        name = str(channel.get("channel_name", f"Channel {index + 1}"))
        pulses = [model.pulse_view(PulseSelector(name, pi)).to_dict() for pi in range(len(channel.get("pulses", [])))]
        channels.append({"name": name, "normalized_name": normalize_channel_name(name), "index": index,
                         "pbn": int(channel.get("pbn", index)), "pulses": pulses})
    return TemplateInspection(str(resolved), model.template_sha256, tuple(channels))


def list_channels(inspection: TemplateInspection) -> tuple[Mapping[str, Any], ...]:
    return inspection.channels


def list_pulses(channel: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    return tuple(channel.get("pulses", ()))


def build_target_selector(path: str | Path, channel: str, pulse_index: int, *, alias: str | None = None) -> dict[str, Any]:
    model = AsgSequence.from_path(Path(path)); view = model.pulse_view(PulseSelector(channel, pulse_index))
    return {"alias": alias, "channel": channel, "pulse": pulse_index, "fingerprint": view.fingerprint}
