import pytest

from qulab.instruments import InstrumentConfigurationError, InstrumentRegistry, build_context_from_resources
from qulab.instruments.adapters import MockDAQCounter, MockMicrowaveSource, MockPulseSequencer


def test_registry_builds_default_mock_adapters() -> None:
    registry = InstrumentRegistry()

    mw = registry.create("mw", {"adapter": "mock_microwave", "frequency_hz": "2870000000"})
    asg = registry.create("asg", {"adapter": "mock_asg"})
    daq = registry.create("daq", {"adapter": "mock_daq"})

    assert isinstance(mw, MockMicrowaveSource)
    assert isinstance(asg, MockPulseSequencer)
    assert isinstance(daq, MockDAQCounter)
    assert mw.set_frequency(2.88e9) == 2.88e9
    assert daq.read_counts()["photon_bins"] == [1000, 1001, 1002]


def test_registry_accepts_adaptor_alias_for_legacy_configs() -> None:
    asg = InstrumentRegistry().create("asg", {"adaptor": "mock_asg"})

    assert isinstance(asg, MockPulseSequencer)


def test_registry_rejects_unknown_adapter() -> None:
    with pytest.raises(InstrumentConfigurationError, match="Unknown adapter"):
        InstrumentRegistry().create("mw", {"adapter": "real_hardware"})


def test_build_context_connects_resources_on_load() -> None:
    context = build_context_from_resources(
        {
            "mw": {"adapter": "mock_microwave", "connect_on_load": True},
            "daq": {"adapter": "mock_daq", "connect_on_load": False},
        }
    )

    assert context.resources["mw"].connected is True
    assert context.resources["daq"].connected is False


def test_mock_pulse_sequencer_accepts_sequence_file_key() -> None:
    asg = InstrumentRegistry().create("asg", {"adapter": "mock_asg"})

    result = asg.load_sequence(sequence_file="sequences/rabi.yaml")

    assert result == {"sequence_file": "sequences/rabi.yaml", "sequence": None}
    assert asg.snapshot()["settings"]["sequence_file"] == "sequences/rabi.yaml"
