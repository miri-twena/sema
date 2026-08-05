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
  alert: { en: "Alerts", he: "התראות" },
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
  "semantic.draft_saved": (e, dir) =>
    dir === "rtl"
      ? `${actorOf(e)} שמר/ה טיוטה עבור ${targetOf(e)}`
      : `${actorOf(e)} saved a draft for ${targetOf(e)}`,
  "semantic.draft_discarded": (e, dir) =>
    dir === "rtl"
      ? `${actorOf(e)} מחק/ה את הטיוטה עבור ${targetOf(e)}`
      : `${actorOf(e)} discarded the draft for ${targetOf(e)}`,
  "semantic.draft_archived": (e, dir) =>
    dir === "rtl"
      ? `${actorOf(e)} סימן/ה את ${targetOf(e)} כמיושן (ממתין לפרסום)`
      : `${actorOf(e)} marked ${targetOf(e)} as deprecated (pending publish)`,
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
  "alert.created": (e, dir) =>
    dir === "rtl" ? `${actorOf(e)} יצר/ה את ההתראה "${targetOf(e)}"` : `${actorOf(e)} created the "${targetOf(e)}" alert`,
  "alert.updated": (e, dir) =>
    dir === "rtl" ? `${actorOf(e)} ערך/ה את ההתראה "${targetOf(e)}"` : `${actorOf(e)} edited the "${targetOf(e)}" alert`,
  "alert.toggled": (e, dir) => {
    const enabled = field(e.after, "enabled");
    if (dir === "rtl") {
      return enabled === false
        ? `${actorOf(e)} ניטרל/ה את ההתראה "${targetOf(e)}"`
        : `${actorOf(e)} הפעיל/ה את ההתראה "${targetOf(e)}"`;
    }
    return enabled === false
      ? `${actorOf(e)} disabled the "${targetOf(e)}" alert`
      : `${actorOf(e)} enabled the "${targetOf(e)}" alert`;
  },
  "alert.deleted": (e, dir) =>
    dir === "rtl" ? `${actorOf(e)} מחק/ה את ההתראה "${targetOf(e)}"` : `${actorOf(e)} deleted the "${targetOf(e)}" alert`,
  // impersonation_prompt.md: `actor` is always the REAL admin on these two
  // events specifically (unlike every other row, where a dual-identity event
  // has the TARGET as actor and the admin as impersonator -- see
  // impersonatorSuffix below).
  "impersonation.started": (e, dir) =>
    dir === "rtl"
      ? `${actorOf(e)} התחיל/ה לצפות כ${targetOf(e)}`
      : `${actorOf(e)} started viewing as ${targetOf(e)}`,
  "impersonation.stopped": (e, dir) => {
    const expired = field(e.after, "reason") === "expired";
    if (dir === "rtl") {
      return expired
        ? `הצפייה של ${actorOf(e)} כ${targetOf(e)} הסתיימה (פג תוקף)`
        : `${actorOf(e)} הפסיק/ה לצפות כ${targetOf(e)}`;
    }
    return expired
      ? `${actorOf(e)}'s session viewing as ${targetOf(e)} expired`
      : `${actorOf(e)} stopped viewing as ${targetOf(e)}`;
  },
};

/** "Dana Levi (via Miri Levi)" -- appended after the actor's name wherever an
 * audit row is rendered, whenever this action happened WHILE the real admin
 * was impersonating `actor_name` (impersonation_prompt.md's audit spec: every
 * such action must show BOTH identities, never plain-target with no trace of
 * the admin). Empty string when there's no impersonator (the overwhelming
 * majority of rows). */
export function impersonatorSuffix(e: AuditEvent, dir: Dir): string {
  if (!e.impersonator_name) return "";
  return dir === "rtl" ? ` (על ידי ${e.impersonator_name})` : ` (via ${e.impersonator_name})`;
}

/** One human-readable sentence for an audit row, in the app's active
 * language -- built from the action id + target, never hardcoded per row so
 * every surface (table row, drawer header) reads identically. Falls back to
 * a generic "{actor} performed {action} on {target}" for an action id this
 * module doesn't recognize yet, so a new action is never silently blank.
 *
 * impersonation_prompt.md: whenever the event carries an impersonator (this
 * action happened while the real admin was impersonating `actor_name`), the
 * sentence gets a trailing "(via {impersonator})" -- e.g. "Dana Levi invited
 * Ronit Shapira as Analyst (via Miri Levi)" -- so no action performed while
 * impersonating can ever read as plain-target with no trace of the admin. */
export function auditSentence(e: AuditEvent, dir: Dir): string {
  const build = SENTENCES[e.action];
  const base = build
    ? build(e, dir)
    : dir === "rtl"
      ? `${actorOf(e)} ביצע/ה ${e.action} על ${targetOf(e)}`
      : `${actorOf(e)} performed ${e.action} on ${targetOf(e)}`;
  return base + impersonatorSuffix(e, dir);
}
