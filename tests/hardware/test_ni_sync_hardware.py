import os

import pytest

from qulab.config import load_yaml_config, parse_experiment_config


pytestmark = pytest.mark.hardware


def test_ni_sync_driver_connect_from_env_config() -> None:
    config_path = os.environ.get("QULAB_NI_SYNC_HARDWARE_CONFIG")
    if not config_path:
        pytest.skip("Set QULAB_NI_SYNC_HARDWARE_CONFIG to run NI sync hardware tests")

    parsed = parse_experiment_config(load_yaml_config(config_path))
    daq = parsed.context.resources.get("daq")
    if daq is None:
        pytest.skip("Hardware config must define a 'daq' resource")

    daq.connect()
    try:
        assert daq.health_check()["ok"]
        assert daq.snapshot()["settings"]["driver"] in {"sync", "custom"}
    finally:
        daq.disconnect()
