// Hebrew labels for the fixed vocabulary of column names the agent's SQL
// actually produces (sql/schema.sql's tables + sql/semantic/*.yaml's metric/
// dimension names and SQL aliases) -- so a table answering a Hebrew question
// shows Hebrew headers instead of prettified English snake_case. A column
// outside this known vocabulary (the agent can alias freely) falls back to
// the English prettified form rather than a guessed/broken translation.
const COLUMN_LABEL_HE: Record<string, string> = {
  // customers
  customer_id: "מזהה לקוח",
  customer_name: "שם לקוח",
  first_name: "שם פרטי",
  last_name: "שם משפחה",
  email: "אימייל",
  signup_date: "תאריך הרשמה",
  country: "מדינה",
  acquisition_channel: "ערוץ רכישה",
  segment: "פלח",
  // products
  product_id: "מזהה מוצר",
  product_name: "שם מוצר",
  category: "קטגוריה",
  unit_price: "מחיר יחידה",
  unit_cost: "עלות יחידה",
  launch_date: "תאריך השקה",
  is_active: "פעיל",
  // marketing_campaigns
  campaign_id: "מזהה קמפיין",
  campaign_name: "שם קמפיין",
  channel: "ערוץ",
  start_date: "תאריך התחלה",
  end_date: "תאריך סיום",
  budget: "תקציב",
  spend: "הוצאה",
  // orders / order_items
  order_id: "מזהה הזמנה",
  order_date: "תאריך הזמנה",
  status: "סטטוס",
  traffic_source: "מקור תנועה",
  discount_amount: "סכום הנחה",
  shipping_cost: "עלות משלוח",
  total_amount: "סכום כולל",
  order_item_id: "מזהה פריט הזמנה",
  quantity: "כמות",
  // website_sessions
  session_id: "מזהה ביקור",
  session_start: "תחילת ביקור",
  device_type: "סוג מכשיר",
  converted: "הומר",
  // time grains
  month: "חודש",
  year: "שנה",
  week: "שבוע",
  day: "יום",
  date: "תאריך",
  // semantic-layer metrics/aliases
  revenue: "הכנסה",
  cogs: "עלות (COGS)",
  gross_profit: "רווח גולמי",
  gross_margin: "מארג'ין גולמי",
  gross_margin_pct: "מארג'ין %",
  aov: "ערך הזמנה ממוצע (AOV)",
  conversion_rate: "שיעור המרה",
  conversion_rate_pct: "שיעור המרה %",
  churn_risk: "סיכון נטישה",
  at_risk_count: "לקוחות בסיכון",
  high_value_at_risk: "לקוחות בעלי ערך גבוה בסיכון",
  active_customers: "לקוחות פעילים",
  active_count: "מספר פעילים",
  returning_customers: "לקוחות חוזרים",
  vip_customers: "לקוחות VIP",
  completed_orders: "הזמנות שהושלמו",
  attributed_orders: "הזמנות משויכות",
  attributed_revenue: "הכנסה משויכת",
  lifetime_revenue: "הכנסה מצטברת",
  ltv: "ערך לקוח לכל החיים (LTV)",
  last_order: "הזמנה אחרונה",
  last_order_date: "תאריך הזמנה אחרונה",
  mom_aov_change: "שינוי חודשי ב-AOV",
  mom_pct_change: "שינוי חודשי (%)",
  pct_rank: "דירוג אחוזון",
  roi: "תשואה (ROI)",
  units_sold: "יחידות שנמכרו",
  revenue_by_category: "הכנסה לפי קטגוריה",
};

/** Title-cases a snake_case column name: "gross_profit" -> "Gross Profit". */
export function prettifyColumn(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Column header in the app's active direction -- Hebrew for a known column
 * name when the question was asked in Hebrew, else the prettified English
 * name (also the fallback for any column outside the known vocabulary). */
export function columnLabel(name: string, dir?: "rtl" | "ltr"): string {
  if (dir === "rtl") {
    const he = COLUMN_LABEL_HE[name.toLowerCase()];
    if (he) return he;
  }
  return prettifyColumn(name);
}
