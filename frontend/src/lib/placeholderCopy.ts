// Bilingual copy for the "placeholders pass" (product_placeholders_prompt.md):
// every discussed-but-not-yet-built surface gets a real entry point now, with
// consistent "coming soon" feedback. Read via lib/useUiLang.ts. Same
// Record<Lang, {...}> shape as lib/loginCopy.ts's LOGIN_COPY.

export type Lang = "he" | "en";

export const COMMON = {
  en: { comingSoon: "Coming soon" },
  he: { comingSoon: "בקרוב" },
} as const;

export const USER_MENU = {
  en: { personalSettings: "Personal settings", logOut: "Log out" },
  he: { personalSettings: "הגדרות אישיות", logOut: "התנתקות" },
} as const;

// Bilingual role label for the sidebar user row -- small enough to keep
// local rather than exporting auditSentences.ts's private (unrelated-scope)
// copy of the same three entries.
export const ROLE_LABEL: Record<string, { en: string; he: string }> = {
  client_admin: { en: "Admin", he: "מנהל/ת" },
  analyst: { en: "Analyst", he: "אנליסט/ית" },
  viewer: { en: "Viewer", he: "צופה" },
};

export const GEAR_MENU = {
  en: { manageOrg: "Manage organization", platformConsole: "Platform console" },
  he: { manageOrg: "ניהול הארגון", platformConsole: "קונסולת פלטפורמה" },
} as const;

export const DATA_SOURCE_GALLERY = {
  en: {
    title: "Add a data source",
    subtitle: "Connections are set up by the platform team; this shows what's on the way.",
    addButton: "Add data source",
    groups: {
      sql: "SQL databases",
      business: "Business systems",
      easy: "Easy sources",
      soon: "Coming soon",
    },
    connectorUnlocks: {
      postgres: "Connect a PostgreSQL database directly.",
      mysql: "Connect a MySQL database directly.",
      mssql: "Connect a Microsoft SQL Server database directly.",
      priority: "Orders, invoices, inventory, customers and suppliers.",
      salesforce: "Leads, opportunities, accounts and sales activity.",
      google_sheets: "Pull data straight from a shared spreadsheet.",
      csv: "Upload a file to analyze right away.",
      shopify: "Storefront orders, products and customers.",
      google_analytics: "Website traffic and conversion behavior.",
      meta_ads: "Ad spend and campaign performance.",
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
      easy: "מקורות קלים",
      soon: "בקרוב",
    },
    connectorUnlocks: {
      postgres: "חיבור ישיר למסד נתונים PostgreSQL.",
      mysql: "חיבור ישיר למסד נתונים MySQL.",
      mssql: "חיבור ישיר למסד נתונים Microsoft SQL Server.",
      priority: "הזמנות, חשבוניות, מלאי, לקוחות וספקים.",
      salesforce: "לידים, הזדמנויות, חשבונות ופעילות מכירה.",
      google_sheets: "משיכת נתונים ישירות מגיליון משותף.",
      csv: "העלאת קובץ לניתוח מיידי.",
      shopify: "הזמנות, מוצרים ולקוחות מהחנות.",
      google_analytics: "תנועה באתר והתנהגות המרה.",
      meta_ads: "הוצאות פרסום וביצועי קמפיינים.",
    },
    toast: "החיבור ייפתח כאן בקרוב — בפיתוח.",
  },
} as const;

export type ConnectorKey = keyof (typeof DATA_SOURCE_GALLERY)["en"]["connectorUnlocks"];
