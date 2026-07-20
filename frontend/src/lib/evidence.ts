// Localized rendering for the trust panel. The server sends STRUCTURED facts
// (stage keys, {op, ...} steps, raw counts) and the language is chosen here
// from the user's question -- so a Hebrew answer gets a Hebrew trust panel.

export interface AnalysisStep {
  op?: string;
  name?: string;
  value?: string;
  start?: string | null;
  end?: string | null;
  count?: number;
  sources?: string[];
  by?: string;
}

export type Lang = "he" | "en";

export const EV_LABELS: Record<Lang, Record<string, string>> = {
  en: {
    evidence: "Why you can trust this answer",
    definition: "Metric definition",
    connection: "Connection",
    sources: "Source tables",
    dateRange: "Date range",
    filters: "Filters applied",
    sqlStatus: "SQL execution",
    rows: "Rows returned",
    queriedAt: "Data queried at",
    assumptions: "Assumptions",
    checked: "What SEMA checked",
    noAssumptions: "No unsupported assumptions",
    unavailable: "Source detail unavailable",
  },
  he: {
    evidence: "למה אפשר לסמוך על התשובה",
    definition: "הגדרת המדד",
    connection: "חיבור",
    sources: "טבלאות מקור",
    dateRange: "טווח תאריכים",
    filters: "פילטרים שהוחלו",
    sqlStatus: "הרצת SQL",
    rows: "שורות שהוחזרו",
    queriedAt: "הנתונים נשלפו ב",
    assumptions: "הנחות",
    checked: "מה SEMA בדקה",
    noAssumptions: "לא נדרשו הנחות",
    unavailable: "פרטי המקור אינם זמינים",
  },
};

const n = (v: number | undefined) => (v ?? 0).toLocaleString();
const one = (v: number | undefined) => (v ?? 0) === 1;

/** One structured operation -> a short factual sentence in `lang`. */
export function stepText(s: AnalysisStep, lang: Lang): string {
  const he = lang === "he";
  switch (s.op) {
    case "metric":
      return he ? `נעשה שימוש בהגדרה המאושרת “${s.name}”.` : `Used the approved “${s.name}” definition.`;
    case "date_range": {
      const range = s.start && s.end ? `${s.start} – ${s.end}` : s.start || s.end || "";
      return he ? `סינון לטווח ${range}.` : `Filtered to ${range}.`;
    }
    case "filter":
      return he ? `הוחל פילטר: ${s.value}.` : `Applied filter: ${s.value}.`;
    case "queries": {
      const src = s.sources?.length ? s.sources.join(", ") : "";
      if (he) {
        const head = one(s.count) ? "הורצה שאילתה אחת" : `הורצו ${n(s.count)} שאילתות`;
        return `${head}${src ? ` מול ${src}` : ""}.`;
      }
      return `Ran ${n(s.count)} ${one(s.count) ? "query" : "queries"}${src ? ` against ${src}` : ""}.`;
    }
    case "rows":
      if (he) return one(s.count) ? "הוחזרה שורה אחת בסך הכול." : `הוחזרו ${n(s.count)} שורות בסך הכול.`;
      return `Returned ${n(s.count)} ${one(s.count) ? "row" : "rows"} in total.`;
    case "comparison":
      return he ? "בוצעה השוואה מול תקופת בסיס." : "Compared the result against a baseline period.";
    case "breakdown":
      return he ? `פילוח התוצאה לפי ${s.by}.` : `Broke the result down by ${s.by}.`;
    case "table_rows":
      if (he) return one(s.count) ? "הוצגה שורה אחת בטבלה." : `הוצגו ${n(s.count)} שורות בטבלה.`;
      return `Listed ${n(s.count)} ${one(s.count) ? "row" : "rows"} in a table.`;
    case "failed_queries":
      if (he)
        return one(s.count)
          ? "שאילתה אחת נכשלה ולא נכללה בתשובה."
          : `${n(s.count)} שאילתות נכשלו ולא נכללו בתשובה.`;
      return `${n(s.count)} ${one(s.count) ? "query" : "queries"} failed and were not used.`;
    default:
      return ""; // unknown op: stay silent rather than invent a description
  }
}

/** Execution status line. Only ever claims success when a query really ran. */
export function sqlStatusText(
  status: "ok" | "failed" | "none" | undefined,
  runs: number,
  failed: number,
  lang: Lang,
): string {
  const he = lang === "he";
  if (status === "ok") {
    const base = he
      ? `בוצעה בהצלחה (${runs === 1 ? "שאילתה אחת" : `${n(runs)} שאילתות`})`
      : `Executed successfully (${n(runs)} ${runs === 1 ? "query" : "queries"})`;
    if (!failed) return base;
    return he ? `${base}, ${n(failed)} נכשלו` : `${base}, ${n(failed)} failed`;
  }
  if (status === "failed") {
    return he
      ? "השאילתה נכשלה — התשובה לא אומתה מול מסד הנתונים"
      : "Query failed — answer not verified against the database";
  }
  return he ? "לא הורצה שאילתה" : "No query was executed";
}
