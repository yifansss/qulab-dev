from pathlib import Path

from qulab.gui.sequence_bridge import _ImportCheck, inspect_sequence_file, open_sequence_editor


def test_inspect_sequence_file_reports_hash_params_and_channels(tmp_path: Path) -> None:
    sequence = tmp_path / "rabi.seq"
    sequence.write_text("channel 1 pulse tau=${tau_s}\nparam: laser_width_s\nch5 trigger\n", encoding="utf-8")

    info = inspect_sequence_file(sequence)

    assert info.exists is True
    assert info.sha256 is not None
    assert len(info.sha256) == 64
    assert info.parameters == ["laser_width_s", "tau_s"]
    assert info.channels == ["ch1", "ch5"]
    assert info.size_bytes == sequence.stat().st_size


def test_inspect_sequence_file_missing_returns_warning(tmp_path: Path) -> None:
    info = inspect_sequence_file(tmp_path / "missing.seq")

    assert info.exists is False
    assert info.sha256 is None
    assert info.warnings


def test_open_sequence_editor_is_monkeypatchable(tmp_path: Path) -> None:
    editor = tmp_path / "sequence_editor.py"
    editor.write_text("print('editor')\n", encoding="utf-8")
    calls: list[list[str]] = []

    class Process:
        pid = 1234

    def fake_popen(command: list[str]) -> Process:
        calls.append(command)
        return Process()

    result = open_sequence_editor(
        editor,
        tmp_path / "rabi.seq",
        popen_factory=fake_popen,
        import_check=lambda python, module: _ImportCheck(True),
    )

    assert result.ok is True
    assert result.pid == 1234
    assert calls
    assert calls[0][-3].endswith("sequence_editor_launcher.py")
    assert calls[0][-2:] == [str(editor), str(tmp_path / "rabi.seq")]


def test_open_sequence_editor_missing_is_friendly(tmp_path: Path) -> None:
    result = open_sequence_editor(tmp_path / "missing.py")

    assert result.ok is False
    assert "not found" in result.message


def test_open_sequence_editor_missing_pyqt5_does_not_launch(tmp_path: Path) -> None:
    editor = tmp_path / "sequence_editor.py"
    editor.write_text("from PyQt5.QtWidgets import QApplication\n", encoding="utf-8")
    calls: list[list[str]] = []

    result = open_sequence_editor(
        editor,
        popen_factory=lambda command: calls.append(command),
        import_check=lambda python, module: _ImportCheck(False, "No module named PyQt5"),
    )

    assert result.ok is False
    assert "requires PyQt5" in result.message
    assert calls == []
