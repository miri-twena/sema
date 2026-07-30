import type { AuditEvent } from "../../lib/api";

type Dir = "rtl" | "ltr";

const ROLE_LABEL: Record<string, { en: string; he: string }> = {
  client_admin: { en: "Admin", he: "מנהל/ת" },
  analyst: { en: "Analyst", he: "אנליסט/ית" },
  viewer: { en: "Viewer", he: "צופה" },
};

const SCOPE_LABEL: Record<string, { en: string; he: string }> = {
  full: { en: "Full access", he: "גישה מלאה" },
  no_financials: { en: "No financials", he: "ללא נתונים פיננסיים" },
  sales_only: { en: "Sales only", he: "מכירות בלבד" },
  custom: { en: "Custom", he: "מותאם אישית" },
};

function roleLabel(id: unknown, dir: Dir): string {
  const l = typeof id === "string" ? ROLE_LABEL[id] : undefined;
  return l ? l[dir === "rtl" ? "he" : "en"] : String(id ?? "—");
}

function scopeLabel(id: unknown, dir: Dir): string {
  const l = typeof id === "string" ? SCOPE_LABEL[id] : undefined;
  return l ? l[dir === "rtl" ? "he" : "en"] : String(id ?? "—");
}

function field(obj: Record<string, unknown> | null, key: string): unknown {
  return obj ? obj[key] : undefined;
}

/** Category tag shown per row -- the part of the dotted action id before the
 * first ".", capitalized for display ("user" -> "Users"). */
export function auditCategory(action: string): string {
  return action.split(".")[0] ?? action;
}

const CATEGORY_LABEL: Record<string, { en: string; he: string }> = {
  user: { en: "Users", he: "משתמשים" },
  semantic: { en: "Semantic model", he: "מודל סמנטי" },
  org_settings: { en: "Organization settings", he: "הגדרות ארגון" },
  home_config: { en: "Home screen", he: "מסך הבית" },
  data_source: { en: "Data sources", he: "מקורות נתונים" },
  impersonation: { en: "Impersonation", he: "התחזות" },
};

export function auditCategoryLabel(action: string, dir: Dir): string {
  const cat = auditCategory(action);
  const l = CATEGORY_LABEL[cat];
  return l ? l[dir === "rtl" ? "he" : "en"] : cat;
}

/** Impersonation events get an amber side bar in the table/drawer (spec §3
 * item 9) -- the event TYPE exists even though impersonation itself is a
 * platform-level feature not built yet, so no action currently sets this. */
export function isImpersonationEvent(action: string): boolean {
  return auditCategory(action) === "impersonation";
}

type Sentence = (e: AuditEvent, dir: Dir) => string;

const actorOf = (e: AuditEvent) => e.actor_name || "—";
const targetOf = (e: AuditEvent) => e.target_label || "—";

const SENTENCES: Record<string, Sentence> = {
  "user.invited": (e, dir) =>
    dir === "rtl"
      ? `${actorOf(e)} הזמין/ה את ${targetOf(e)} בתור ${roleLabel(field(e.after, "role"), dir)}`
      : `${actorOf(e)} invited ${targetOf(e)} as ${roleLabel(field(e.after, "role"), dir)}`,
  "user.role_changed": (e, dir) =>
    dir === "rtl"
      ? `${actorOf(e)} שינה/תה את התפקיד של ${targetOf(e)} מ-${roleLabel(field(e.before, "role"), dir)} ל-${roleLabel(field(e.after, "role"), dir)}`
      : `${actorOf(e)} changed ${targetOf(e)}'s role from ${roleLabel(field(e.before, "role"), dir)} to ${roleLabel(field(e.after, "role"), dir)}`,
  "user.suspended": (e, dir) =>
    dir === "rtl" ? `${actorOf(e)} השעה/תה את ${targetOf(e)}` : `${actorOf(e)} suspended ${targetOf(e)}`,
  "user.reactivated": (e, dir) =>
    dir === "rtl" ? `${actorOf(e)} הפעיל/ה מחדש את ${targetOf(e)}` : `${actorOf(e)} reactivated ${targetOf(e)}`,
  "user.data_scope_changed": (e, dir) =>
    dir === "rtl"
      ? `${actorOf(e)} שינה/תה את גישת הנתונים של ${targetOf(e)} מ-${scopeLabel(field(e.before, "data_scope"), dir)} ל-${scopeLabel(field(e.after, "data_scope"), dir)}`
      : `${actorOf(e)} changed ${targetOf(e)}'s data access from ${scopeLabel(field(e.before, "data_scope"), dir)} to ${scopeLabel(field(e.after, "data_scope"), dir)}`,
  "user.removed": (e, dir) =>
    dir === "rtl"
      ? `${actorOf(e)} הסיר/ה את ${targetOf(e)} מהארגון`
      : `${actorOf(e)} removed ${targetOf(e)} from the organization`,
  "user.invite_resent": (e, dir) =>
    dir === "rtl" ? `${actorOf(e)} שלח/ה שוב הזמנה ל-${targetOf(e)}` : `${actorOf(e)} resent an invite to ${targetOf(e)}`,
  "semantic.published": (e, dir) =>
    dir === "rtl"
      ? `${actorOf(e)} פרסם/ה את המודל הסמנטי (${targetOf(e)})`
      : `${actorOf(e)} published the semantic model (${targetOf(e)})`,
  "semantic.restored": (e, dir) =>
    dir === "rtl"
      ? `${actorOf(e)} שחזר/ה את המודל הסמנטי לגרסה ${field(e.before, "version")}`
      : `${actorOf(e)} restored the semantic model to version ${field(e.before, "version")}`,
  "org_settings.updated": (e, dir) => {
    const before = e.before ? Object.values(e.before)[0] : undefined;
    const after = e.after ? Object.values(e.after)[0] : undefined;
    return dir === "rtl"
      ? `${actorOf(e)} עדכן/ה את "${targetOf(e)}" מ-${before ?? "—"} ל-${after ?? "—"}`
      : `${actorOf(e)} changed "${targetOf(e)}" from ${before ?? "—"} to ${after ?? "—"}`;
  },
  "data_source.problem_reported": (e, dir) =>
    dir === "rtl"
      ? `${actorOf(e)} דיווח/ה על בעיה במקור הנתונים "${targetOf(e)}"`
      : `${actorOf(e)} reported a problem with the "${targetOf(e)}" data source`,
};

/** One human-readable sentence for an audit row, in the app's active
 * language -- built from the action id + target, never hardcoded per row so
 * every surface (table row, drawer header) reads identically. Falls back to
 * a generic "{actor} performed {action} on {target}" for an action id this
 * module doesn't recognize yet, so a new action is never silently blank. */
export function auditSentence(e: AuditEvent, dir: Dir): string {
  const build = SENTENCES[e.action];
  if (build) return build(e, dir);
  return dir === "rtl"
    ? `${actorOf(e)} ביצע/ה ${e.action} על ${targetOf(e)}`
    : `${actorOf(e)} performed ${e.action} on ${targetOf(e)}`;
}
