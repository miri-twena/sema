"""
SEMA: table rendering.

Thin wrapper around st.dataframe so every supporting table in the app gets
a consistent title and styling.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st


def render(df: pd.DataFrame, title: str | None = None) -> None:
    if df is None or df.empty:
        return

    if title:
        st.markdown(f"**{title}**")

    st.dataframe(df, use_container_width=True, hide_index=True)
