import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Search } from "lucide-react";
import { api, type AuditEvent } from "../../lib/api";
import { useAuditLog } from "../../hooks/useAuditLog";
import { initials, pastelFor } from "../../lib/avatar";
import { timeAgo } from "../../lib/time";
import { auditCategoryLabel, auditSentence, isImpersonationEvent } from "./auditSentences";
import { AuditEventDrawer } from "./AuditEventDrawer";

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
      <span className="shrink-0 inline-flex items-center rounded-full bg-surfaceAlt px-2 py-0.5 text-[0.68rem] font-medium text-muted">
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
    api.admin
      .users()
      .then((data) => setActorOptions(data.users.map((u) => ({ id: u.id, label: u.name || u.email }))))
      .catch(() => setActorOptions([]));
  }, []);

  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  const canPrev = page > 1;
  const canNext = to < total;

  return (
    <div className="max-w-5xl mx-auto px-8 py-8">
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
        <div className="flex items-center gap-3 px-2 pb-2 text-[0.68rem] font-semibold uppercase tracking-wide text-faint border-b border-line">
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

        {!loading && !error && total > 0 && (
          <div className="flex items-center justify-between mt-3">
            <p className="text-[0.75rem] text-muted">
              Showing {from}–{to} of {total}
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(page - 1)}
                disabled={!canPrev}
                aria-label="Previous page"
                className="w-7 h-7 flex items-center justify-center rounded-lg border border-line text-muted hover:text-ink hover:border-primary disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                <ChevronLeft size={14} />
              </button>
              <button
                onClick={() => setPage(page + 1)}
                disabled={!canNext}
                aria-label="Next page"
                className="w-7 h-7 flex items-center justify-center rounded-lg border border-line text-muted hover:text-ink hover:border-primary disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {selected && <AuditEventDrawer event={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
