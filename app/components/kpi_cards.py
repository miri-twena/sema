"""
SEMA: KPI tile rendering (pastel cards).

Same idea as a Power BI card visual: label, big number, optional delta.
Each card in a response cycles through the brand pastel tints so a row of
KPIs reads as a calm, coordinated set rather than three identical boxes.
"""

from __future__ import annotations

import streamlit as st

from components.theme import KPI_TINTS


def _compact(value) -> str:
    """Abbreviate large numbers so they fit a glanceable KPI card.

    1,672,356 -> "1.67M", 824,068 -> "824.1K", 950 -> "950". The exact
    figure is still available in the insight text and any result table -- a
    KPI card should read at a glance, like a Power BI card visual.
    """
    n = float(value)
    a = abs(n)
    if a >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if a >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,.0f}"


def _format_value(value, fmt: str) -> str:
    if fmt == "currency":
        return f"${_compact(value)}"
    if fmt == "percent":
        return f"{value:.1f}%"
    if fmt == "number":
        return _compact(value)
    if fmt == "ratio":
        return f"{value:.2f}x"
    return str(value)


def render(kpis: list[dict]) -> None:
    if not kpis:
        return

    cols = st.columns(len(kpis))
    for i, (col, kpi) in enumerate(zip(cols, kpis)):
        bg, label_color = KPI_TINTS[i % len(KPI_TINTS)]
        value_str = _format_value(kpi["value"], kpi.get("format", "text"))

        delta_html = ""
        if "delta" in kpi:
            delta = kpi["delta"]
            up = delta >= 0
            arrow = "▲" if up else "▼"
            cls = "up" if up else "down"
            delta_label = kpi.get("delta_label", "")
            delta_html = (
                f'<div class="sema-kpi-delta {cls}">'
                f"{arrow} {abs(delta):.1f}% {delta_label}"
                f"</div>"
            )

        with col:
            st.markdown(
                f"""
                <div class="sema-kpi" style="background:{bg};">
                    <div class="sema-kpi-label" style="color:{label_color};">{kpi['label']}</div>
                    <div class="sema-kpi-value">{value_str}</div>
                    {delta_html}
                </div>
                """,
                unsafe_allow_html=True,
            )
