"""
SEMA: chat message rendering.

User messages render as a right-aligned lavender bubble (self-contained
HTML). SEMA responses render inside a real bordered st.container -- which,
unlike a raw HTML div, genuinely wraps the Streamlit widgets inside it
(insight text, KPI cards, charts, table, actions) into one card.
"""

from __future__ import annotations

import re

import streamlit as st

from components import actions, charts, kpi_cards, tables
from components.theme import connected_flow_logo

# Hebrew letters (incl. presentation forms). We decide a turn's direction
# from the *question's* language, not per paragraph: if the question has any
# Hebrew, the whole answer renders right-to-left.
_HEBREW_RE = re.compile(r"[֐-׿יִ-ﭏ]")


def is_rtl(text: str) -> bool:
    """True if `text` contains Hebrew -- the turn should render right-to-left."""
    return bool(text and _HEBREW_RE.search(text))


def render_user_message(text: str, rtl: bool = False) -> None:
    direction = "rtl" if rtl else "ltr"
    st.markdown(
        f'<div class="sema-row user"><div class="sema-bubble user" dir="{direction}">'
        f"{text}</div></div>",
        unsafe_allow_html=True,
    )


def render_assistant_message(response: dict, rtl: bool = False) -> None:
    with st.container(border=True):
        # Hidden marker the CSS keys off (via :has()) to flip this whole card
        # to RTL when the question was in Hebrew.
        if rtl:
            st.markdown('<span class="sema-rtl-flag"></span>', unsafe_allow_html=True)

        st.markdown(
            f'<div class="sema-assistant-head">{connected_flow_logo(22)}'
            f'<span class="name">SEMA</span></div>',
            unsafe_allow_html=True,
        )

        # Rendered as plain markdown (not wrapped in an HTML div) so the
        # **bold** and bullet lists in the insight text parse correctly.
        # Streamlit treats $...$ as LaTeX math, so a dollar amount like
        # "$831K" would render as an italic formula -- escape literal dollar
        # signs to "\$" so currency in the narrative shows as plain text.
        st.markdown(response["insight_text"].replace("$", "\\$"))

        if response.get("kpis"):
            st.write("")
            kpi_cards.render(response["kpis"])

        for chart_spec in response.get("charts", []):
            fig = charts.render(chart_spec)
            st.plotly_chart(fig, use_container_width=True)

        if response.get("table") is not None:
            tables.render(response["table"], response.get("table_title"), rtl=rtl)

        if response.get("recommended_actions"):
            actions.render(response["recommended_actions"])


def render_messages(messages: list[dict]) -> None:
    for message in messages:
        rtl = message.get("rtl", False)
        if message["role"] == "user":
            render_user_message(message["content"], rtl)
        else:
            render_assistant_message(message["content"], rtl)
