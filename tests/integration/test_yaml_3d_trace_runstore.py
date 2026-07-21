import csv
import json
from pathlib import Path

from qulab.config import run_dry_config
from qulab.viewer.plot_data import heatmap_from_run, trace_from_run


ROOT = Path(__file__).resolve().parents[2]


def test_yaml_3d_trace_runstore_writes_point_matched_trace_csv(tmp_path) -> None:
    result = run_dry_config(ROOT / "configs" / "experiments" / "dry_run_3d_trace.yaml", tmp_path)
    run_path = result.run_path

    metadata = json.loads((run_path / "metadata.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_path / "dataset_manifest.json").read_text(encoding="utf-8"))

    with (run_path / "tables" / "points.csv").open(encoding="utf-8", newline="") as file:
        points = list(csv.DictReader(file))
    with (run_path / "tables" / "traces" / "photon_bins.csv").open(encoding="utf-8", newline="") as file:
        trace_rows = list(csv.DictReader(file))
    with (run_path / "tables" / "summaries" / "counts_mean.csv").open(encoding="utf-8", newline="") as file:
        summary_rows = list(csv.DictReader(file))

    assert result.executor_state == "completed"
    assert metadata["point_count"] == 8
    assert metadata["completed_point_count"] == 8
    assert len(points) == 8
    assert len(summary_rows) == 8
    assert len(trace_rows) == 8 * 1000
    assert manifest["data_vars"]["counts_mean"]["dims"] == ["ao_v", "rf_freq_hz", "tau_s"]
    assert manifest["data_vars"]["photon_bins"]["dims"] == ["ao_v", "rf_freq_hz", "tau_s", "time_s"]

    first_point = points[0]
    first_summary = summary_rows[0]
    first_trace = trace_rows[:1000]
    assert first_point["point_id"] == "p000001"
    assert first_point["ao_v"] == "0.0"
    assert first_point["rf_freq_hz"] == "2860000000.0"
    assert first_point["tau_s"] == "2e-08"
    assert first_summary["point_id"] == "p000001"
    assert first_summary["ao_v"] == "0.0"
    assert first_summary["rf_freq_hz"] == "2860000000.0"
    assert first_summary["tau_s"] == "2e-08"
    assert first_summary["value"] == "600.5"
    assert {row["point_id"] for row in first_trace} == {"p000001"}
    assert first_trace[0]["time_s"] == "0.0"
    assert first_trace[999]["time_s"] == "999.0"
    assert first_trace[0]["value"] == "101"
    assert first_trace[999]["value"] == "1100"

    heatmap = heatmap_from_run(
        run_path,
        "counts_mean",
        "rf_freq_hz",
        "tau_s",
        selectors={"ao_v": 0.0},
        backend="csv",
    )
    trace = trace_from_run(
        run_path,
        "photon_bins",
        {"ao_v": 0.0, "rf_freq_hz": 2860000000.0, "tau_s": 2e-08},
        backend="csv",
    )

    assert heatmap.values.shape == (2, 2)
    assert heatmap.x.tolist() == [2860000000.0, 2862000000.0]
    assert heatmap.y.tolist() == [2e-08, 4e-08]
    assert heatmap.values[0, 0] == 600.5
    assert trace.values.shape == (1000,)
    assert trace.values[0] == 101.0
    assert trace.point_status == "ok"
