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

from components import chat, sidebar, styles
from components.theme import TOKENS, connected_flow_logo
from query_router import SUGGESTED_QUESTIONS
from wiring import get_response

_ICON_PATH = Path(__file__).parent / "assets" / "sema_icon.svg"

st.set_page_config(
    page_title="SEMA",
    page_icon=str(_ICON_PATH) if _ICON_PATH.exists() else "✦",
    layout="wide",
)
styles.inject()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "history" not in st.session_state:
    st.session_state.history = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None

sidebar.render()

st.markdown('<div class="sema-title">SEMA</div>', unsafe_allow_html=True)
st.markdown('<div class="sema-subtitle">Ask your business anything.</div>', unsafe_allow_html=True)

chat.render_messages(st.session_state.messages)

# Friendly empty state on first open.
if not st.session_state.messages:
    chips = "".join(
        f'<span style="display:inline-block; background:{TOKENS["lav_tint"]}; '
        f'color:{TOKENS["primary_dark"]}; border:1px solid {TOKENS["border_soft"]}; '
        f'border-radius:999px; padding:0.4rem 0.85rem; font-size:0.82rem; '
        f'margin:0.25rem;">{q}</span>'
        for q in SUGGESTED_QUESTIONS[:4]
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

user_input = st.chat_input("Ask about revenue, customers, campaigns...")

question = None
if st.session_state.pending_question:
    question = st.session_state.pending_question
    st.session_state.pending_question = None
elif user_input:
    question = user_input

if question:
    with st.spinner("SEMA is analyzing..."):
        response = get_response(question)

    # Decide direction once, from the question's language: a Hebrew question
    # makes both the question bubble and the whole answer render right-to-left.
    rtl = chat.is_rtl(question)
    st.session_state.messages.append({"role": "user", "content": question, "rtl": rtl})
    st.session_state.messages.append({"role": "assistant", "content": response, "rtl": rtl})
    st.session_state.history.append(question)

    st.rerun()
