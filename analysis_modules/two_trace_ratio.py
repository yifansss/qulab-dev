"""Normalize pulsed fluorescence using two independently triggered AI records."""

from __future__ import annotations

import math
from typing import Any, Mapping

from qulab.analysis import ComputeArgumentSpec, ComputePoint, ComputeResult


class TwoTraceMeanRatio:
    name = "two_trace_mean_ratio"
    version = "1"
    input_keys = ("fluorescence_traces",)
    output_keys = ("fluorescence_signal_mean", "fluorescence_reference_mean", "fluorescence_ratio")

    @staticmethod
    def describe_arguments():
        return (
            ComputeArgumentSpec("signal_record", "integer", default=0, minimum=0),
            ComputeArgumentSpec("reference_record", "integer", default=1, minimum=0),
            ComputeArgumentSpec("channel_index", "integer", default=0, minimum=0),
            ComputeArgumentSpec("sample_start", "integer", default=0, minimum=0),
            ComputeArgumentSpec("sample_stop", "integer", default=1000, minimum=1),
            ComputeArgumentSpec("denominator_epsilon", "number", default=1.0e-12, minimum=0.0),
        )

    def setup(self, config: Mapping[str, Any], run_context: Mapping[str, Any]) -> None:
        self.signal_record = int(config.get("signal_record", 0))
        self.reference_record = int(config.get("reference_record", 1))
        self.channel_index = int(config.get("channel_index", 0))
        self.sample_start = int(config.get("sample_start", 0))
        self.sample_stop = int(config.get("sample_stop", 1000))
        self.denominator_epsilon = float(config.get("denominator_epsilon", 1.0e-12))
        if self.signal_record == self.reference_record:
            raise ValueError("signal_record and reference_record must be different")
        if self.sample_stop <= self.sample_start:
            raise ValueError("sample_stop must be greater than sample_start")

    def process_point(self, point: ComputePoint) -> ComputeResult:
        records = point.data["fluorescence_traces"]
        signal = self._record_mean(records, self.signal_record)
        reference = self._record_mean(records, self.reference_record)
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
                "sample_window": [self.sample_start, self.sample_stop],
            },
        )

    def close(self) -> None:
        pass

    def _record_mean(self, records: Any, record_index: int) -> float:
        if not isinstance(records, (list, tuple)) or record_index >= len(records):
            raise ValueError(f"missing fluorescence record {record_index}")
        record = records[record_index]
        if not isinstance(record, (list, tuple)) or self.channel_index >= len(record):
            raise ValueError(f"missing channel {self.channel_index} in fluorescence record {record_index}")
        trace = [float(value) for value in record[self.channel_index]]
        if self.sample_stop > len(trace):
            raise ValueError(
                f"sample window {self.sample_start}:{self.sample_stop} exceeds a {len(trace)}-sample record"
            )
        selected = trace[self.sample_start:self.sample_stop]
        if not selected or not all(math.isfinite(value) for value in selected):
            raise ValueError("fluorescence trace window must contain finite numeric samples")
        return sum(selected) / len(selected)

