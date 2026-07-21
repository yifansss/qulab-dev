"""Offline example that writes a concrete three-point Rabi sequence bundle.

This is an ordinary user script, not Qulab's planned pre-run generator hook.
Run it before loading the experiment config, then point ``sequence_bundles`` at
the generated ``manifest.yaml``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

import yaml


def build_bundle(output_dir: Path, tau_values_s: Iterable[float]) -> Path:
    output_dir = output_dir.resolve()
    sequence_dir = output_dir / "sequences"
    sequence_dir.mkdir(parents=True, exist_ok=True)
    values = [float(value) for value in tau_values_s]
    entries = []
    for index, tau_s in enumerate(values):
        tau_ns = tau_s * 1e9
        label = f"tau_{tau_ns:g}ns".replace(".", "p")
        entry_id = f"point_{index:04d}_{label}"
        sequence_path = sequence_dir / f"{entry_id}.json"
        sequence = _rabi_sequence(tau_s)
        sequence_path.write_text(json.dumps(sequence, indent=2) + "\n", encoding="utf-8")
        entries.append(
            {
                "id": entry_id,
                "coordinates": {"tau_s": tau_s},
                "sequence_file": str(Path("sequences") / sequence_path.name),
                "sha256": hashlib.sha256(sequence_path.read_bytes()).hexdigest(),
                "metadata": {
                    "duration_s": 8e-6,
                    "required_acquisition_s": 8e-6,
                    "trigger_channels": ["ch6"],
                    "output_channels": ["ch1", "ch6"],
                },
            }
        )
    manifest = {
        "schema_version": 1,
        "kind": "sequence_bundle",
        "id": "rabi_tau",
        "resource": "asg",
        "format": "pycontrol_asg_json",
        "coordinates": {"tau_s": {"unit": "s", "values": values}},
        "entries": entries,
        "generator": {
            "script": "examples/generate_rabi_sequence_bundle.py",
            "mode": "offline_user_script",
        },
    }
    manifest_path = output_dir / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest_path


def _rabi_sequence(tau_s: float) -> list[dict]:
    """Return concrete pycontrol-ASG JSON data; pulse times use microseconds."""

    tau_us = tau_s * 1e6
    return [
        {
            "channel_name": "Channel 1",
            "delay_off": 0.0,
            "pulses": [
                {
                    "rise": 1,
                    "time_on": tau_us,
                    "d": 10.0,
                    "type": "notype",
                    "phas": 0.0,
                    "pbn": 0,
                    "start_time": 3.0,
                }
            ],
            "pbn": 0,
        },
        {
            "channel_name": "Channel 6",
            "delay_off": 0.0,
            "pulses": [
                {
                    "rise": 1,
                    "time_on": 2.0,
                    "d": 10.0,
                    "type": "notype",
                    "phas": 0.0,
                    "pbn": 5,
                    "start_time": 5.0,
                }
            ],
            "pbn": 5,
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--tau-ns", type=float, nargs="+", default=[20.0, 40.0, 60.0])
    args = parser.parse_args()
    manifest = build_bundle(args.output_dir, (value * 1e-9 for value in args.tau_ns))
    print(manifest)


if __name__ == "__main__":
    main()
