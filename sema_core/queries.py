"""
SEMA: saved report library.

Each function below loads one .sql file from sql/queries/ and runs it
through db.run_query(). Think of this module as a set of stored procedures
you can call from Python -- the SQL itself lives in sql/queries/*.sql so it
can be read, reviewed, and edited like any other query file.

Results are cached for a short time (framework-neutral TTL cache, keyed by the
active client) so that re-running the same report (e.g. clicking a suggested
question twice) doesn't hit the database again immediately -- and one client's
cached report is never served to another.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from sema_core.cache import ttl_cache
from sema_core.client_registry import active_client_id
from sema_core.db import run_query, run_sql_readonly

QUERIES_DIR = Path(__file__).resolve().parent.parent / "sql" / "queries"


def _load_sql(filename: str) -> str:
    return (QUERIES_DIR / filename).read_text(encoding="utf-8")


def _normalize_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Postgres ::date columns come back from psycopg2 as Python date objects
    (pandas dtype "object"), which don't compare equal to pd.Timestamp. We
    convert once here so every chart/insight can rely on datetime64 dates."""
    for col in ("month", "day"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    return df


def _run(filename: str) -> pd.DataFrame:
    """Run a saved query through the app's own DB role (`run_query`)."""
    return _normalize_dates(run_query(_load_sql(filename)))


def _run_readonly(filename: str) -> pd.DataFrame:
    """Same as `_run`, but through the read-only role -- for reports (like the
    Daily Brief's daily-grain data) we'd rather be defensive about, the same
    way alerts_engine.py runs its checks through the read-only connection."""
    return _normalize_dates(run_sql_readonly(_load_sql(filename)))


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_data_bounds() -> pd.DataFrame:
    return _run("data_bounds.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_revenue_by_month() -> pd.DataFrame:
    return _run("revenue_by_month.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_revenue_by_category_by_month() -> pd.DataFrame:
    return _run("revenue_by_category_by_month.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_traffic_source_by_month() -> pd.DataFrame:
    return _run("traffic_source_by_month.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_segment_orders_by_month() -> pd.DataFrame:
    return _run("segment_orders_by_month.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_revenue_by_category() -> pd.DataFrame:
    return _run("revenue_by_category.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_top_customers() -> pd.DataFrame:
    return _run("top_customers.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_top5pct_revenue_share() -> pd.DataFrame:
    return _run("top5pct_revenue_share.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_campaign_performance() -> pd.DataFrame:
    return _run("campaign_performance.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_at_risk_customers() -> pd.DataFrame:
    return _run("at_risk_customers.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_at_risk_session_trend() -> pd.DataFrame:
    return _run("at_risk_session_trend.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_daily_orders() -> pd.DataFrame:
    return _run_readonly("daily_orders.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_daily_sessions() -> pd.DataFrame:
    return _run_readonly("daily_sessions.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_product_revenue_by_month() -> pd.DataFrame:
    return _run_readonly("product_revenue_by_month.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_campaign_roi_status() -> pd.DataFrame:
    return _run_readonly("campaign_roi_status.sql")


@ttl_cache(ttl=300, vary_on=active_client_id)
def get_vip_inactive() -> pd.DataFrame:
    return _run_readonly("vip_inactive.sql")
