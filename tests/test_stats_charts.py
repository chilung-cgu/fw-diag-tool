from __future__ import annotations

import plotly.graph_objects as go

from fw_diag_tool.gui.charts.stats_charts import (
    distribution_bar,
    distribution_pie,
    heatmap_grid,
    phase_waterfall,
)


def _assert_dark_figure(fig: go.Figure, title: str) -> None:
    assert fig.layout.template.layout is not None
    assert fig.layout.template.layout.paper_bgcolor == "rgb(17,17,17)"
    assert fig.layout.title.text == title


def test_distribution_pie_builds_pie_trace() -> None:
    fig = distribution_pie({"Read": 3, "Write": 2}, "Commands")

    assert len(fig.data) == 1
    assert isinstance(fig.data[0], go.Pie)
    assert list(fig.data[0].labels) == ["Read", "Write"]
    assert list(fig.data[0].values) == [3, 2]
    _assert_dark_figure(fig, "Commands")


def test_distribution_pie_empty_data_is_renderable() -> None:
    fig = distribution_pie({}, "Empty")

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0
    _assert_dark_figure(fig, "Empty")


def test_distribution_pie_preserves_zero_values() -> None:
    fig = distribution_pie({"Read": 0, "Write": 1}, "Commands")

    assert list(fig.data[0].values) == [0, 1]


def test_distribution_bar_builds_vertical_bar_trace() -> None:
    fig = distribution_bar({"Endpoint": 4, "Bridge": 1}, "Topology")

    assert len(fig.data) == 1
    assert isinstance(fig.data[0], go.Bar)
    assert fig.data[0].orientation == "v"
    assert list(fig.data[0].x) == ["Endpoint", "Bridge"]
    assert list(fig.data[0].y) == [4, 1]
    _assert_dark_figure(fig, "Topology")


def test_distribution_bar_builds_horizontal_bar_trace() -> None:
    fig = distribution_bar({"Gen4": 5, "Gen3": 2}, "Link speeds", horizontal=True)

    assert len(fig.data) == 1
    assert fig.data[0].orientation == "h"
    assert list(fig.data[0].x) == [5, 2]
    assert list(fig.data[0].y) == ["Gen4", "Gen3"]


def test_distribution_bar_empty_data_is_renderable() -> None:
    fig = distribution_bar({}, "Empty", horizontal=True)

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0
    _assert_dark_figure(fig, "Empty")


def test_distribution_bar_accepts_negative_counts() -> None:
    fig = distribution_bar({"error": -1}, "Counts")

    assert list(fig.data[0].y) == [-1]


def test_phase_waterfall_builds_relative_phase_trace() -> None:
    fig = phase_waterfall({"bootloader": 1.2, "kernel": 3.4}, "Boot")

    assert len(fig.data) == 1
    assert isinstance(fig.data[0], go.Waterfall)
    assert list(fig.data[0].x) == ["bootloader", "kernel"]
    assert list(fig.data[0].y) == [1.2, 3.4]
    assert list(fig.data[0].measure) == ["relative", "relative"]
    _assert_dark_figure(fig, "Boot")


def test_phase_waterfall_skips_unknown_phase_durations() -> None:
    fig = phase_waterfall({"bootloader": None, "kernel": 3.4, "userspace": None}, "Boot")

    assert len(fig.data) == 1
    assert list(fig.data[0].x) == ["kernel"]
    assert list(fig.data[0].y) == [3.4]


def test_phase_waterfall_empty_data_is_renderable() -> None:
    fig = phase_waterfall({}, "Empty")

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0
    _assert_dark_figure(fig, "Empty")


def test_heatmap_grid_builds_rectangular_trace() -> None:
    fig = heatmap_grid(
        {"src-a": {"dst-a": 2, "dst-b": 1}, "src-b": {"dst-a": 3}},
        "Endpoints",
        x_label="Destination",
        y_label="Source",
    )

    assert len(fig.data) == 1
    assert isinstance(fig.data[0], go.Heatmap)
    assert list(fig.data[0].x) == ["dst-a", "dst-b"]
    assert list(fig.data[0].y) == ["src-a", "src-b"]
    assert [list(row) for row in fig.data[0].z] == [[2, 1], [3, 0]]
    assert fig.layout.xaxis.title.text == "Destination"
    assert fig.layout.yaxis.title.text == "Source"
    _assert_dark_figure(fig, "Endpoints")


def test_heatmap_grid_empty_data_is_renderable() -> None:
    fig = heatmap_grid({}, "Empty")

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0
    _assert_dark_figure(fig, "Empty")


def test_heatmap_grid_collects_columns_from_all_rows() -> None:
    fig = heatmap_grid({"a": {"x": 1}, "b": {"y": 2}}, "Sparse")

    assert list(fig.data[0].x) == ["x", "y"]
    assert [list(row) for row in fig.data[0].z] == [[1, 0], [0, 2]]


def test_heatmap_grid_preserves_zero_counts() -> None:
    fig = heatmap_grid({"a": {"x": 0}}, "Zeros")

    assert [list(row) for row in fig.data[0].z] == [[0]]
