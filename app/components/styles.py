"""
SEMA: global CSS, generated from design tokens.

We use string.Template ($name placeholders) instead of an f-string because
CSS is full of { } braces that would collide with f-string syntax. Every
color/radius comes from theme.TOKENS -- this file only arranges them.
"""

from __future__ import annotations

from string import Template

import streamlit as st

from components.theme import TOKENS

_CSS = Template(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background-color: $bg;
}

/* Tighten the default top padding so the header sits high */
.block-container {
    padding-top: 2.2rem;
    padding-bottom: 4rem;
    max-width: 1100px;
}

/* Hide Streamlit's default chrome for a cleaner product feel */
#MainMenu, footer, header[data-testid="stHeader"] {
    visibility: hidden;
}

h1, h2, h3 {
    color: $text;
    font-weight: 600;
    letter-spacing: -0.01em;
}

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
    background-color: $surface;
    border-right: 1px solid $border;
}
[data-testid="stSidebar"] .block-container {
    padding-top: 1.5rem;
}

.sema-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 2px;
}
.sema-brand-name {
    font-size: 1.35rem;
    font-weight: 600;
    color: $text;
}
.sema-brand-sub {
    font-size: 0.8rem;
    color: $muted;
    margin-bottom: 1.1rem;
}
.sema-section-label {
    font-size: 0.72rem;
    color: $label;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 1.1rem 0 0.5rem 0;
}
.sema-source {
    background: $bg;
    border: 1px solid $border_soft;
    border-radius: $radius_sm;
    padding: 0.6rem 0.75rem;
}
.sema-source-name {
    font-size: 0.82rem;
    color: $text;
}
.sema-status {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.78rem;
    margin-top: 0.35rem;
}
.sema-status .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.sema-status.connected { color: $success; }
.sema-status.connected .dot { background: $success; }
.sema-status.disconnected { color: $danger; }
.sema-status.disconnected .dot { background: $danger; }
.sema-history-item {
    font-size: 0.8rem;
    color: $muted;
    padding: 0.3rem 0;
    border-bottom: 1px solid $border_soft;
}

/* ---- Suggested-question chips (Streamlit buttons) ---- */
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    text-align: left;
    background: $lav_tint;
    color: $primary_dark;
    border: 1px solid $border_soft;
    border-radius: $radius_sm;
    padding: 0.55rem 0.8rem;
    font-size: 0.82rem;
    font-weight: 500;
    line-height: 1.35;
    transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.12s ease;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: $surface;
    border-color: $primary;
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(124, 140, 255, 0.18);
}

/* Per-chip pastel backgrounds. Streamlit (>=1.39) adds an st-key-<key>
   class to each keyed widget's container, so we color each chip by its
   key (sq0..sq4 set in sidebar.py). Same specificity as the rule above
   but declared later, so these win for the background color. */
[data-testid="stSidebar"] .st-key-sq0 button { background: $lav_tint; color: $primary_dark; }
[data-testid="stSidebar"] .st-key-sq1 button { background: $mint_tint; color: $mint_text; }
[data-testid="stSidebar"] .st-key-sq2 button { background: $yellow_tint; color: $yellow_text; }
[data-testid="stSidebar"] .st-key-sq3 button { background: $sky_tint; color: $sky_text; }
[data-testid="stSidebar"] .st-key-sq4 button { background: $coral_tint; color: $coral_text; }

/* ---- Headline ---- */
.sema-title {
    font-size: 2rem;
    font-weight: 600;
    color: $text;
    letter-spacing: -0.02em;
    margin-bottom: 0.1rem;
}
.sema-subtitle {
    font-size: 1rem;
    color: $muted;
    margin-bottom: 1.4rem;
}

/* ---- Chat bubbles ---- */
.sema-row { display: flex; width: 100%; margin: 0.35rem 0; }
.sema-row.user { justify-content: flex-end; }
.sema-bubble.user {
    background: $primary;
    color: #FFFFFF;
    padding: 0.7rem 1rem;
    border-radius: 16px 16px 4px 16px;
    max-width: 72%;
    font-size: 0.92rem;
    line-height: 1.5;
    box-shadow: 0 4px 14px rgba(124, 140, 255, 0.25);
}

/* The assistant response is a bordered st.container -- style it as a card */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: $surface;
    border: 1px solid $border !important;
    border-radius: $radius_lg !important;
    padding: 0.4rem 0.5rem;
    box-shadow: 0 6px 24px rgba(30, 41, 59, 0.05);
}
.sema-assistant-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 0.3rem;
}
.sema-assistant-head .name {
    font-size: 0.82rem;
    font-weight: 600;
    color: $primary_dark;
}
.sema-insight { color: $text; font-size: 0.95rem; line-height: 1.7; }

/* ---- KPI cards ---- */
.sema-kpi {
    border-radius: $radius;
    padding: 0.85rem 1rem;
}
.sema-kpi-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.3rem;
}
.sema-kpi-value {
    /* clamp() scales the number down on narrow cards so a long value can
       never spill outside its tile (4 KPIs in a row get quite narrow). */
    font-size: clamp(1.05rem, 2.1vw, 1.55rem);
    font-weight: 600;
    color: $text;
    line-height: 1.1;
    white-space: nowrap;
}
.sema-kpi-delta { font-size: 0.82rem; margin-top: 0.25rem; font-weight: 500; }
.sema-kpi-delta.up { color: $success; }
.sema-kpi-delta.down { color: $danger; }

/* ---- Recommended actions ---- */
.sema-actions-title {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: $faint;
    margin: 0.6rem 0 0.5rem 0;
}
.sema-action {
    background: $yellow_tint;
    border: 1px solid #F4E3B0;
    border-radius: $radius;
    padding: 0.65rem 0.85rem;
    margin-bottom: 0.5rem;
    font-size: 0.9rem;
    color: #8A6410;
    display: flex;
    gap: 0.5rem;
    align-items: flex-start;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.sema-action:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(244, 197, 66, 0.22);
}
.sema-action .arrow { color: #C99A1E; font-weight: 600; }

/* ---- Empty state ---- */
.sema-empty {
    text-align: center;
    padding: 1.5rem 0 0.5rem 0;
}
.sema-empty-title { font-size: 1.1rem; color: $text; font-weight: 600; margin-top: 0.8rem; }
.sema-empty-sub { font-size: 0.9rem; color: $muted; margin-bottom: 0.5rem; }

/* ---- Tables ---- */
[data-testid="stDataFrame"] { border-radius: $radius; }

/* ---- RTL: direction is decided per turn, from the QUESTION's language ----
   main.py tags each message with an `rtl` flag (true when the question
   contains Hebrew). For an RTL turn, chat.py sets dir="rtl" on the user
   bubble and drops a hidden .sema-rtl-flag marker inside the assistant card.
   The :has() rule below then flips the WHOLE response card to right-to-left
   -- every paragraph (even one that starts with an English metric name),
   list bullets, and the order of the KPI cards -- so a Hebrew question
   always yields a fully right-to-left answer. English turns keep the
   default left-to-right. */
.sema-rtl-flag { display: none; }

[data-testid="stVerticalBlockBorderWrapper"]:has(.sema-rtl-flag) {
    direction: rtl;
    text-align: right;
}
</style>
"""
).substitute(TOKENS)


def inject() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
