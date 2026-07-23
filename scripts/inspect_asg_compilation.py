#!/usr/bin/env python
"""Print the exact ASG script and pulse timing generated from an editor JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qulab.sequence_generation.asg_script import compile_asg_sequence_json
from qulab.sequence_generation.providers.asg_model import AsgSequence, PulseSelector


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Qulab ASG JSON compilation without hardware output.")
    parser.add_argument("sequence", type=Path, help="ASG editor JSON file, for example configs/sequences/rabi.json")
    args = parser.parse_args()

    source = args.sequence.read_text(encoding="utf-8")
    try:
        decoded = json.loads(source)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON: {exc}") from exc
    if isinstance(decoded, dict) and isinstance(decoded.get("saved_artifact"), dict):
        artifact = decoded["saved_artifact"].get("path", "(path not provided)")
        raise SystemExit(
            "This is a Sequence Editor protocol report, not an ASG pulse JSON file. "
            f"Inspect/copy the raw saved artifact instead: {artifact}"
        )
    if not isinstance(decoded, list):
        raise SystemExit("ASG pulse JSON must have a channel-list root.")
    model = AsgSequence.from_bytes(source.encode("utf-8"))
    print(f"source: {args.sequence.resolve()}")
    print("expected high intervals:")
    for channel_index, channel in enumerate(model.channels):
        name = str(channel.get("channel_name", f"Channel {channel_index + 1}"))
        for pulse_index, _pulse in enumerate(channel.get("pulses", ())):
            view = model.pulse_view(PulseSelector(name, pulse_index))
            print(
                f"  {view.channel} pulse {pulse_index}: "
                f"HIGH {view.start_s * 1e6:.9g} us -> {view.end_s * 1e6:.9g} us "
                f"({view.duration_s * 1e6:.9g} us)"
            )
    print("\ncompiled ASG script:\n")
    print(compile_asg_sequence_json(source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
