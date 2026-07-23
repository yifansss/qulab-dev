from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PYCONTROL = ROOT / "drivers" / "pycontrol"


def _driver_class(monkeypatch):
    monkeypatch.syspath_prepend(str(PYCONTROL))
    sys.modules.pop("PulseGenerator.driver", None)
    return importlib.import_module("PulseGenerator.driver").ASG24100Driver


def test_upload_and_run_propagates_upload_failure(monkeypatch) -> None:
    cls = _driver_class(monkeypatch)
    driver = object.__new__(cls)
    driver._is_sim = False
    driver._check_connection = lambda: None
    driver.configure_free_mode = lambda: (_ for _ in ()).throw(AssertionError("mode must not be configured"))
    driver.upload_waveform = lambda code: False
    driver.set_loop = lambda loop: (_ for _ in ()).throw(AssertionError("loop must not be set"))

    with pytest.raises(RuntimeError, match="waveform upload was rejected"):
        driver.upload_and_run("ASG_OUT[1] = s1", arm_only=True, configure_mode=False)


def test_upload_and_run_reports_rejected_loop(monkeypatch) -> None:
    cls = _driver_class(monkeypatch)
    driver = object.__new__(cls)
    driver._is_sim = False
    driver._check_connection = lambda: None
    driver.upload_waveform = lambda code: True
    driver.set_loop = lambda loop: False

    with pytest.raises(RuntimeError, match=r"/loop=1"):
        driver.upload_and_run("ASG_OUT[1] = s1", arm_only=True, configure_mode=False)


def test_upload_and_run_can_explicitly_configure_playback_mode(monkeypatch) -> None:
    cls = _driver_class(monkeypatch)
    driver = object.__new__(cls)
    driver._is_sim = False
    driver._check_connection = lambda: None
    calls = []
    driver.configure_free_mode = lambda: calls.append("mode") or True
    driver.upload_waveform = lambda code: calls.append("upload") or True
    driver.set_loop = lambda loop: calls.append(("loop", loop)) or True

    assert driver.upload_and_run("ASG_OUT[1] = s1", loop=1, arm_only=True, configure_mode=True) is True
    assert calls == ["mode", "upload", ("loop", 1)]


def test_output_channel_configuration_propagates_register_failure(monkeypatch) -> None:
    cls = _driver_class(monkeypatch)
    driver = object.__new__(cls)
    driver._is_sim = False
    driver._check_connection = lambda: None
    driver.set_param_int = lambda path, value: not path.startswith("/Device/ChildCard")

    assert driver.configure_output_channels(channel_limit=1) is True
    with pytest.raises(RuntimeError, match=r"/Device/ChildCard1/OutputLevel"):
        driver.configure_output_channels(channel_limit=1, configure_childcards=True)
