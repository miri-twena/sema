"""
SEMA: Client Management (admin page).

Streamlit auto-discovers files in app/pages/, so this shows up as a second
page. It lists every configured client with its live connection status and
semantic-layer size, and lets you switch the active client for the whole app.

Switching just updates st.session_state.active_client_id; because db.py caches
connections per client_id and semantic.py resolves the folder at call time,
the rest of the app picks up the new client on the next run -- no restart.
"""

from __future__ import annotations

import streamlit as st

import client_registry
from agent.semantic import load_semantic_layer
from components import styles
from components.theme import connected_flow_logo
from db import check_connection

st.set_page_config(page_title="SEMA — Clients", page_icon="⚙", layout="wide")
styles.inject()

# Guard: a user could land here first, before main.py set the default.
if "active_client_id" not in st.session_state:
    st.session_state.active_client_id = client_registry.DEFAULT_CLIENT_ID

st.markdown(
    f'<div class="sema-assistant-head">{connected_flow_logo(28)}'
    f'<span class="name" style="font-size:1rem;">Client Management</span></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sema-subtitle">Each client has its own database and semantic '
    'layer. Switch the active client for the whole app.</div>',
    unsafe_allow_html=True,
)
st.page_link("main.py", label="← Back to chat", use_container_width=False)
st.write("")

clients = client_registry.load_clients()
active_id = st.session_state.active_client_id
cols = st.columns(len(clients))

for col, client in zip(cols, clients):
    with col:
        with st.container(border=True):
            is_active = client["id"] == active_id

            connected = check_connection(client["id"])
            status_cls = "connected" if connected else "disconnected"
            status_text = "Connected" if connected else "Disconnected"

            try:
                n_metrics = len(load_semantic_layer(client["id"]))
            except Exception:
                n_metrics = 0

            st.markdown(
                f"""
                <div class="sema-source-name" style="font-size:1.05rem; font-weight:600;">
                    {client["label"]}
                </div>
                <div class="sema-status {status_cls}" style="margin:0.4rem 0;">
                    <span class="dot"></span>{status_text}
                </div>
                <div class="sema-history-item" style="border:none;">
                    Database: <code>{client["id"]}</code><br>
                    Semantic metrics: <b>{n_metrics}</b>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if is_active:
                st.success("● Active client", icon="✅")
            else:
                if st.button(
                    f"Switch to {client['label']}",
                    key=f"switch_{client['id']}",
                    use_container_width=True,
                ):
                    st.session_state.active_client_id = client["id"]
                    # A fresh client means a fresh conversation context.
                    st.session_state.messages = []
                    st.session_state.history = []
                    st.session_state.pending_question = None
                    try:
                        st.switch_page("main.py")
                    except Exception:
                        st.rerun()
