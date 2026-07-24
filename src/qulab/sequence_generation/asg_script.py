"""Compile standalone-editor ASG JSON into CIQTEK Seq_Gen script."""

from __future__ import annotations

import json
import math
from typing import Any

from .errors import SequenceGenerationError
from .providers.asg_model import AsgSequence


def compile_asg_sequence_json(source: str) -> str:
    try:
        raw = json.loads(source)
    except json.JSONDecodeError as exc:
        raise SequenceGenerationError("sequence_compile_invalid_json", f"Invalid ASG sequence JSON: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise SequenceGenerationError("sequence_compile_empty", "ASG sequence must contain at least one channel")

    model = AsgSequence.from_bytes(source.encode("utf-8"))
    lines: list[str] = []
    used_channels: set[int] = set()
    for index, channel in enumerate(model.channels):
        pulses = channel.get("pulses", [])
        if not pulses:
            continue
        channel_number = _channel_number(channel, index)
        if channel_number in used_channels:
            raise SequenceGenerationError("sequence_compile_duplicate_channel", f"ASG channel {channel_number} is duplicated")
        used_channels.add(channel_number)
        segments = _compile_channel_segments(pulses, channel_number)
        waveform = f"w{channel_number}"
        sequence = f"s{channel_number}"
        lines.extend(
            [
                f"{waveform} = Seq_Gen({','.join(segments)})",
                f"{sequence} = ASG_SEQ([{waveform}(1)])",
                f"ASG_OUT[{channel_number}] = {sequence}",
            ]
        )
    if not lines:
        raise SequenceGenerationError("sequence_compile_empty", "ASG sequence has no pulse outputs")
    # Match the vendor SDK example: every statement, including the final one,
    # is newline-terminated before the buffer is submitted to the parser.
    return "\n".join(lines) + "\n"


def is_asg_sequence_json(source: str) -> bool:
    try:
        value = json.loads(source)
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(value, list)


def _channel_number(channel: dict[str, Any], index: int) -> int:
    """Return the one-based physical PB output selected by zero-based ``pbn``.

    ``channel_name`` is an editor label and may be reordered independently of
    the physical output.  Treating labels such as ``Channel 5`` as hardware
    addresses silently routed pulses to the wrong connector whenever ``pbn``
    and the display order differed.
    """

    pulses = channel.get("pulses", [])
    raw_pbn = channel.get("pbn")
    pulse_pbns = {
        int(pulse["pbn"])
        for pulse in pulses
        if isinstance(pulse, dict) and pulse.get("pbn") is not None
    }
    if raw_pbn is None:
        if len(pulse_pbns) == 1:
            raw_pbn = next(iter(pulse_pbns))
        elif not pulse_pbns:
            raw_pbn = index
        else:
            raise SequenceGenerationError(
                "sequence_compile_pbn_conflict",
                f"Channel {index + 1} contains pulses assigned to multiple PB outputs: {sorted(pulse_pbns)}",
            )
    pbn = int(raw_pbn)
    if pulse_pbns and pulse_pbns != {pbn}:
        raise SequenceGenerationError(
            "sequence_compile_pbn_conflict",
            f"Channel {index + 1} pbn={pbn} conflicts with pulse pbn values {sorted(pulse_pbns)}",
        )
    number = pbn + 1
    if number < 1 or number > 24:
        raise SequenceGenerationError(
            "sequence_compile_channel",
            f"ASG pbn must be in 0..23, got {pbn}",
        )
    return number


def _compile_channel_segments(pulses: list[dict[str, Any]], channel: int) -> list[str]:
    intervals: list[tuple[int, int]] = []
    for pulse_index, pulse in enumerate(pulses):
        try:
            count = int(pulse.get("rise", 1))
            start_ns = _to_ns(pulse.get("start_time", 0.0), f"channel {channel} pulse {pulse_index} start")
            width_ns = _to_ns(pulse.get("time_on"), f"channel {channel} pulse {pulse_index} width")
            spacing_ns = _to_ns(pulse.get("d", pulse.get("time_on")), f"channel {channel} pulse {pulse_index} spacing")
        except (TypeError, ValueError) as exc:
            raise SequenceGenerationError("sequence_compile_timing", f"Invalid timing on channel {channel} pulse {pulse_index}") from exc
        if count < 1 or width_ns < 1 or start_ns < 0:
            raise SequenceGenerationError("sequence_compile_timing", f"Invalid timing on channel {channel} pulse {pulse_index}")
        if count > 1 and spacing_ns < width_ns:
            raise SequenceGenerationError(
                "sequence_compile_overlap",
                f"Repeated pulses overlap on channel {channel} pulse {pulse_index}",
            )
        intervals.extend((start_ns + repeat * spacing_ns, start_ns + repeat * spacing_ns + width_ns) for repeat in range(count))

    intervals.sort()
    segments: list[str] = []
    cursor = 0
    for start, end in intervals:
        if start < cursor:
            raise SequenceGenerationError("sequence_compile_overlap", f"Pulses overlap on ASG channel {channel}")
        if start > cursor:
            segments.extend(("L", str(start - cursor)))
        segments.extend(("H", str(end - start)))
        cursor = end
    # ASG basic waveforms must occupy an integral number of 4 ns words.  The
    # vendor GUI pads this automatically; make the uploaded DSL explicit.
    trailing_low_ns = 1 + (-(cursor + 1) % 4)
    segments.extend(("L", str(trailing_low_ns)))
    return segments


def _to_ns(value: Any, label: str) -> int:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} is not finite")
    nanoseconds = number * 1000.0
    rounded = round(nanoseconds)
    if not math.isclose(nanoseconds, rounded, rel_tol=0.0, abs_tol=1e-6):
        raise SequenceGenerationError("sequence_compile_resolution", f"{label} must align to the 1 ns ASG grid")
    return int(rounded)
