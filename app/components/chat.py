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
from components.theme import TOKENS, connected_flow_logo

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


# --- widget sub-conversations -------------------------------------------------
# Every widget (KPI/chart/table/action) gets a 💬 button. Clicking it stores a
# "widget context" in session state; main.py prefixes the next question with it
# so the agent focuses on that element. kpi_cards/actions stay pure renderers --
# we pass _set_widget_context to them as a callback (no import of chat there, so
# no circular import); the chart/table buttons live here and call it directly.


def _set_widget_context(ctx: dict) -> None:
    """Store the focused widget context and rerun so the chip shows."""
    st.session_state.widget_context = ctx
    st.rerun()


def _chart_ctx_button(spec: dict, msg_idx: int, chart_idx: int) -> None:
    label = spec.get("title", "גרף")
    if st.button("💬 שאל על הגרף", key=f"ctx_chart_{msg_idx}_{chart_idx}"):
        _set_widget_context(
            {
                "type": "chart",
                "label": label,
                "agent_prefix": (
                    "[Context: The user is asking about a specific chart from the previous answer.\n"
                    f"Chart title: '{label}', Type: {spec.get('kind', '')}, "
                    f"X-axis: {spec.get('x', '')}, Y-axis: {spec.get('y', '')}.\n"
                    "Focus your answer on this chart specifically.]"
                ),
            }
        )


def _table_ctx_button(title: str | None, df, msg_idx: int) -> None:
    if df is None or (hasattr(df, "empty") and df.empty):
        return
    label = title or "טבלת נתונים"
    n_rows = len(df) if hasattr(df, "__len__") else "?"
    columns = list(df.columns) if hasattr(df, "columns") else "unknown"
    if st.button("💬 שאל על הטבלה", key=f"ctx_table_{msg_idx}"):
        _set_widget_context(
            {
                "type": "table",
                "label": f"{label} ({n_rows} שורות)",
                "agent_prefix": (
                    "[Context: The user is asking about a specific data table from the previous answer.\n"
                    f"Table title: '{label}', Columns: {columns}.\n"
                    "Focus your answer on this table specifically.]"
                ),
            }
        )


def render_assistant_message(response: dict, rtl: bool = False, msg_idx: int = 0) -> None:
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
            kpi_cards.render(response["kpis"], msg_idx=msg_idx, on_context=_set_widget_context)

        for chart_idx, chart_spec in enumerate(response.get("charts", [])):
            fig = charts.render(chart_spec)
            st.plotly_chart(fig, use_container_width=True)
            _chart_ctx_button(chart_spec, msg_idx=msg_idx, chart_idx=chart_idx)

        if response.get("table") is not None:
            tables.render(response["table"], response.get("table_title"), rtl=rtl)
            _table_ctx_button(response.get("table_title"), response["table"], msg_idx=msg_idx)

        if response.get("recommended_actions"):
            actions.render(response["recommended_actions"], msg_idx=msg_idx, on_context=_set_widget_context)


def render_messages(messages: list[dict]) -> None:
    # msg_idx counts only assistant messages, giving each its widget buttons a
    # stable unique key across reruns (so clicking 💬 on an OLD answer works).
    assistant_idx = 0
    for i, message in enumerate(messages):
        rtl = message.get("rtl", False)
        if message["role"] == "user":
            # A thin separator before each new turn (except the first) so the
            # multi-turn transcript reads as distinct question/answer blocks.
            if i > 0:
                st.markdown(
                    f'<hr style="border:none; border-top:1px solid {TOKENS["border"]}; '
                    f'margin:0.6rem 0;">',
                    unsafe_allow_html=True,
                )
            render_user_message(message["content"], rtl)
        else:
            render_assistant_message(message["content"], rtl, msg_idx=assistant_idx)
            assistant_idx += 1
