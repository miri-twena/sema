// Bilingual copy for the "placeholders pass" (product_placeholders_prompt.md):
// every discussed-but-not-yet-built surface gets a real entry point now, with
// consistent "coming soon" feedback. Read via lib/useUiLang.ts. Same
// Record<Lang, {...}> shape as lib/loginCopy.ts's LOGIN_COPY.
//
// COMMON/USER_MENU/ROLE_LABEL/GEAR_MENU used to live here too; they moved
// into the central locale files (locales/en.ts + he.ts, useT()) when
// i18n_language_files_prompt.md replaced every scattered copy dict with one
// mechanism. DATA_SOURCE_GALLERY (the Data sources "Add a source" gallery)
// is deliberately NOT migrated in that pass -- AddDataSourceModal.tsx reads
// only its `.en` half by design (a prior, still-current decision to keep
// that one flow English-only regardless of org language, documented in the
// modal itself), so moving it into the org-language-aware locale files would
// misrepresent it as something that should follow the org setting.

export type Lang = "he" | "en";

export const DATA_SOURCE_GALLERY = {
  en: {
    title: "Add a data source",
    subtitle: "Connections are set up by the platform team; this shows what's on the way.",
    addButton: "Add data source",
    groups: {
      sql: "SQL databases",
      business: "Business systems",
      easy: "Files and sheets",
      soon: "Coming soon",
    },
    connectorUnlocks: {
      postgres: "Connect a PostgreSQL database directly.",
      mysql: "Connect a MySQL database directly.",
      mssql: "Connect a Microsoft SQL Server database directly.",
      priority: "Orders, invoices, inventory, customers and suppliers.",
      salesforce: "Leads, opportunities, accounts and sales activity.",
      sap_b1: "Orders, invoices, inventory and financials from SAP B1.",
      google_sheets: "Pull data straight from a shared spreadsheet.",
      csv: "Upload a file to analyze right away.",
      google_drive: "Pull spreadsheets and CSV files from a shared Drive folder.",
      sharepoint: "Pull files and lists from SharePoint sites.",
    },
    toast: "That connection will open here soon — in development.",
  },
  he: {
    title: "הוסף מקור נתונים",
    subtitle: "חיבורים מוגדרים על ידי צוות הפלטפורמה; כאן רואים מה בדרך.",
    addButton: "הוסף מקור נתונים",
    groups: {
      sql: "מסדי נתונים SQL",
      business: "מערכות עסקיות",
      easy: "קבצים וגליונות",
      soon: "בקרוב",
    },
    connectorUnlocks: {
      postgres: "חיבור ישיר למסד נתונים PostgreSQL.",
      mysql: "חיבור ישיר למסד נתונים MySQL.",
      mssql: "חיבור ישיר למסד נתונים Microsoft SQL Server.",
      priority: "הזמנות, חשבוניות, מלאי, לקוחות וספקים.",
      salesforce: "לידים, הזדמנויות, חשבונות ופעילות מכירה.",
      sap_b1: "הזמנות, חשבוניות, מלאי ופיננסים מ-SAP B1.",
      google_sheets: "משיכת נתונים ישירות מגיליון משותף.",
      csv: "העלאת קובץ לניתוח מיידי.",
      google_drive: "משיכת גיליונות וקבצי CSV מתיקיית Drive משותפת.",
      sharepoint: "משיכת קבצים ורשימות מאתרי SharePoint.",
    },
    toast: "החיבור ייפתח כאן בקרוב — בפיתוח.",
  },
} as const;

export type ConnectorKey = keyof (typeof DATA_SOURCE_GALLERY)["en"]["connectorUnlocks"];
