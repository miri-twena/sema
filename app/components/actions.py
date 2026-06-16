"""
SEMA: recommended actions (pastel yellow cards).

The "what should I do about this" list -- the part that makes SEMA an
*advisor*, not just a reporting tool. Each action is its own soft yellow
card with a leading arrow.
"""

from __future__ import annotations

import html

import streamlit as st


def render(actions: list[str]) -> None:
    if not actions:
        return

    st.markdown('<div class="sema-actions-title">Recommended actions</div>', unsafe_allow_html=True)
    for action in actions:
        st.markdown(
            f'<div class="sema-action"><span class="arrow">&#8599;</span>'
            f"<span>{html.escape(action)}</span></div>",
            unsafe_allow_html=True,
        )
