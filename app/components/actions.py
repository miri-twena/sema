"""
SEMA: recommended actions (pastel yellow cards).

The "what should I do about this" list -- the part that makes SEMA an
*advisor*, not just a reporting tool. Each action is its own soft yellow
card with a leading arrow.
"""

from __future__ import annotations

import html

import streamlit as st


def render(actions: list[str], msg_idx: int = 0, on_context=None) -> None:
    """Render recommended-action cards. `on_context`, if given, is called with a
    widget-context dict when an action's 💬 button is clicked (passed in by
    chat.py so this stays a pure renderer -- no circular import)."""
    if not actions:
        return

    st.markdown('<div class="sema-actions-title">Recommended actions</div>', unsafe_allow_html=True)
    for i, action in enumerate(actions):
        col_action, col_btn = st.columns([9, 1])
        with col_action:
            st.markdown(
                f'<div class="sema-action"><span class="arrow">&#8599;</span>'
                f"<span>{html.escape(action)}</span></div>",
                unsafe_allow_html=True,
            )
        with col_btn:
            if on_context and st.button("💬", key=f"ctx_action_{msg_idx}_{i}", help="ספר לי עוד"):
                on_context(
                    {
                        "type": "action",
                        "label": action[:60] + ("..." if len(action) > 60 else ""),
                        "agent_prefix": (
                            "[Context: The user is asking about a specific recommended action from the previous answer.\n"
                            f"Action: '{action}'.\n"
                            "Explain how to execute this, what results to expect, and what to measure.]"
                        ),
                    }
                )
