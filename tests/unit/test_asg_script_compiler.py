from __future__ import annotations

import json

import pytest

from qulab.sequence_generation import SequenceGenerationError
from qulab.sequence_generation.asg_script import compile_asg_sequence_json
from qulab.instruments.adapters.pycontrol import PycontrolASGAdapter


def _source(*pulses) -> str:
    return json.dumps([{"channel_name": "Channel 1", "pbn": 0, "pulses": list(pulses)}])


def test_editor_json_compiles_microseconds_to_asg_nanosecond_script() -> None:
    script = compile_asg_sequence_json(
        _source({"rise": 1, "start_time": 5.0, "time_on": 20.0, "d": 10.0, "pbn": 0})
    )

    assert script == "w1 = Seq_Gen(L,5000,H,20000,L,1)\ns1 = ASG_SEQ([w1(1)])\nASG_OUT[1] = s1"


def test_repeated_pulse_expands_using_spacing() -> None:
    script = compile_asg_sequence_json(
        _source({"rise": 2, "start_time": 1.0, "time_on": 0.1, "d": 0.5, "pbn": 0})
    )

    assert "Seq_Gen(L,1000,H,100,L,400,H,100,L,1)" in script


def test_empty_and_overlapping_sequences_fail_before_hardware_upload() -> None:
    with pytest.raises(SequenceGenerationError, match="no pulse outputs"):
        compile_asg_sequence_json(json.dumps([{"channel_name": "Channel 1", "pulses": []}]))
    with pytest.raises(SequenceGenerationError, match="overlap"):
        compile_asg_sequence_json(
            _source(
                {"rise": 1, "start_time": 1.0, "time_on": 2.0, "d": 2.0},
                {"rise": 1, "start_time": 2.0, "time_on": 1.0, "d": 1.0},
            )
        )


def test_asg_arm_compiles_json_enables_used_channel_and_uploads_script() -> None:
    calls = []

    class Driver:
        def configure_output_channels(self, **kwargs):
            calls.append(("outputs", kwargs))
            return True

        def upload_and_run(self, code, **kwargs):
            calls.append(("upload", code, kwargs))
            return True

    adapter = PycontrolASGAdapter("asg", {"voltage_level": 0, "impedance": 0})
    adapter.connected = True
    adapter._driver = Driver()
    adapter.compiled_code = _source({"rise": 1, "start_time": 5.0, "time_on": 20.0, "d": 10.0})

    assert adapter.arm() is True
    assert calls[0] == ("outputs", {"channel_limit": 1, "voltage_level": 0, "impedance": 0})
    assert calls[1][0] == "upload"
    assert "ASG_OUT[1]" in calls[1][1]
    assert adapter.output_channels == [1]
