from __future__ import annotations

import plotly.graph_objects as go


def _empty_figure(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark",
        title=title,
        annotations=[
            {
                "text": "沒有可顯示的資料（No data available）",
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
            }
        ],
    )
    return fig


def distribution_pie(data: dict[str, int], title: str) -> go.Figure:
    """Build a pie chart for a categorical count distribution."""
    if not data:
        return _empty_figure(title)

    fig = go.Figure(
        data=[
            go.Pie(
                labels=list(data),
                values=list(data.values()),
                name=title,
                hole=0.0,
            )
        ]
    )
    fig.update_layout(template="plotly_dark", title=title)
    return fig


def distribution_bar(
    data: dict[str, int], title: str, horizontal: bool = False
) -> go.Figure:
    """Build a bar chart for a categorical count distribution."""
    if not data:
        return _empty_figure(title)

    labels = list(data)
    values = list(data.values())
    trace = (
        go.Bar(x=values, y=labels, orientation="h")
        if horizontal
        else go.Bar(x=labels, y=values, orientation="v")
    )
    fig = go.Figure(data=[trace])
    fig.update_layout(template="plotly_dark", title=title)
    return fig


def phase_waterfall(phases: dict[str, float | None], title: str) -> go.Figure:
    """Build a relative waterfall chart from phase durations in seconds."""
    available = [(name, duration) for name, duration in phases.items() if duration is not None]
    if not available:
        return _empty_figure(title)

    names = [name for name, _ in available]
    durations = [duration for _, duration in available]
    fig = go.Figure(
        data=[
            go.Waterfall(
                x=names,
                y=durations,
                measure=["relative"] * len(available),
                connector={"line": {"color": "#666"}},
            )
        ]
    )
    fig.update_layout(template="plotly_dark", title=title, yaxis_title="秒（s）")
    return fig


def heatmap_grid(
    matrix: dict[str, dict[str, int]],
    title: str,
    x_label: str = "",
    y_label: str = "",
) -> go.Figure:
    """Build a heatmap from a row-keyed, column-keyed count matrix."""
    if not matrix:
        return _empty_figure(title)

    rows = list(matrix)
    columns: list[str] = []
    for row in matrix.values():
        for column in row:
            if column not in columns:
                columns.append(column)

    if not columns:
        return _empty_figure(title)

    values = [[matrix[row].get(column, 0) for column in columns] for row in rows]
    fig = go.Figure(data=[go.Heatmap(x=columns, y=rows, z=values)])
    fig.update_layout(
        template="plotly_dark",
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
    )
    return fig


__all__ = [
    "distribution_bar",
    "distribution_pie",
    "heatmap_grid",
    "phase_waterfall",
]
