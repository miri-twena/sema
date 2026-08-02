import { useEffect, useState } from "react";
import { Download, Search } from "lucide-react";
import { api, type AuditEvent } from "../../lib/api";
import { useAuditLog } from "../../hooks/useAuditLog";
import { initials, pastelFor } from "../../lib/avatar";
import { timeAgo } from "../../lib/time";
import { auditCategory, auditCategoryLabel, auditSentence, isImpersonationEvent } from "./auditSentences";
import { AuditEventDrawer } from "./AuditEventDrawer";
import { Pager } from "./Pager";
import { CHART_PALETTE, CHART_PALETTE_TEXT } from "../../lib/tokens";

/** Category -> identity hue index, so a long log becomes scannable at a
 * glance. `impersonation` shares coral with `alert` -- both read as "needs
 * attention". */
const CATEGORY_HUE: Record<string, number> = {
  user: 0,
  semantic: 5,
  org_settings: 2,
  home_config: 1,
  data_source: 4,
  alert: 3,
  impersonation: 3,
};

const CATEGORIES = [
  { id: "user", label: "Users" },
  { id: "semantic", label: "Semantic model" },
  { id: "org_settings", label: "Organization settings" },
  { id: "home_config", label: "Home screen" },
  { id: "data_source", label: "Data sources" },
  { id: "alert", label: "Alerts" },
  { id: "impersonation", label: "Impersonation" },
];

function SkeletonRows() {
  return (
    <div aria-busy="true" className="flex flex-col">
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="flex items-center gap-3 px-2 py-2.5">
          <div className="w-20 h-3 rounded bg-surfaceAlt animate-pulse" />
          <div className="w-7 h-7 rounded-full bg-surfaceAlt animate-pulse" />
          <div className="flex-1 h-3 rounded bg-surfaceAlt animate-pulse" />
          <div className="w-24 h-5 rounded-full bg-surfaceAlt animate-pulse" />
        </div>
      ))}
    </div>
  );
}

function EventRow({ event, onOpen }: { event: AuditEvent; onOpen: (e: AuditEvent) => void }) {
  const [bg, fg] = pastelFor(event.actor_id || event.actor_name || "system");
  const impersonation = isImpersonationEvent(event.action);
  const hueIdx = CATEGORY_HUE[auditCategory(event.action)] ?? 0;
  const hue = CHART_PALETTE[hueIdx];
  const hueText = CHART_PALETTE_TEXT[hueIdx];
  return (
    <button
      onClick={() => onOpen(event)}
      className={`w-full text-start flex items-center gap-3 px-2 py-2.5 border-s-2 ${
        impersonation ? "border-s-warning-fg" : "border-s-transparent"
      } hover:bg-surfaceAlt transition focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 rounded-md`}
    >
      <span className="w-28 shrink-0 text-[0.75rem] text-muted" title={event.created_at}>
        {timeAgo(event.created_at)}
      </span>
      <span
        aria-hidden
        className="shrink-0 inline-flex items-center justify-center w-7 h-7 rounded-full text-[0.66rem] font-semibold"
        style={{ background: bg, color: fg }}
      >
        {initials(event.actor_name || "?")}
      </span>
      <span className="flex-1 min-w-0 text-[0.85rem] text-ink truncate" dir="auto">
        {auditSentence(event, "ltr")}
      </span>
      <span
        className="shrink-0 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[0.68rem] font-medium"
        style={{ background: `${hue}24`, color: hueText }}
      >
        <span className="w-[5px] h-[5px] rounded-full shrink-0" style={{ background: hue }} aria-hidden />
        {auditCategoryLabel(event.action, "ltr")}
      </span>
    </button>
  );
}

/**
 * The "Audit log" screen (spec §3): a chronological, filterable, paginated
 * view of every admin-panel mutation, with a CSV export and a row-click
 * drawer for the field-by-field diff. Filtering/pagination are server-side
 * (see useAuditLog) since the log can grow unbounded, unlike Users.
 */
export function AuditLogScreen({ clientLabel }: { clientLabel: string }) {
  const {
    events,
    total,
    page,
    pageSize,
    loading,
    error,
    filtering,
    actor,
    setActor,
    category,
    setCategory,
    dateFrom,
    setDateFrom,
    dateTo,
    setDateTo,
    search,
    setSearch,
    setPage,
    clearFilters,
    exportUrl,
  } = useAuditLog();

  const [selected, setSelected] = useState<AuditEvent | null>(null);
  // Actor dropdown options -- this org's users, fetched once. A removed
  // user's past events still filter fine by id even once they drop off
  // this list; only the picker itself would no longer offer them.
  const [actorOptions, setActorOptions] = useState<{ id: string; label: string }[]>([]);
  useEffect(() => {
    // page_size big enough to cover any real org in one call -- this needs
    // every user for the dropdown, not one 25-row page (users_pagination_
    // prompt.md added paging to the default GET /api/admin/users call).
    api.admin
      .users({ page_size: 1000 })
      .then((data) => setActorOptions(data.users.map((u) => ({ id: u.id, label: u.name || u.email }))))
      .catch(() => setActorOptions([]));
  }, []);

  return (
    <div className="max-w-3xl xl:max-w-5xl 2xl:max-w-6xl mx-auto px-8 py-8">
      <div className="text-[0.75rem] text-muted mb-2" dir="auto">
        {clientLabel || "Workspace"} <span className="text-faint">›</span> Organization admin
      </div>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">Audit log</h1>
          <p className="text-[0.82rem] text-muted mt-1">
            {total} event{total === 1 ? "" : "s"}
          </p>
        </div>
        <a
          href={exportUrl}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[0.82rem] text-ink hover:border-primary hover:text-primary transition"
        >
          <Download size={14} /> Export CSV
        </a>
      </div>

      {/* Filters toolbar */}
      <div className="flex items-center gap-2 mt-5 flex-wrap">
        <div className="relative flex-1 min-w-[180px] max-w-xs">
          <Search
            size={15}
            className="pointer-events-none absolute start-2.5 top-1/2 -translate-y-1/2 text-faint"
            aria-hidden
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by target"
            aria-label="Search audit events by target"
            className="w-full rounded-lg border border-line bg-surface ps-8 pe-3 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
          />
        </div>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          aria-label="Filter by category"
          className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
        <select
          value={actor}
          onChange={(e) => setActor(e.target.value)}
          aria-label="Filter by actor"
          className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
        >
          <option value="">All actors</option>
          {actorOptions.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </select>
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          aria-label="From date"
          className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
        />
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          aria-label="To date"
          className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
        />
        {filtering && (
          <button
            onClick={clearFilters}
            className="text-[0.78rem] font-medium text-primary hover:underline"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Table */}
      <div className="mt-4">
        <div className="rounded-xl border border-line bg-surface overflow-hidden">
          <span className="block h-[3px] w-full" style={{ background: CHART_PALETTE[0] }} aria-hidden />
          <div className="flex items-center gap-3 px-2 pt-2 pb-2 text-[0.68rem] font-semibold uppercase tracking-wide text-faint border-b border-line">
            <span className="w-28">When</span>
            <span className="w-7" aria-hidden />
            <span className="flex-1">Event</span>
            <span className="w-32">Category</span>
          </div>

          {loading ? (
            <SkeletonRows />
          ) : error ? (
            <div className="px-2 py-10 text-center text-sm text-muted">
              Couldn't load the audit log. Please try again.
            </div>
          ) : events.length === 0 ? (
            <div className="px-2 py-10 text-center text-sm text-muted">
              {filtering ? "No events match your filters." : "No admin activity yet."}
            </div>
          ) : (
            <div className="flex flex-col divide-y divide-lineSoft">
              {events.map((e) => (
                <EventRow key={e.id} event={e} onOpen={setSelected} />
              ))}
            </div>
          )}
        </div>

        {!loading && !error && (
          <Pager page={page} total={total} pageSize={pageSize} onPageChange={setPage} />
        )}
      </div>

      {selected && <AuditEventDrawer event={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
