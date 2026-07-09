"""
SEMA: insight builder.

This module is the "brain" between raw query results and what gets shown
on screen. For each supported intent, it:
  1. Pulls one or more dataframes from queries.py (real data from Postgres).
  2. Computes the actual numbers we need (deltas, shares, rankings) --
     nothing here is hardcoded, it's all derived from the live dataframes.
  3. Packages everything into a single response dict that main.py /
     components/chat.py know how to render.

Response dict shape (always all keys present):
{
    "insight_text": str,                 # narrative summary
    "kpis": list[dict],                  # KPI tiles, see components/kpi_cards.py
    "charts": list[dict],                # chart specs, see components/charts.py
    "table": pd.DataFrame | None,        # optional supporting table
    "table_title": str | None,
    "recommended_actions": list[str],
}
"""

from __future__ import annotations

import pandas as pd

from sema_core import queries
from sema_core.query_router import SUGGESTED_QUESTIONS


def _month_label(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).strftime("%b %Y")


def _pct_change(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / old * 100.0


def _empty_response() -> dict:
    return {
        "insight_text": "",
        "kpis": [],
        "charts": [],
        "table": None,
        "table_title": None,
        "recommended_actions": [],
    }


def _march_dip() -> dict:
    monthly = queries.get_revenue_by_month()
    march = monthly[monthly["month"] == pd.Timestamp("2026-03-01")].iloc[0]
    feb = monthly[monthly["month"] == pd.Timestamp("2026-02-01")].iloc[0]
    april = monthly[monthly["month"] == pd.Timestamp("2026-04-01")].iloc[0]

    revenue_vs_feb_pct = _pct_change(march["revenue"], feb["revenue"])
    revenue_vs_april_pct = _pct_change(march["revenue"], april["revenue"])

    # Category breakdown: compare March to April (a "typical" month).
    cat_df = queries.get_revenue_by_category_by_month()
    mar_cat = cat_df[cat_df["month"] == pd.Timestamp("2026-03-01")][["category", "revenue"]]
    apr_cat = cat_df[cat_df["month"] == pd.Timestamp("2026-04-01")][["category", "revenue"]]
    cat_compare = mar_cat.merge(apr_cat, on="category", suffixes=("_march", "_april"))
    cat_compare["pct_change"] = cat_compare.apply(
        lambda r: _pct_change(r["revenue_march"], r["revenue_april"]), axis=1
    )
    cat_compare = cat_compare.sort_values("pct_change")
    worst_category = cat_compare.iloc[0]

    # Traffic source breakdown: same March vs April comparison.
    traffic_df = queries.get_traffic_source_by_month()
    mar_traffic = traffic_df[traffic_df["month"] == pd.Timestamp("2026-03-01")][
        ["traffic_source", "order_count", "revenue"]
    ]
    apr_traffic = traffic_df[traffic_df["month"] == pd.Timestamp("2026-04-01")][
        ["traffic_source", "order_count", "revenue"]
    ]
    traffic_compare = mar_traffic.merge(
        apr_traffic, on="traffic_source", suffixes=("_march", "_april")
    )
    traffic_compare["pct_change"] = traffic_compare.apply(
        lambda r: _pct_change(r["order_count_march"], r["order_count_april"]), axis=1
    )
    traffic_compare = traffic_compare.sort_values("pct_change")
    worst_traffic = traffic_compare.iloc[0]

    # Segment breakdown: which customer segment lost the most orders?
    seg_df = queries.get_segment_orders_by_month()
    mar_seg = seg_df[seg_df["month"] == pd.Timestamp("2026-03-01")][
        ["segment", "order_count", "revenue"]
    ]
    apr_seg = seg_df[seg_df["month"] == pd.Timestamp("2026-04-01")][
        ["segment", "order_count", "revenue"]
    ]
    seg_compare = mar_seg.merge(apr_seg, on="segment", suffixes=("_march", "_april"))
    seg_compare["pct_change"] = seg_compare.apply(
        lambda r: _pct_change(r["order_count_march"], r["order_count_april"]), axis=1
    )
    seg_compare = seg_compare.sort_values("pct_change")
    worst_segment = seg_compare.iloc[0]

    insight_text = (
        f"**March 2026 revenue was {march['revenue']:,.0f}**, "
        f"down {abs(revenue_vs_feb_pct):.1f}% from February "
        f"({feb['revenue']:,.0f}) and "
        f"{abs(revenue_vs_april_pct):.1f}% below April "
        f"({april['revenue']:,.0f}).\n\n"
        f"Three factors stand out when comparing March to April:\n\n"
        f"- **{worst_category['category']}** revenue fell "
        f"{abs(worst_category['pct_change']):.1f}% "
        f"({worst_category['revenue_march']:,.0f} vs "
        f"{worst_category['revenue_april']:,.0f} in April) -- the "
        f"steepest category decline.\n"
        f"- **{worst_traffic['traffic_source']}**-attributed orders dropped "
        f"{abs(worst_traffic['pct_change']):.1f}% "
        f"({worst_traffic['order_count_march']:.0f} vs "
        f"{worst_traffic['order_count_april']:.0f} in April), "
        f"suggesting weaker performance on that channel.\n"
        f"- **{worst_segment['segment']}** customers placed "
        f"{abs(worst_segment['pct_change']):.1f}% fewer orders "
        f"({worst_segment['order_count_march']:.0f} vs "
        f"{worst_segment['order_count_april']:.0f} in April)."
    )

    resp = _empty_response()
    resp["insight_text"] = insight_text
    resp["kpis"] = [
        {
            "label": "March 2026 Revenue",
            "value": march["revenue"],
            "delta": revenue_vs_feb_pct,
            "delta_label": "vs Feb 2026",
            "format": "currency",
        },
        {
            "label": f"{worst_category['category']} Revenue",
            "value": worst_category["revenue_march"],
            "delta": worst_category["pct_change"],
            "delta_label": "vs Apr 2026",
            "format": "currency",
        },
        {
            "label": f"{worst_traffic['traffic_source']} Orders",
            "value": worst_traffic["order_count_march"],
            "delta": worst_traffic["pct_change"],
            "delta_label": "vs Apr 2026",
            "format": "number",
        },
    ]
    resp["charts"] = [
        {
            "kind": "line",
            "df": monthly,
            "x": "month",
            "y": "revenue",
            "title": "Monthly Revenue (highlighting March 2026)",
            "highlight_x": pd.Timestamp("2026-03-01"),
        },
        {
            "kind": "grouped_bar",
            "df": cat_compare.melt(
                id_vars="category",
                value_vars=["revenue_march", "revenue_april"],
                var_name="month",
                value_name="revenue",
            ).replace({"revenue_march": "March 2026", "revenue_april": "April 2026"}),
            "x": "category",
            "y": "revenue",
            "color": "month",
            "title": "Revenue by Category: March vs April 2026",
        },
    ]
    # Format for display: currency with thousands separators, % to 1 dp.
    cat_table = cat_compare.copy()
    cat_table["revenue_march"] = cat_table["revenue_march"].map(lambda v: f"${v:,.0f}")
    cat_table["revenue_april"] = cat_table["revenue_april"].map(lambda v: f"${v:,.0f}")
    cat_table["pct_change"] = cat_table["pct_change"].map(lambda v: f"{v:+.1f}%")
    resp["table"] = cat_table.rename(
        columns={
            "category": "Category",
            "revenue_march": "March Revenue",
            "revenue_april": "April Revenue",
            "pct_change": "% Change",
        }
    )
    resp["table_title"] = "Category Revenue: March vs April 2026"
    resp["recommended_actions"] = [
        f"Investigate the {worst_category['category']} catalog for stockouts, "
        f"pricing changes, or promo gaps in March 2026.",
        f"Review {worst_traffic['traffic_source']} campaign creative, budget "
        f"pacing, and bidding for March 2026.",
        f"Run a win-back or loyalty offer targeted at {worst_segment['segment']} "
        f"customers to recover lost order volume.",
    ]
    return resp


def _top_customers() -> dict:
    top10 = queries.get_top_customers()
    pareto = queries.get_top5pct_revenue_share().iloc[0]
    top1 = top10.iloc[0]

    insight_text = (
        f"Your top 10 customers have generated "
        f"**{top10['lifetime_revenue'].sum():,.0f}** in lifetime revenue. "
        f"The single most valuable customer, **{top1['customer_name']}** "
        f"(segment: {top1['segment']}, acquired via {top1['acquisition_channel']}), "
        f"has contributed **{top1['lifetime_revenue']:,.0f}** across "
        f"{top1['order_count']} orders.\n\n"
        f"More broadly, the **top 5% of customers** "
        f"({int(pareto['top5pct_customers'])} of {int(pareto['total_customers'])}) "
        f"account for **{pareto['top5pct_share_pct']:.1f}%** of total revenue -- "
        f"a clear sign of revenue concentration worth protecting and growing."
    )

    resp = _empty_response()
    resp["insight_text"] = insight_text
    resp["kpis"] = [
        {
            "label": "Top Customer Lifetime Revenue",
            "value": top1["lifetime_revenue"],
            "format": "currency",
        },
        {
            "label": "Revenue from Top 5% of Customers",
            "value": pareto["top5pct_share_pct"],
            "format": "percent",
        },
        {
            "label": "Top 10 Combined Revenue",
            "value": top10["lifetime_revenue"].sum(),
            "format": "currency",
        },
    ]
    resp["charts"] = [
        {
            "kind": "bar",
            "df": top10,
            "x": "customer_name",
            "y": "lifetime_revenue",
            "title": "Top 10 Customers by Lifetime Revenue",
        }
    ]
    resp["table"] = top10
    resp["table_title"] = "Top 10 Customers"
    resp["recommended_actions"] = [
        "Set up a VIP loyalty tier with perks for your top revenue customers.",
        "Assign top-5% customers to a dedicated account manager or concierge "
        "support channel.",
        "Use the top-customer profile (segment, acquisition channel) to guide "
        "lookalike audience targeting for acquisition campaigns.",
    ]
    return resp


def _revenue_trend() -> dict:
    monthly = queries.get_revenue_by_month()
    latest = monthly.iloc[-1]
    prior = monthly.iloc[-2]
    delta_pct = _pct_change(latest["revenue"], prior["revenue"])

    insight_text = (
        f"Total revenue across the dataset is "
        f"**{monthly['revenue'].sum():,.0f}** over {len(monthly)} months. "
        f"The most recent month, **{_month_label(latest['month'])}**, brought in "
        f"**{latest['revenue']:,.0f}**, "
        f"{'up' if delta_pct >= 0 else 'down'} {abs(delta_pct):.1f}% from "
        f"{_month_label(prior['month'])} ({prior['revenue']:,.0f})."
    )

    resp = _empty_response()
    resp["insight_text"] = insight_text
    resp["kpis"] = [
        {
            "label": f"{_month_label(latest['month'])} Revenue",
            "value": latest["revenue"],
            "delta": delta_pct,
            "delta_label": "vs prior month",
            "format": "currency",
        },
        {
            "label": "Total Revenue (All Months)",
            "value": monthly["revenue"].sum(),
            "format": "currency",
        },
        {
            "label": "Months of Data",
            "value": len(monthly),
            "format": "number",
        },
    ]
    resp["charts"] = [
        {
            "kind": "line",
            "df": monthly,
            "x": "month",
            "y": "revenue",
            "title": "Monthly Revenue Trend",
        }
    ]
    resp["table"] = monthly
    resp["table_title"] = "Revenue by Month"
    resp["recommended_actions"] = [
        "Drill into any month-over-month dips by category, channel, or "
        "customer segment to find root causes early.",
        "Set a revenue target per month and track variance against this trend.",
    ]
    return resp


def _campaign_performance() -> dict:
    campaigns = queries.get_campaign_performance()
    best = campaigns.iloc[0]
    total_spend = campaigns["spend"].sum()
    total_revenue = campaigns["attributed_revenue"].sum()

    insight_text = (
        f"Across all campaigns, total spend was **{total_spend:,.0f}** and "
        f"attributed revenue was **{total_revenue:,.0f}**.\n\n"
        f"The best-performing campaign by ROAS (return on ad spend) is "
        f"**{best['campaign_name']}** ({best['channel']}), generating "
        f"**{best['attributed_revenue']:,.0f}** in revenue from "
        f"**{best['spend']:,.0f}** spend -- a ROAS of "
        f"**{best['roas']:.2f}x** across {int(best['attributed_orders'])} orders."
    )

    resp = _empty_response()
    resp["insight_text"] = insight_text
    resp["kpis"] = [
        {
            "label": "Best Campaign",
            "value": best["campaign_name"],
            "format": "text",
        },
        {
            "label": "Best Campaign ROAS",
            "value": best["roas"],
            "format": "ratio",
        },
        {
            "label": "Total Marketing Spend",
            "value": total_spend,
            "format": "currency",
        },
    ]
    resp["charts"] = [
        {
            "kind": "bar",
            "df": campaigns,
            "x": "campaign_name",
            "y": "roas",
            "title": "Campaign ROAS (Return on Ad Spend)",
        }
    ]
    resp["table"] = campaigns
    resp["table_title"] = "Campaign Performance"
    resp["recommended_actions"] = [
        f"Consider reallocating budget toward {best['campaign_name']} given its "
        f"strong ROAS.",
        "Review or pause campaigns with ROAS below 1.0x -- they're spending "
        "more than they return.",
    ]
    return resp


def _at_risk() -> dict:
    at_risk_df = queries.get_at_risk_customers()
    session_trend = queries.get_at_risk_session_trend()

    count = len(at_risk_df)
    total_revenue_at_risk = at_risk_df["lifetime_revenue"].sum()
    avg_days_inactive = at_risk_df["days_inactive"].mean()

    insight_text = (
        f"**{count:,} customers** have placed no completed order in the last "
        f"90 days, representing **{total_revenue_at_risk:,.0f}** in historical "
        f"lifetime revenue (average **{avg_days_inactive:.0f} days** since "
        f"their last order).\n\n"
        f"Website activity from this group has also been trending down, "
        f"reinforcing that they are disengaging rather than just between "
        f"purchases."
    )

    resp = _empty_response()
    resp["insight_text"] = insight_text
    resp["kpis"] = [
        {
            "label": "At-Risk Customers",
            "value": count,
            "format": "number",
        },
        {
            "label": "Lifetime Revenue at Risk",
            "value": total_revenue_at_risk,
            "format": "currency",
        },
        {
            "label": "Avg. Days Since Last Order",
            "value": avg_days_inactive,
            "format": "number",
        },
    ]
    resp["charts"] = [
        {
            "kind": "line",
            "df": session_trend,
            "x": "month",
            "y": "session_count",
            "title": "Website Sessions from At-Risk Customers, by Month",
        }
    ]
    resp["table"] = at_risk_df.sort_values("lifetime_revenue", ascending=False).head(15)
    resp["table_title"] = "Top 15 At-Risk Customers by Lifetime Revenue"
    resp["recommended_actions"] = [
        "Launch a win-back email/SMS campaign targeted at customers inactive "
        "90+ days, prioritized by lifetime revenue.",
        "Offer a personalized discount or loyalty incentive to the highest-value "
        "at-risk customers first.",
        "Set up an automated re-engagement trigger for customers approaching "
        "the 90-day inactivity threshold.",
    ]
    return resp


def _revenue_by_category() -> dict:
    cat_df = queries.get_revenue_by_category()
    total_revenue = cat_df["revenue"].sum()
    top = cat_df.iloc[0]
    top_share = top["revenue"] / total_revenue * 100

    insight_text = (
        f"Total revenue across all categories is **{total_revenue:,.0f}**. "
        f"**{top['category']}** is the leading category with "
        f"**{top['revenue']:,.0f}** in revenue "
        f"({top_share:.1f}% of total), from {int(top['units_sold']):,} units sold."
    )

    resp = _empty_response()
    resp["insight_text"] = insight_text
    resp["kpis"] = [
        {
            "label": "Total Revenue",
            "value": total_revenue,
            "format": "currency",
        },
        {
            "label": "Top Category",
            "value": top["category"],
            "format": "text",
        },
        {
            "label": "Top Category Share of Revenue",
            "value": top_share,
            "format": "percent",
        },
    ]
    resp["charts"] = [
        {
            "kind": "bar",
            "df": cat_df,
            "x": "category",
            "y": "revenue",
            "title": "Revenue by Product Category",
        }
    ]
    resp["table"] = cat_df
    resp["table_title"] = "Revenue by Category"
    resp["recommended_actions"] = [
        f"Double down on {top['category']} with expanded assortment or "
        f"featured placement, given it's the top revenue driver.",
        "Review lower-performing categories for pricing, merchandising, or "
        "inventory issues.",
    ]
    return resp


def _pareto() -> dict:
    pareto = queries.get_top5pct_revenue_share().iloc[0]
    top10 = queries.get_top_customers()

    other_revenue = pareto["total_revenue"] - pareto["top5pct_revenue"]

    insight_text = (
        f"The **top 5% of customers** "
        f"({int(pareto['top5pct_customers'])} of {int(pareto['total_customers'])} "
        f"total customers) generate **{pareto['top5pct_share_pct']:.1f}%** of "
        f"total revenue -- **{pareto['top5pct_revenue']:,.0f}** out of "
        f"**{pareto['total_revenue']:,.0f}**.\n\n"
        f"This concentration means retention and growth efforts for this small "
        f"group have an outsized impact on overall revenue."
    )

    resp = _empty_response()
    resp["insight_text"] = insight_text
    resp["kpis"] = [
        {
            "label": "Revenue from Top 5% of Customers",
            "value": pareto["top5pct_share_pct"],
            "format": "percent",
        },
        {
            "label": "Top 5% Customer Count",
            "value": pareto["top5pct_customers"],
            "format": "number",
        },
        {
            "label": "Top 5% Revenue",
            "value": pareto["top5pct_revenue"],
            "format": "currency",
        },
    ]
    resp["charts"] = [
        {
            "kind": "donut",
            "df": pd.DataFrame(
                {
                    "segment": ["Top 5% of Customers", "All Other Customers"],
                    "revenue": [pareto["top5pct_revenue"], other_revenue],
                }
            ),
            "names": "segment",
            "values": "revenue",
            "title": "Revenue Concentration: Top 5% vs. Everyone Else",
        }
    ]
    resp["table"] = top10
    resp["table_title"] = "Top 10 Customers (context for the top 5%)"
    resp["recommended_actions"] = [
        "Build a dedicated retention program for top-5% customers -- losing "
        "even a few has an outsized revenue impact.",
        "Analyze what these customers have in common (segment, channel, "
        "category mix) to find more like them.",
    ]
    return resp


_BUILDERS = {
    "march_dip": _march_dip,
    "top_customers": _top_customers,
    "revenue_trend": _revenue_trend,
    "campaign_performance": _campaign_performance,
    "at_risk": _at_risk,
    "revenue_by_category": _revenue_by_category,
    "pareto": _pareto,
}


def unsupported_response() -> dict:
    questions_list = "\n".join(f"- {q}" for q in SUGGESTED_QUESTIONS)
    resp = _empty_response()
    resp["insight_text"] = (
        "I don't have a predefined report for that question yet. Here's what "
        "I can answer right now:\n\n" + questions_list
    )
    return resp


def build(intent_id: str | None) -> dict:
    if intent_id is None or intent_id not in _BUILDERS:
        return unsupported_response()
    return _BUILDERS[intent_id]()
