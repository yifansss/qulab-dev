import os

import pytest

from qulab.config import load_yaml_config, parse_experiment_config

pytestmark = pytest.mark.hardware


def test_pycontrol_connect_only_smoke_from_env_config() -> None:
    config_path = os.environ.get("QULAB_HARDWARE_CONFIG")
    if not config_path:
        pytest.skip("Set QULAB_HARDWARE_CONFIG=/path/to/real_nv_setup.yaml to run hardware smoke tests")

    parsed = parse_experiment_config(load_yaml_config(config_path))
    assert parsed.validation.ok

    failures: list[str] = []
    for name, resource in parsed.context.resources.items():
        try:
            resource.connect()
            assert resource.health_check()["ok"]
            assert resource.snapshot()["connected"] is True
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
        finally:
            resource.disconnect()

    assert not failures
