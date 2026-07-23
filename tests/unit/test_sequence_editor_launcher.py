import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _launcher_module():
    path = ROOT / "src/qulab/gui/sequence_editor_launcher.py"
    spec = importlib.util.spec_from_file_location("sequence_editor_launcher_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_writes_pulse_channel_list_not_protocol_report(tmp_path: Path) -> None:
    launcher = _launcher_module()
    destination = tmp_path / "rabi.json"
    pulses = [{"channel_name": "Channel 1", "pulses": [{"pbn": 0, "time_on": 1.0}]}]

    artifact = launcher._write_sequence_artifact(destination, pulses)

    assert json.loads(destination.read_text(encoding="utf-8")) == pulses
    assert artifact["path"] == str(destination)
    assert len(artifact["sha256"]) == 64


def test_launcher_refuses_protocol_object_as_sequence_data(tmp_path: Path) -> None:
    launcher = _launcher_module()
    try:
        launcher._write_sequence_artifact(tmp_path / "rabi.json", {"protocol_version": 1})
    except RuntimeError as exc:
        assert "channel list" in str(exc)
    else:
        raise AssertionError("protocol report was written as a sequence")
