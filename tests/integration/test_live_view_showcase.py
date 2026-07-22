from pathlib import Path

from qulab.gui.controller import OperatorController


def test_live_view_showcase_covers_saved_live_only_waiting_and_plot_shapes(tmp_path):
    config = Path(__file__).parents[2] / "configs" / "experiments" / "live_view_showcase.yaml"
    controller = OperatorController(tmp_path)
    controller.load_config(config)
    assert controller.prepare().ok
    assert controller.start_dry_run().status == "completed"
    specs = {item.key: item for item in controller.list_live_data_specs()}
    assert specs["saved_scale"].saved and specs["saved_scale"].status == "active"
    assert not specs["live_only_scale"].saved
    assert specs["waiting_preview"].status == "waiting"
    assert specs["raw_trace"].data_kind == "vector"
    assert specs["raw_matrix"].data_kind == "matrix"
    heat = controller.get_live_plot_data(controller.set_live_selection(
        ("source_value",), plot_type="heatmap", x_dim="frequency_hz", y_dim="power_dbm"))
    assert heat.values.shape == (2, 3)
    point_id = controller.list_live_points()[-1]["point_id"]
    trace = controller.get_live_plot_data(controller.set_live_selection(("raw_matrix",), point_id=point_id, channel=1))
    assert trace.values.tolist() == [0.2, 0.3]
    before = controller.last_run_path
    controller.clear_live_display()
    assert controller.list_live_points() == () and controller.last_run_path == before
    stored = set(controller.list_run_data_keys())
    assert "saved_scale" in stored and "live_only_scale" not in stored


def test_repository_runtime_files_do_not_embed_user_home_paths():
    root = Path(__file__).parents[2]
    candidates = [root / "src", root / "configs", root / "docs", root / "README.md"]
    offenders = []
    for candidate in candidates:
        paths = [candidate] if candidate.is_file() else candidate.rglob("*")
        for path in paths:
            if path.is_file() and path.suffix in {".py", ".yaml", ".yml", ".md"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if ("/" + "Users/") in text or ("C:" + "\\Users\\") in text:
                    offenders.append(str(path.relative_to(root)))
    assert offenders == []
