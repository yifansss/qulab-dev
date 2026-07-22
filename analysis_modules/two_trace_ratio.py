"""Normalize pulsed fluorescence using two independently triggered AI records."""

from __future__ import annotations

import math
from typing import Any, Mapping

from qulab.analysis import ComputeArgumentSpec, ComputePoint, ComputeResult


class TwoTraceMeanRatio:
    name = "two_trace_mean_ratio"
    version = "2"
    input_keys = ("fluorescence_traces",)
    output_keys = ("fluorescence_signal_mean", "fluorescence_reference_mean", "fluorescence_ratio")

    @staticmethod
    def describe_arguments():
        return (
            ComputeArgumentSpec("signal_record", "integer", default=0, minimum=0),
            ComputeArgumentSpec("reference_record", "integer", default=1, minimum=0),
            ComputeArgumentSpec("channel_index", "integer", default=0, minimum=0),
            ComputeArgumentSpec("signal_sample_start", "integer", default=0, minimum=0),
            ComputeArgumentSpec("signal_sample_stop", "integer", default=1000, minimum=1),
            ComputeArgumentSpec("reference_sample_start", "integer", default=0, minimum=0),
            ComputeArgumentSpec("reference_sample_stop", "integer", default=1000, minimum=1),
            ComputeArgumentSpec("denominator_epsilon", "number", default=1.0e-12, minimum=0.0),
        )

    def setup(self, config: Mapping[str, Any], run_context: Mapping[str, Any]) -> None:
        self.signal_record = int(config.get("signal_record", 0))
        self.reference_record = int(config.get("reference_record", 1))
        self.channel_index = int(config.get("channel_index", 0))
        legacy_start = int(config.get("sample_start", 0))
        legacy_stop = int(config.get("sample_stop", 1000))
        self.signal_sample_start = int(config.get("signal_sample_start", legacy_start))
        self.signal_sample_stop = int(config.get("signal_sample_stop", legacy_stop))
        self.reference_sample_start = int(config.get("reference_sample_start", legacy_start))
        self.reference_sample_stop = int(config.get("reference_sample_stop", legacy_stop))
        self.denominator_epsilon = float(config.get("denominator_epsilon", 1.0e-12))
        if self.signal_record == self.reference_record:
            raise ValueError("signal_record and reference_record must be different")
        self._validate_window("signal", self.signal_sample_start, self.signal_sample_stop)
        self._validate_window("reference", self.reference_sample_start, self.reference_sample_stop)

    def process_point(self, point: ComputePoint) -> ComputeResult:
        records = point.data["fluorescence_traces"]
        signal = self._record_mean(
            records, self.signal_record, self.signal_sample_start, self.signal_sample_stop
        )
        reference = self._record_mean(
            records, self.reference_record, self.reference_sample_start, self.reference_sample_stop
        )
        if abs(reference) <= self.denominator_epsilon:
            raise ValueError("reference fluorescence mean is too close to zero for a stable ratio")
        return ComputeResult(
            {
                "fluorescence_signal_mean": signal,
                "fluorescence_reference_mean": reference,
                "fluorescence_ratio": signal / reference,
            },
            units={"fluorescence_signal_mean": "V", "fluorescence_reference_mean": "V"},
            metadata={
                "signal_record": self.signal_record,
                "reference_record": self.reference_record,
                "signal_sample_window": [self.signal_sample_start, self.signal_sample_stop],
                "reference_sample_window": [self.reference_sample_start, self.reference_sample_stop],
            },
        )

    def close(self) -> None:
        pass

    @staticmethod
    def _validate_window(label: str, start: int, stop: int) -> None:
        if start < 0 or stop <= start:
            raise ValueError(f"{label}_sample_stop must be greater than {label}_sample_start >= 0")

    def _record_mean(self, records: Any, record_index: int, start: int, stop: int) -> float:
        if not isinstance(records, (list, tuple)) or record_index >= len(records):
            raise ValueError(f"missing fluorescence record {record_index}")
        record = records[record_index]
        if not isinstance(record, (list, tuple)) or self.channel_index >= len(record):
            raise ValueError(f"missing channel {self.channel_index} in fluorescence record {record_index}")
        trace = [float(value) for value in record[self.channel_index]]
        if stop > len(trace):
            raise ValueError(
                f"sample window {start}:{stop} exceeds a {len(trace)}-sample record"
            )
        selected = trace[start:stop]
        if not selected or not all(math.isfinite(value) for value in selected):
            raise ValueError("fluorescence trace window must contain finite numeric samples")
        return sum(selected) / len(selected)
