"""
SEMA: table rendering.

Thin wrapper around st.dataframe so every supporting table in the app gets
a consistent title and styling.

Column headers come straight from the SQL aliases the agent writes, so they
are English snake_case (e.g. "avg_annual_premium"). When the turn is in
Hebrew (rtl=True) we relabel known columns to natural Hebrew via COLUMN_LABELS
below, so a Hebrew question yields a fully Hebrew table. Unknown columns fall
back to a tidied version of the raw name (underscores -> spaces). English
turns keep the original headers.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

# Raw SQL column name (lowercased) -> Hebrew header. Covers the insurance
# semantic layer's common aliases plus a few ecommerce ones. Add to this as
# new metrics/dimensions get queried.
COLUMN_LABELS: dict[str, str] = {
    # --- dimensions ---
    "acquisition_channel": "ערוץ רכישה",
    "channel": "ערוץ",
    "agent_channel": "ערוץ סוכן",
    "coverage_type": "סוג כיסוי",
    "product_name": "שם מוצר",
    "business_type": "סוג עסקה",
    "region": "אזור",
    "incident_region": "אזור אירוע",
    "registration_region": "אזור רישום",
    "claim_type": "סוג תביעה",
    "vehicle_category": "קטגוריית רכב",
    "usage_type": "סוג שימוש",
    "age_band": "קבוצת גיל",
    "age_group": "קבוצת גיל",
    "gender": "מין",
    "marital_status": "מצב משפחתי",
    "credit_band": "דירוג אשראי",
    "status": "סטטוס",
    "month": "חודש",
    "year": "שנה",
    "quarter": "רבעון",
    # --- premium measures ---
    "annual_premium": "פרמיה שנתית",
    "avg_annual_premium": "פרמיה שנתית ממוצעת",
    "average_premium": "פרמיה ממוצעת",
    "avg_premium": "פרמיה ממוצעת",
    "written_premium": "פרמיה נכתבת",
    "total_written_premium": "סך פרמיה נכתבת",
    "earned_premium": "פרמיה מורווחת",
    "total_earned_premium": "סך פרמיה מורווחת",
    "new_business_premium": "פרמיה מעסקים חדשים",
    # --- claims measures ---
    "incurred_claims": "תביעות ששולמו",
    "total_incurred_claims": "סך תביעות ששולמו",
    "paid_amount": "סכום ששולם",
    "total_paid_amount": "סך סכום ששולם",
    "claim_amount": "סכום התביעה",
    "claims": "מספר תביעות",
    "claim_count": "מספר תביעות",
    "total_claims": "סך תביעות",
    "claims_per_100_policies": "תביעות ל-100 פוליסות",
    "claims_frequency": "תדירות תביעות",
    "avg_claim_severity": "חומרת תביעה ממוצעת",
    "claim_severity": "חומרת תביעה",
    "loss_ratio": "יחס נזק",
    "loss_ratio_pct": "יחס נזק (%)",
    # --- policy / customer counts ---
    "policies": "מספר פוליסות",
    "total_policies": "מספר פוליסות",
    "policy_count": "מספר פוליסות",
    "policies_in_force": "פוליסות בתוקף",
    "renewal_rate": "שיעור חידוש",
    "renewal_rate_pct": "שיעור חידוש (%)",
    "retention_rate": "שיעור שימור",
    "policyholders": "בעלי פוליסות",
    "policyholder_count": "מספר בעלי פוליסות",
    # --- generic aggregates / ecommerce overlap ---
    "count": "כמות",
    "total": "סך הכול",
    "revenue": "הכנסה",
    "total_revenue": "סך הכנסה",
    "orders": "הזמנות",
    "order_count": "מספר הזמנות",
    "category": "קטגוריה",
    "segment": "סגמנט",
    "aov": "ערך הזמנה ממוצע",
}


def _pretty_fallback(name: str) -> str:
    """Tidy an unknown column name: underscores -> spaces, words capitalised."""
    return name.replace("_", " ").strip().title()


def _to_hebrew_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with headers relabelled to Hebrew where known."""
    rename = {
        col: COLUMN_LABELS.get(str(col).lower(), _pretty_fallback(str(col)))
        for col in df.columns
    }
    return df.rename(columns=rename)


def render(df: pd.DataFrame, title: str | None = None, rtl: bool = False) -> None:
    if df is None or df.empty:
        return

    if title:
        st.markdown(f"**{title}**")

    if rtl:
        df = _to_hebrew_headers(df)

    st.dataframe(df, use_container_width=True, hide_index=True)
