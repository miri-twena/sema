"""
SEMA: sidebar.

Brand mark, a live (real, not hardcoded) data-source connection status,
clickable suggested-question chips, and session history.
"""

from __future__ import annotations

import streamlit as st

from components.theme import connected_flow_logo
from db import check_connection
from query_router import SUGGESTED_QUESTIONS


def render() -> None:
    with st.sidebar:
        st.markdown(
            f"""
            <div class="sema-brand">
                {connected_flow_logo(34)}
                <span class="sema-brand-name">SEMA</span>
            </div>
            <div class="sema-brand-sub">AI Business Advisor</div>
            """,
            unsafe_allow_html=True,
        )

        connected = check_connection()
        status_cls = "connected" if connected else "disconnected"
        status_text = "Connected" if connected else "Disconnected"
        st.markdown(
            f"""
            <div class="sema-section-label">Data sources</div>
            <div class="sema-source">
                <div class="sema-source-name">Synthetic E-commerce Database</div>
                <div class="sema-status {status_cls}"><span class="dot"></span>{status_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="sema-section-label">Suggested questions</div>', unsafe_allow_html=True)
        # Show a short, curated set in the sidebar (the rest still work when
        # typed). Keys sq0.. drive the per-chip pastel colors in styles.py.
        for i, question in enumerate(SUGGESTED_QUESTIONS[:4]):
            if st.button(question, key=f"sq{i}", use_container_width=True):
                st.session_state.pending_question = question
                st.rerun()

        if st.session_state.get("history"):
            st.markdown('<div class="sema-section-label">Session history</div>', unsafe_allow_html=True)
            for past_question in st.session_state.history:
                st.markdown(f'<div class="sema-history-item">{past_question}</div>', unsafe_allow_html=True)
