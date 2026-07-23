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
    driver.configure_free_mode = lambda: True
    driver.upload_waveform = lambda code: False
    driver.set_loop = lambda loop: (_ for _ in ()).throw(AssertionError("loop must not be set"))

    assert driver.upload_and_run("ASG_OUT[1] = s1", arm_only=True) is False


def test_output_channel_configuration_propagates_register_failure(monkeypatch) -> None:
    cls = _driver_class(monkeypatch)
    driver = object.__new__(cls)
    driver._is_sim = False
    driver._check_connection = lambda: None
    driver.set_param_int = lambda path, value: path != "/Device/C1/Output"

    with pytest.raises(RuntimeError, match=r"/Device/C1/Output"):
        driver.configure_output_channels(channel_limit=1)
