"""
SEMA: the "add a data source" connector catalog (data_sources_add_prompt.md,
client screens spec §4.4 v1.6). Server-side and config-driven on purpose --
the frontend renders whatever this returns rather than hardcoding connector
metadata, so a new connector (or an availability flip once a driver is
sorted out) is a one-line change here, not a frontend deploy.

`kind` decides which add-flow the frontend opens when a card is clicked:
  sql_db       -> the credentials wizard (Path A)
  saas_request -> the non-secret request form (Path B)
  light        -> Google Sheets / CSV-upload flow (Path C)
`availability` gates whether that flow is reachable at all:
  available      -> the flow opens normally
  coming_soon    -> click only records interest, no flow opens
  driver_pending -> same as coming_soon, but the copy explains it's a driver/
                    packaging gap specifically (see MYSQL_AVAILABLE below)
"""

from __future__ import annotations

# MySQL's driver (pymysql) is pure-Python -- no system libraries needed, so
# it installs the same everywhere. Kept as a constant (not hardcoded true)
# so a future environment where it genuinely can't be installed just flips
# this one line rather than editing the catalog rows below.
MYSQL_AVAILABLE = True

# pymssql ships a manylinux wheel with FreeTDS statically bundled -- verified
# it installs cleanly in this project's own API container with no apt-get
# system packages required (see the queue's evidence log for that check).
MSSQL_AVAILABLE = True

CONNECTOR_CATALOG: list[dict] = [
    {
        "id": "postgres",
        "kind": "sql_db",
        "label": "PostgreSQL",
        "unlocks": {"en": "Connect a PostgreSQL database directly.", "he": "חיבור ישיר למסד נתונים PostgreSQL."},
        "availability": "available",
    },
    {
        "id": "mysql",
        "kind": "sql_db",
        "label": "MySQL",
        "unlocks": {"en": "Connect a MySQL database directly.", "he": "חיבור ישיר למסד נתונים MySQL."},
        "availability": "available" if MYSQL_AVAILABLE else "driver_pending",
    },
    {
        "id": "mssql",
        "kind": "sql_db",
        "label": "Microsoft SQL Server",
        "unlocks": {
            "en": "Connect a Microsoft SQL Server database directly.",
            "he": "חיבור ישיר למסד נתונים Microsoft SQL Server.",
        },
        "availability": "available" if MSSQL_AVAILABLE else "driver_pending",
    },
    {
        "id": "priority",
        "kind": "saas_request",
        "label": "Priority ERP",
        "unlocks": {
            "en": "Orders, invoices, inventory, customers and suppliers.",
            "he": "הזמנות, חשבוניות, מלאי, לקוחות וספקים.",
        },
        "availability": "available",
    },
    {
        "id": "salesforce",
        "kind": "saas_request",
        "label": "Salesforce",
        "unlocks": {
            "en": "Leads, opportunities, accounts and sales activity.",
            "he": "לידים, הזדמנויות, חשבונות ופעילות מכירה.",
        },
        "availability": "available",
    },
    {
        "id": "google_sheets",
        "kind": "light",
        "label": "Google Sheets",
        "unlocks": {
            "en": "Pull data straight from a shared spreadsheet.",
            "he": "משיכת נתונים ישירות מגיליון משותף.",
        },
        "availability": "available",
    },
    {
        "id": "csv",
        "kind": "light",
        "label": "Excel / CSV",
        "unlocks": {"en": "Upload a file to analyze right away.", "he": "העלאת קובץ לניתוח מיידי."},
        "availability": "available",
    },
    {
        "id": "shopify",
        "kind": "saas_request",
        "label": "Shopify",
        "unlocks": {"en": "Storefront orders, products and customers.", "he": "הזמנות, מוצרים ולקוחות מהחנות."},
        "availability": "coming_soon",
    },
    {
        "id": "google_analytics",
        "kind": "saas_request",
        "label": "Google Analytics",
        "unlocks": {"en": "Website traffic and conversion behavior.", "he": "תנועה באתר והתנהגות המרה."},
        "availability": "coming_soon",
    },
    {
        "id": "meta_ads",
        "kind": "saas_request",
        "label": "Meta Ads",
        "unlocks": {"en": "Ad spend and campaign performance.", "he": "הוצאות פרסום וביצועי קמפיינים."},
        "availability": "coming_soon",
    },
]


def get_catalog() -> list[dict]:
    return CONNECTOR_CATALOG


def get_connector(connector_id: str) -> dict | None:
    return next((c for c in CONNECTOR_CATALOG if c["id"] == connector_id), None)
