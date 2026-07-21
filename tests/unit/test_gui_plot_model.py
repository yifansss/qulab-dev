from __future__ import annotations

from qulab.core import DataPoint, LogMessage
from qulab.gui.plot_model import PlotSeries


def test_plot_series_uses_first_numeric_coord_and_nested_counts_mean() -> None:
    series = PlotSeries()

    series.handle_event(
        DataPoint(
            point_id="p000001",
            coords={"tau_s": 2.0e-8, "avg": 0},
            data={"counts": {"counts_mean": 1001.0, "photon_bins": [1000, 1001, 1002]}},
        )
    )

    assert series.points == [(2.0e-8, 1001.0)]


def test_plot_series_uses_index_when_no_numeric_coord_and_ignores_non_numeric_y() -> None:
    series = PlotSeries()

    series.handle_event(DataPoint(coords={"label": "a"}, data={"counts_mean": 4}))
    series.handle_event(DataPoint(coords={"label": "b"}, data={"status": "ok"}))
    series.handle_event(LogMessage(message="not a data point"))

    assert series.points == [(0.0, 4.0)]
