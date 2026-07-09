"""
SEMA: main Streamlit app.

Entry point: `streamlit run app/main.py`.

Flow per user message:
  user question -> query_router.detect_intent() -> insight_builder.build()
  -> response dict -> components/chat.py renders it

No LLM yet -- intent detection is rule-based (query_router.py) and every
insight is computed live from Postgres via queries.py + insight_builder.py.
This file is presentation/wiring only.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from sema_core import client_registry
from components import chat, sidebar, styles
from sema_core.alerts_engine import evaluate_all_alerts
from components.alerts_panel import render as render_alerts
from components.theme import TOKENS, connected_flow_logo
from sema_core.wiring import get_response

_ICON_PATH = Path(__file__).parent / "assets" / "sema_icon.svg"

st.set_page_config(
    page_title="SEMA",
    page_icon=str(_ICON_PATH) if _ICON_PATH.exists() else "✦",
    layout="wide",
)
styles.inject()

if "active_client_id" not in st.session_state:
    st.session_state.active_client_id = client_registry.DEFAULT_CLIENT_ID
if "messages" not in st.session_state:
    st.session_state.messages = []
if "history" not in st.session_state:
    st.session_state.history = []
# Conversation memory in Claude API format (alternating user/assistant text),
# passed to the agent so follow-up questions have context. Kept separate from
# `messages` (which holds rich UI response dicts, not API-shaped turns).
if "agent_history" not in st.session_state:
    st.session_state.agent_history = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None
# Widget sub-conversations: when set (by a 💬 button on a KPI/chart/table/
# action), the next question is prefixed with this element's context so the
# agent focuses on it. None = a general question. See components/chat.py.
if "widget_context" not in st.session_state:
    st.session_state.widget_context = None

sidebar.render()

# Proactive alerts: a floating right-side panel evaluated directly against the
# active client's database (not via the agent). Renders nothing if no breaches.
render_alerts(evaluate_all_alerts())

st.markdown('<div class="sema-title">SEMA</div>', unsafe_allow_html=True)
st.markdown('<div class="sema-subtitle">Ask your business anything.</div>', unsafe_allow_html=True)

chat.render_messages(st.session_state.messages)

# Friendly empty state on first open.
if not st.session_state.messages:
    suggested = client_registry.get_active_client().get("suggested_questions", [])
    chips = "".join(
        f'<span style="display:inline-block; background:{TOKENS["lav_tint"]}; '
        f'color:{TOKENS["primary_dark"]}; border:1px solid {TOKENS["border_soft"]}; '
        f'border-radius:999px; padding:0.4rem 0.85rem; font-size:0.82rem; '
        f'margin:0.25rem;">{q}</span>'
        for q in suggested[:4]
    )
    st.markdown(
        f"""
        <div class="sema-empty">
            <div style="display:flex; justify-content:center;">{connected_flow_logo(56)}</div>
            <div class="sema-empty-title">Ask your business anything.</div>
            <div class="sema-empty-sub">Pick a question from the sidebar, or try one of these:</div>
            <div style="margin-top:0.6rem;">{chips}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Focused widget context, shown as a chip above the input with a clear (×).
if st.session_state.widget_context:
    ctx = st.session_state.widget_context
    col_ctx, col_clear = st.columns([10, 1])
    with col_ctx:
        st.markdown(
            f'<div class="sema-ctx-chip">💬 שואל על: {ctx["label"]}</div>',
            unsafe_allow_html=True,
        )
    with col_clear:
        if st.button("×", key="clear_ctx", help="חזור לשאלה כללית"):
            st.session_state.widget_context = None
            st.rerun()

user_input = st.chat_input("Ask about revenue, customers, campaigns...")

question = None
if st.session_state.pending_question:
    question = st.session_state.pending_question
    st.session_state.pending_question = None
elif user_input:
    question = user_input

if question:
    # If a widget context is active, prefix it onto the question sent to the
    # agent (so it focuses on that element), then clear it -- the next general
    # question starts clean. The user still sees their original text in the UI.
    agent_question = question
    if st.session_state.widget_context:
        agent_question = f'{st.session_state.widget_context["agent_prefix"]}\n\n{question}'
        st.session_state.widget_context = None

    with st.spinner("SEMA is analyzing..."):
        # Pass the prior conversation so the agent can handle follow-ups.
        response = get_response(agent_question, history=st.session_state.agent_history)

    # Decide direction once, from the question's language: a Hebrew question
    # makes both the question bubble and the whole answer render right-to-left.
    rtl = chat.is_rtl(question)
    st.session_state.messages.append({"role": "user", "content": question, "rtl": rtl})
    st.session_state.messages.append({"role": "assistant", "content": response, "rtl": rtl})
    st.session_state.history.append(question)

    # Grow the agent's conversation memory: the (context-prefixed) question, and
    # the answer's narrative text only (Claude reads prose, not UI KPI/chart JSON).
    st.session_state.agent_history.append({"role": "user", "content": agent_question})
    st.session_state.agent_history.append(
        {"role": "assistant", "content": response.get("insight_text", "")}
    )

    st.rerun()
