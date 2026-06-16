"""
SEMA: design tokens.

This is the single source of truth for every color, radius, and brand
palette value in the UI -- the visual equivalent of the semantic layer we
use for business concepts. No other file should hardcode a hex value;
everything reads from here, so a rebrand is a one-file change.

Personality: calm, intelligent, premium, pastel. Light theme.
"""

from __future__ import annotations

# --- Core palette -----------------------------------------------------------
TOKENS: dict[str, str] = {
    # Surfaces
    "bg": "#F8FAFC",          # app canvas
    "surface": "#FFFFFF",     # cards
    "surface_alt": "#F1F5F9", # subtle inset panels
    # Brand
    "primary": "#7C8CFF",     # lavender -- intelligence / AI
    "primary_dark": "#5B5F9F",
    "mint": "#7EE6C3",        # growth / success
    "coral": "#FFB4A2",       # attention / risk
    "yellow": "#FFE59A",      # insights / recommendations
    "sky": "#9ED8FF",         # trends / analytics
    # Text
    "text": "#1E293B",
    "muted": "#64748B",
    "faint": "#94A3B8",
    # Lines
    "border": "#E8EDF3",
    "border_soft": "#EEF2F7",
    # Section labels (darker than the faint hint grey)
    "label": "#475569",
    # Text colors that read on the pastel tints
    "mint_text": "#1B7A5E",
    "yellow_text": "#946C12",
    "sky_text": "#5A7894",
    "coral_text": "#9A6A58",
    # Semantic deltas
    "success": "#16A34A",
    "danger": "#C2410C",
    # Soft pastel tints (for chips, KPI cards, action cards)
    "lav_tint": "#EEF0FF",
    "mint_tint": "#EAFBF4",
    "yellow_tint": "#FFF6E0",
    "sky_tint": "#EAF5FF",
    "coral_tint": "#FBEEEA",
    # Shape
    "radius": "14px",
    "radius_sm": "10px",
    "radius_lg": "18px",
}

# Ordered color sequence for charts (lavender, mint, sky, coral, yellow).
CHART_COLORWAY: list[str] = [
    TOKENS["primary"],
    TOKENS["mint"],
    TOKENS["sky"],
    TOKENS["coral"],
    "#F2C94C",  # slightly deeper yellow so it reads on white
]

# (background tint, label color) pairs cycled across KPI cards in a response.
KPI_TINTS: list[tuple[str, str]] = [
    (TOKENS["coral_tint"], "#9A6A58"),
    (TOKENS["sky_tint"], "#5A7894"),
    (TOKENS["lav_tint"], TOKENS["primary_dark"]),
]


def connected_flow_logo(size: int = 34) -> str:
    """Inline SVG for the 'connected flow' SEMA mark.

    Four nodes (question -> semantics -> insights -> actions) linked along
    an S-shaped path, in the brand pastels. Returned as a raw SVG string so
    it can be dropped straight into st.markdown(..., unsafe_allow_html=True).
    """
    # Returned as a single line with no leading whitespace: Streamlit's
    # markdown treats 4-space-indented lines as a code block, which would
    # break the surrounding HTML when this is embedded via st.markdown.
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 64 64" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="SEMA logo">'
        f'<path d="M44,16 C26,18 20,30 32,34 C44,38 42,50 20,52" fill="none" '
        f'stroke="#CBD5E1" stroke-width="3" stroke-linecap="round"/>'
        f'<circle cx="44" cy="16" r="5.5" fill="{TOKENS["primary"]}"/>'
        f'<circle cx="22" cy="28" r="5.5" fill="{TOKENS["sky"]}"/>'
        f'<circle cx="42" cy="40" r="5.5" fill="{TOKENS["mint"]}"/>'
        f'<circle cx="20" cy="52" r="5.5" fill="{TOKENS["coral"]}"/>'
        f"</svg>"
    )
