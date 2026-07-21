"""Generate one simulated RunStore run with CSV baseline and optional Zarr."""

from __future__ import annotations

import math
import random
from pathlib import Path

from qulab.core import DataPoint, LogMessage, MeasurementCompleted, MeasurementStarted, RunCompleted, RunStarted
from qulab.storage import RunStore


def main() -> None:
    random.seed(20260628)
    root = Path("runs/simulated_zarr")
    experiment_name = "simulated_nv_rabi_zarr_demo"
    store = RunStore(
        root=root,
        experiment_name=experiment_name,
        config={
            "schema_version": 1,
            "name": experiment_name,
            "storage": {"backend": "zarr"},
            "procedure": "simulated 2D mw_freq_hz x tau_s with CSV baseline and optional Zarr arrays",
        },
        resolved_config={
            "mw_freq_hz": {"start": 2.864e9, "stop": 2.876e9, "points": 7},
            "tau_s": {"start": 20e-9, "stop": 300e-9, "points": 6},
            "readout_bins": 32,
            "analog_channels": ["ai0", "ai1"],
            "storage": {"backends": ["csv", "zarr"]},
        },
    )

    store.open()
    store.handle_event(RunStarted(run_id=store.run_id, procedure_name=experiment_name))
    store.handle_event(LogMessage(level="info", message="Starting simulated Zarr NV storage run"))

    freqs = [2.864e9 + i * (12e6 / 6) for i in range(7)]
    taus = [20e-9 + i * (280e-9 / 5) for i in range(6)]
    center = 2.8702e9
    linewidth = 2.0e6
    contrast = 0.22
    rabi_period = 235e-9
    bin_count = 32
    point_counter = 0

    for freq in freqs:
        detuning = (freq - center) / linewidth
        odmr_dip = contrast * math.exp(-0.5 * detuning * detuning)
        for tau in taus:
            point_counter += 1
            point_id = f"p{point_counter:06d}"
            coords = {"mw_freq_hz": round(freq, 3), "tau_s": tau}
            store.handle_event(MeasurementStarted(point_id=point_id, coords=coords))

            rabi = 0.5 * (1.0 + math.cos(2.0 * math.pi * tau / rabi_period))
            expected = 1800.0 * (1.0 - odmr_dip * rabi)
            counts_mean = expected + random.gauss(0.0, 18.0)
            counts_std = 34.0 + abs(random.gauss(0.0, 4.0))

            photon_bins = []
            for bin_index in range(bin_count):
                decay = math.exp(-bin_index / 18.0)
                value = expected / bin_count * (0.62 + 0.58 * decay) + random.gauss(0.0, 2.0)
                photon_bins.append(round(max(value, 0.0), 3))

            analog_trace = []
            for channel_index, phase in enumerate([0.0, math.pi / 4.0]):
                channel = []
                for bin_index in range(bin_count):
                    t = bin_index / (bin_count - 1)
                    envelope = math.exp(-2.2 * t)
                    voltage = 0.022 * math.sin(2 * math.pi * 4.0 * t + phase) * envelope
                    voltage += 0.0025 * channel_index + random.gauss(0.0, 0.0007)
                    channel.append(round(voltage, 6))
                analog_trace.append(channel)

            store.handle_event(
                DataPoint(
                    point_id=point_id,
                    coords=coords,
                    data={
                        "counts_mean": round(counts_mean, 3),
                        "counts_std": round(counts_std, 3),
                        "photon_bins": photon_bins,
                        "analog_trace": analog_trace,
                    },
                    metadata={
                        "source": "simulated DataPoint constructed by scripts/simulate_zarr_runstore.py",
                        "unit_counts": "count",
                        "unit_analog_trace": "V",
                        "time_step_s": 16e-9,
                        "channels": ["ai0", "ai1"],
                    },
                )
            )
            store.handle_event(MeasurementCompleted(point_id=point_id, status="ok", coords=coords))

    store.handle_event(LogMessage(level="info", message=f"Completed {point_counter} simulated Zarr measurement points"))
    store.handle_event(RunCompleted(run_id=store.run_id, status="completed"))
    store.close(status="completed")

    print(store.run_path)
    print(point_counter)


if __name__ == "__main__":
    main()
