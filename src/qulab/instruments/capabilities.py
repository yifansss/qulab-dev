"""Capability names used by adapters and configs."""

from __future__ import annotations

MICROWAVE_SOURCE = "microwave_source"
PULSE_SEQUENCER = "pulse_sequencer"
DAQ_COUNTER = "daq_counter"
ANALOG_INPUT = "analog_input"
ANALOG_OUTPUT = "analog_output"
TRIGGER_SOURCE = "trigger_source"
TRIGGER_RECEIVER = "trigger_receiver"
CLOCK_PARTICIPANT = "clock_participant"
WAVEFORM_GENERATOR = "waveform_generator"

KNOWN_CAPABILITIES = {
    MICROWAVE_SOURCE,
    PULSE_SEQUENCER,
    DAQ_COUNTER,
    ANALOG_INPUT,
    ANALOG_OUTPUT,
    TRIGGER_SOURCE,
    TRIGGER_RECEIVER,
    CLOCK_PARTICIPANT,
    WAVEFORM_GENERATOR,
}
