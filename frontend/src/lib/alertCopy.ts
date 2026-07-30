// Bilingual copy for the template-based alert builder (alert_templates_
// prompt.md). Template label/description come straight from the server
// catalog (already bilingual, api.admin.alerts.templates()) -- this file
// only covers form chrome and the small per-metric Hebrew label map the
// metrics catalog endpoint doesn't carry. Same Record<Lang,{...}> shape as
// lib/loginCopy.ts / lib/placeholderCopy.ts.

export type Lang = "he" | "en";

export const METRIC_LABEL_HE: Record<string, string> = {
  revenue: "הכנסות",
  orders: "הזמנות",
  aov: "שווי הזמנה ממוצע",
  churn_risk: "לקוחות בסיכון נטישה",
};

export const ALERT_BUILDER = {
  en: {
    heading: "Your alerts",
    newAlert: "New alert",
    noOrgAlerts: "No alerts created yet.",
    fields: {
      name: "Name",
      metric: "Metric",
      templateType: "Alert type",
      severity: "Severity",
    },
    severity: { critical: "Critical", warning: "Warning" },
    params: {
      window: "Compared to",
      windowOptions: { dod: "yesterday", wow: "last week", mom: "last month" },
      direction: "Direction",
      directionOptions: { drop: "Drops", rise: "Rises" },
      thresholdPct: "By more than (%)",
      operator: "Condition",
      operatorOptions: { above: "Goes above", below: "Goes below" },
      value: "Value",
      nSigma: "Standard deviations",
      nDays: "Consecutive days",
    },
    runTest: "Run test",
    testing: "Testing…",
    testFiredPlural: (n: number) => `Would have fired ${n} times in the last 90 days.`,
    testFiredZero: "Would not have fired in the last 90 days -- consider a tighter threshold.",
    testError: "Couldn't evaluate this alert against the data.",
    save: "Save",
    cancel: "Cancel",
    edit: "Edit",
    delete: "Delete",
    deleteConfirm: "Delete this alert?",
    disabledReason: (reason: string) => `Auto-disabled: ${reason}`,
    limitReached: "You've reached the 12-alert limit -- disable or delete one to add another.",
    saveBlocked: "Run a test with these settings before saving.",
    enabledLabel: "Enabled",
  },
  he: {
    heading: "ההתראות שלך",
    newAlert: "התראה חדשה",
    noOrgAlerts: "עדיין לא נוצרו התראות.",
    fields: {
      name: "שם",
      metric: "מדד",
      templateType: "סוג התראה",
      severity: "חומרה",
    },
    severity: { critical: "קריטי", warning: "אזהרה" },
    params: {
      window: "בהשוואה ל",
      windowOptions: { dod: "אתמול", wow: "שבוע שעבר", mom: "חודש שעבר" },
      direction: "כיוון",
      directionOptions: { drop: "יורד", rise: "עולה" },
      thresholdPct: "ביותר מ (%)",
      operator: "תנאי",
      operatorOptions: { above: "עולה מעל", below: "יורד מתחת ל" },
      value: "ערך",
      nSigma: "סטיות תקן",
      nDays: "ימים רצופים",
    },
    runTest: "הרץ בדיקה",
    testing: "בודק…",
    testFiredPlural: (n: number) => `הייתה מופעלת ${n} פעמים ב-90 הימים האחרונים.`,
    testFiredZero: "לא הייתה מופעלת ב-90 הימים האחרונים -- כדאי לשקול סף מחמיר יותר.",
    testError: "לא ניתן היה להעריך את ההתראה מול הנתונים.",
    save: "שמירה",
    cancel: "ביטול",
    edit: "עריכה",
    delete: "מחיקה",
    deleteConfirm: "למחוק את ההתראה?",
    disabledReason: (reason: string) => `נוטרלה אוטומטית: ${reason}`,
    limitReached: "הגעת למגבלה של 12 התראות -- יש לנטרל או למחוק אחת כדי להוסיף.",
    saveBlocked: "יש להריץ בדיקה עם ההגדרות האלה לפני השמירה.",
    enabledLabel: "פעילה",
  },
} as const;

export const DEFAULT_PARAMS: Record<string, Record<string, unknown>> = {
  pct_change: { window: "mom", direction: "drop", threshold_pct: 10 },
  absolute_threshold: { operator: "above", value: 0 },
  anomaly: { n_sigma: 2 },
  streak: { n_days: 3, direction: "drop" },
};
