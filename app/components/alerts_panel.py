"""
SEMA: floating right-side alerts panel.

A fixed-position notification bell + dropdown injected via HTML/CSS. Streamlit
has no native right-hand sidebar, so we render our own outside the normal flow.

Two Streamlit sanitizer limits shape the implementation:
  - st.markdown strips <script> (and inline event handlers), so an injected JS
    toggle can't run.
  - st.markdown also strips <details>/<summary>, so the native disclosure
    widget can't be used either.
What survives is <div>/<span> with `class`/`style` (the same primitives the KPI
cards use). So the dropdown is **pure CSS**: hovering the bell reveals the
panel via a `:hover` rule -- no JS, no <details>. The CSS is built from the
SEMA design tokens (theme.py) so it matches the app; severity colors are the
standard red/amber alert palette.
"""

from __future__ import annotations

import html
from string import Template

import streamlit as st

from components.theme import TOKENS

# Severity -> (background, accent) for the alert cards and the badge.
_SEVERITY_COLORS = {
    "critical": {"bg": "#fee2e2", "accent": "#dc2626"},
    "warning": {"bg": "#fef9c3", "accent": "#ca8a04"},
}

_CSS = Template(
    """
<style>
/* --- fixed wrapper (bell lives here; panel is fixed too) --- */
.sema-alerts-wrap { position: fixed; top: 1rem; right: 1rem; z-index: 9999; }

/* --- bell trigger --- */
.sema-alerts-btn {
    width: 44px; height: 44px;
    border-radius: 50%;
    background: $surface;
    border: 1px solid $border;
    box-shadow: 0 4px 14px rgba(30, 41, 59, 0.12);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.2rem;
    position: relative;
    cursor: pointer;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.sema-alerts-wrap:hover .sema-alerts-btn {
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(30, 41, 59, 0.18);
}
.sema-alerts-badge {
    position: absolute; top: -4px; right: -4px;
    min-width: 18px; height: 18px; padding: 0 4px;
    border-radius: 9px;
    font-size: 0.7rem; font-weight: 700; color: #ffffff;
    display: flex; align-items: center; justify-content: center;
}
.sema-badge-critical { background: #dc2626; }
.sema-badge-warning { background: #ca8a04; }

/* --- dropdown panel: hidden until the bell (or the panel) is hovered --- */
.sema-alerts-panel {
    position: fixed; top: 3.4rem; right: 1rem;   /* slight overlap with bell = no dead zone */
    width: 320px; max-height: 70vh; overflow-y: auto;
    background: $surface;
    border: 1px solid $border;
    border-radius: $radius;
    box-shadow: 0 8px 30px rgba(30, 41, 59, 0.18);
    padding: 0.65rem;
    z-index: 9998;
    opacity: 0; visibility: hidden; transform: translateY(-6px);
    transition: opacity 0.15s ease, transform 0.15s ease, visibility 0.15s;
}
.sema-alerts-wrap:hover .sema-alerts-panel,
.sema-alerts-panel:hover {
    opacity: 1; visibility: visible; transform: translateY(0);
}

.sema-alerts-head {
    font-size: 0.72rem; font-weight: 600; color: $primary_dark;
    text-transform: uppercase; letter-spacing: 0.05em;
    margin: 0.15rem 0 0.55rem 0.2rem;
}
.sema-alert {
    border-radius: $radius_sm;
    padding: 0.55rem 0.7rem;
    margin-bottom: 0.45rem;
    border-left: 3px solid;
}
.sema-alert:last-child { margin-bottom: 0.1rem; }
.sema-alert-title { font-weight: 600; font-size: 0.85rem; }
.sema-alert-msg {
    font-size: 0.82rem; color: $text; margin-top: 0.15rem; line-height: 1.4;
    unicode-bidi: plaintext; text-align: start;  /* Hebrew messages read RTL */
}
.sema-alert-metric { font-size: 0.7rem; color: $muted; margin-top: 0.3rem; }
</style>
"""
).substitute(TOKENS)


def _alert_html(alert: dict) -> str:
    severity = alert.get("severity", "warning")
    colors = _SEVERITY_COLORS.get(severity, _SEVERITY_COLORS["warning"])
    return (
        f'<div class="sema-alert" style="background:{colors["bg"]}; '
        f'border-left-color:{colors["accent"]};">'
        f'<div class="sema-alert-title" style="color:{colors["accent"]};">'
        f'{html.escape(str(alert.get("alert_label", "")))}</div>'
        f'<div class="sema-alert-msg">{html.escape(str(alert.get("message", "")))}</div>'
        f'<div class="sema-alert-metric">{html.escape(str(alert.get("metric_label", "")))}</div>'
        f"</div>"
    )


def render(alerts: list[dict]) -> None:
    """Inject the floating alerts panel. Renders nothing when there are no alerts."""
    if not alerts:
        return

    count = len(alerts)
    worst = "critical" if any(a.get("severity") == "critical" for a in alerts) else "warning"
    items = "".join(_alert_html(a) for a in alerts)

    # Built as a single, NON-indented line: Streamlit's markdown treats any
    # 4-space-indented block as a code block and would escape the HTML to text.
    panel = (
        '<div class="sema-alerts-wrap">'
        f'<div class="sema-alerts-btn" title="{count} active alert(s)">'
        f'🔔<span class="sema-alerts-badge sema-badge-{worst}">{count}</span>'
        "</div>"
        '<div class="sema-alerts-panel">'
        f'<div class="sema-alerts-head">Alerts · {count}</div>'
        f"{items}"
        "</div>"
        "</div>"
    )

    st.markdown(_CSS + panel, unsafe_allow_html=True)
