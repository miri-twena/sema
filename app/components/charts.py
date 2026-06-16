"""
SEMA: Plotly chart builders (light pastel theme).

Every chart shares one look, driven by the brand palette in theme.py:
soft pastel series, white/transparent background, faint gridlines, rounded
modern tooltips. This replaces the old plotly_dark template.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from components.theme import CHART_COLORWAY, TOKENS

_TRANSPARENT = "rgba(0,0,0,0)"
# Translucent lavender for the soft area fill under a line chart.
_AREA_FILL = "rgba(124, 140, 255, 0.12)"


def _hover(y_format: str | None) -> str:
    """Hover text for a y value, formatted to match the metric type."""
    if y_format == "currency":
        return "%{x}<br>$%{y:,.0f}<extra></extra>"
    if y_format == "percent":
        return "%{x}<br>%{y:.1f}%<extra></extra>"
    return "%{x}<br>%{y:,.0f}<extra></extra>"


def _apply_y_format(fig: go.Figure, y_format: str | None) -> None:
    """Format the y-axis ticks: '$1.6M' for currency, '20%' for percent.

    Only money/percent get a prefix/suffix -- a count axis (orders, sessions)
    stays a plain number, which is why the agent tells us the metric type.
    """
    if y_format == "currency":
        fig.update_yaxes(tickprefix="$", tickformat="~s")
    elif y_format == "percent":
        fig.update_yaxes(ticksuffix="%")


def _style(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=TOKENS["text"])),
        colorway=CHART_COLORWAY,
        paper_bgcolor=_TRANSPARENT,
        plot_bgcolor=_TRANSPARENT,
        font=dict(family="Inter, sans-serif", color=TOKENS["text"], size=12),
        margin=dict(l=10, r=10, t=46, b=10),
        legend=dict(title_text="", orientation="h", y=-0.18, font=dict(size=11)),
        hoverlabel=dict(
            bgcolor=TOKENS["surface"],
            bordercolor=TOKENS["border"],
            font=dict(family="Inter, sans-serif", color=TOKENS["text"], size=12),
        ),
    )
    fig.update_xaxes(
        showgrid=False,
        linecolor=TOKENS["border"],
        tickcolor=TOKENS["border"],
        title_text="",
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=TOKENS["border_soft"],
        zeroline=False,
        title_text="",
    )
    return fig


def line_chart(spec: dict) -> go.Figure:
    df: pd.DataFrame = spec["df"]
    y_format = spec.get("y_format")
    fig = px.line(df, x=spec["x"], y=spec["y"], markers=True)
    fig.update_traces(
        line=dict(color=TOKENS["primary"], width=3),
        marker=dict(color=TOKENS["primary"], size=7),
        # Soft area under the line gives the "advisor dashboard" feel; pairs
        # with the tozero range below so the fill reads from a true baseline.
        fill="tozeroy",
        fillcolor=_AREA_FILL,
        hovertemplate=_hover(y_format),
    )
    # Start the axis at 0 so dips/spikes aren't visually exaggerated by an
    # auto-zoomed baseline -- an honest trend for a business answer.
    fig.update_yaxes(rangemode="tozero")

    highlight_x = spec.get("highlight_x")
    if highlight_x is not None and highlight_x in set(df[spec["x"]]):
        highlight_row = df[df[spec["x"]] == highlight_x].iloc[0]
        fig.add_trace(
            go.Scatter(
                x=[highlight_x],
                y=[highlight_row[spec["y"]]],
                mode="markers",
                marker=dict(color=TOKENS["coral"], size=15, line=dict(color="#FFFFFF", width=2)),
                showlegend=False,
                hovertemplate=_hover(y_format),
            )
        )

    fig = _style(fig, spec["title"])
    _apply_y_format(fig, y_format)
    return fig


def bar_chart(spec: dict) -> go.Figure:
    df: pd.DataFrame = spec["df"]
    y_format = spec.get("y_format")
    fig = px.bar(df, x=spec["x"], y=spec["y"], color_discrete_sequence=[TOKENS["primary"]])
    fig.update_traces(marker_line_width=0, hovertemplate=_hover(y_format))
    fig.update_layout(bargap=0.35)
    fig.update_yaxes(rangemode="tozero")
    fig = _style(fig, spec["title"])
    _apply_y_format(fig, y_format)
    return fig


def grouped_bar_chart(spec: dict) -> go.Figure:
    df: pd.DataFrame = spec["df"]
    y_format = spec.get("y_format")
    fig = px.bar(
        df,
        x=spec["x"],
        y=spec["y"],
        color=spec["color"],
        barmode="group",
        color_discrete_sequence=CHART_COLORWAY,
    )
    fig.update_traces(marker_line_width=0, hovertemplate=_hover(y_format))
    fig.update_yaxes(rangemode="tozero")
    fig = _style(fig, spec["title"])
    _apply_y_format(fig, y_format)
    return fig


def donut_chart(spec: dict) -> go.Figure:
    df: pd.DataFrame = spec["df"]
    fig = px.pie(
        df,
        names=spec["names"],
        values=spec["values"],
        hole=0.6,
        color_discrete_sequence=CHART_COLORWAY,
    )
    # Show the slice label + percent on the chart so it's readable without
    # hovering; multi-slice donuts now cycle the full brand palette.
    fig.update_traces(
        textinfo="label+percent",
        textfont=dict(family="Inter, sans-serif"),
        marker=dict(line=dict(color=TOKENS["surface"], width=2)),
    )
    return _style(fig, spec["title"])


_BUILDERS = {
    "line": line_chart,
    "bar": bar_chart,
    "grouped_bar": grouped_bar_chart,
    "donut": donut_chart,
}


def render(spec: dict) -> go.Figure:
    return _BUILDERS[spec["kind"]](spec)
