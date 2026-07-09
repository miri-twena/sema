"""
SEMA: sidebar.

Brand mark, the active client (with a live connection status and a link to
the admin page to switch), clickable suggested-question chips for that client,
and session history. Everything client-specific now comes from the client
registry, so the sidebar adapts automatically when you switch clients.
"""

from __future__ import annotations

import streamlit as st

from sema_core import client_registry
from components.theme import connected_flow_logo
from sema_core.db import check_connection


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

        client = client_registry.get_active_client()
        connected = check_connection()
        status_cls = "connected" if connected else "disconnected"
        status_text = "Connected" if connected else "Disconnected"
        st.markdown(
            f"""
            <div class="sema-section-label">Active client</div>
            <div class="sema-source">
                <div class="sema-source-name">{client["label"]}</div>
                <div class="sema-status {status_cls}"><span class="dot"></span>{status_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Link to the admin page where clients are listed and switched.
        st.page_link("pages/admin.py", label="⚙ Switch client", use_container_width=True)

        # Start a fresh conversation: clears both the UI transcript and the
        # agent's multi-turn memory so follow-ups don't carry over.
        if st.button("✦ New conversation", key="new_conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.agent_history = []
            st.session_state.history = []
            st.session_state.pending_question = None
            st.rerun()

        st.markdown('<div class="sema-section-label">Suggested questions</div>', unsafe_allow_html=True)
        # Per-client starter questions. Keys sq0.. drive the pastel chip colors
        # in styles.py.
        for i, question in enumerate(client.get("suggested_questions", [])[:4]):
            if st.button(question, key=f"sq{i}", use_container_width=True):
                st.session_state.pending_question = question
                st.rerun()

        if st.session_state.get("history"):
            st.markdown('<div class="sema-section-label">Session history</div>', unsafe_allow_html=True)
            for past_question in st.session_state.history:
                st.markdown(f'<div class="sema-history-item">{past_question}</div>', unsafe_allow_html=True)
