from pathlib import Path

from qulab.config import load_experiment_config
from qulab.gui.sequence_bridge import default_sequence_editor_path
from qulab.paths import project_root, resolve_project_path
from qulab.sequence_files import inspect_sequence_file


def test_resolve_project_path_prefers_project_root() -> None:
    path = resolve_project_path("configs/experiments/bench_05_pse_ai1_asg_triggered_trace.template.yaml")

    assert path == project_root() / "configs" / "experiments" / "bench_05_pse_ai1_asg_triggered_trace.template.yaml"


def test_config_loader_accepts_project_relative_path() -> None:
    config = load_experiment_config("configs/experiments/bench_05_pse_ai1_asg_triggered_trace.template.yaml")

    assert config["name"] == "bench_05_pse_ai1_asg_triggered_trace"


def test_sequence_inspection_accepts_project_relative_path() -> None:
    info = inspect_sequence_file("configs/sequences/asg_ai1_trigger_smoke.json")

    assert info.exists is True
    assert info.sha256
    assert "ch6" in info.channels


def test_default_sequence_editor_is_project_local() -> None:
    path = default_sequence_editor_path(project_root())

    assert path == project_root() / "tools" / "sequence_editor" / "sequence_editor.py"
    assert path.exists()


def test_missing_project_relative_path_returns_project_candidate() -> None:
    path = resolve_project_path("configs/sequences/does_not_exist.seq")

    assert path == project_root() / "configs" / "sequences" / "does_not_exist.seq"
