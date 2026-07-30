import { useEffect, useState } from "react";
import { AlertTriangle, ChevronDown, Database, Flag, RefreshCw } from "lucide-react";
import { api, type DataSource, type DataSourceStatus } from "../../lib/api";
import { timeAgo } from "../../lib/time";
import { useToast } from "./toast-context";

const STATUS_STYLE: Record<DataSourceStatus, { bg: string; fg: string; label: string }> = {
  healthy: { bg: "#EAFBF4", fg: "#1B7A5E", label: "Healthy" },
  error: { bg: "#FEE2E2", fg: "#DC2626", label: "Error" },
  syncing: { bg: "#DBEAFE", fg: "#1D4ED8", label: "Syncing" },
  paused: { bg: "#F1F5F9", fg: "#64748B", label: "Paused" },
};

function StatusPill({ status }: { status: DataSourceStatus }) {
  const s = STATUS_STYLE[status];
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[0.72rem] font-semibold"
      style={{ background: s.bg, color: s.fg }}
    >
      {s.label}
    </span>
  );
}

function formatAge(days: number | null): string {
  if (days === null) return "Unknown";
  if (days < 1) return "Today";
  const whole = Math.floor(days);
  return `${whole} day${whole === 1 ? "" : "s"} ago`;
}

function SkeletonCard() {
  return (
    <div aria-busy="true" className="rounded-xl2 border border-line bg-surface p-5">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-surfaceAlt animate-pulse" />
        <div className="flex-1">
          <div className="w-32 h-3.5 rounded bg-surfaceAlt animate-pulse mb-2" />
          <div className="w-20 h-3 rounded bg-surfaceAlt animate-pulse" />
        </div>
      </div>
    </div>
  );
}

function SourceCard({ source }: { source: DataSource }) {
  const toast = useToast();
  const [expanded, setExpanded] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [reported, setReported] = useState(false);

  const submitReport = async () => {
    setReporting(true);
    try {
      await api.admin.dataSources.reportProblem(source.id);
      setConfirming(false);
      setReported(true);
    } catch {
      toast("Couldn't send the report. Please try again.");
    } finally {
      setReporting(false);
    }
  };

  const entityCount = source.entities.length;

  return (
    <div className="rounded-xl2 border border-line bg-surface p-5">
      <div className="flex items-start gap-3">
        <span className="shrink-0 inline-flex items-center justify-center w-9 h-9 rounded-lg bg-primary/10 text-primary">
          <Database size={18} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-ink">{source.display_name}</span>
            <StatusPill status={source.status} />
          </div>
          <p className="text-[0.75rem] text-muted mt-1">
            {entityCount} entit{entityCount === 1 ? "y" : "ies"} mapped
          </p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-[0.78rem]">
        <div>
          <div className="text-muted">Last checked</div>
          <div className="text-ink font-medium" dir="ltr">
            {source.status === "healthy" || source.status === "syncing"
              ? `${timeAgo(source.last_sync_at)}${
                  source.sync_duration_ms !== null ? ` (${source.sync_duration_ms}ms)` : ""
                }`
              : "Unavailable"}
          </div>
        </div>
        <div>
          <div className="text-muted">Data age</div>
          <div className="text-ink font-medium" dir="ltr">
            {formatAge(source.data_age_days)}
            {source.primary_date_field ? (
              <span className="text-faint"> · {source.primary_date_field}</span>
            ) : null}
          </div>
        </div>
      </div>

      {source.status === "error" && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-critical-fg/25 bg-critical-bg px-3 py-2 text-[0.78rem] text-critical-fg">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <span>This source isn't reachable right now. Questions touching its data will show a caveat.</span>
        </div>
      )}

      {entityCount > 0 && (
        <div className="mt-3 border-t border-lineSoft pt-3">
          <button
            onClick={() => setExpanded((e) => !e)}
            aria-expanded={expanded}
            className="flex items-center gap-1.5 text-[0.78rem] font-medium text-primary hover:underline"
          >
            <ChevronDown size={14} className={`transition-transform ${expanded ? "rotate-180" : ""}`} />
            {expanded ? "Hide" : "Show"} mapped entities
          </button>
          {expanded && (
            <div className="mt-2.5 flex flex-col gap-2">
              {source.entities.map((e) => (
                <div key={e.name} className="text-[0.78rem]" dir="ltr">
                  <span className="font-medium text-ink">{e.name}</span>
                  {e.dependent_metrics.length > 0 && (
                    <span className="text-muted">
                      {" "}
                      → {e.dependent_metrics.join(", ")} ← {source.display_name}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="mt-4 border-t border-lineSoft pt-3">
        {reported ? (
          <p className="text-[0.78rem] text-muted">Reported — the platform team has been notified.</p>
        ) : confirming ? (
          <div className="rounded-lg border border-lineSoft bg-warning-bg/40 px-3 py-2.5 text-[0.78rem] text-ink">
            Report a problem with {source.display_name}? The current status and data age will be
            attached automatically.
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                onClick={submitReport}
                disabled={reporting}
                className="rounded-lg bg-primary text-white text-[0.78rem] font-medium px-3 py-1.5 hover:bg-primary/90 disabled:opacity-60 transition"
              >
                {reporting ? "Sending…" : "Confirm"}
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={reporting}
                className="rounded-lg border border-line text-[0.78rem] text-muted px-3 py-1.5 hover:bg-surfaceAlt transition"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[0.78rem] text-ink hover:border-primary hover:text-primary transition"
          >
            <Flag size={13} /> Report a problem
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * The "Data sources" screen (spec §4): a view-only status card per connected
 * source. No credentials, no connection editing, no manual sync trigger --
 * those are platform-level (spec §4.3); this panel only shows status, data
 * age, and the source→entity→metric trust chain ("revenue, aov ← Postgres").
 */
export function DataSourcesScreen({ clientLabel }: { clientLabel: string }) {
  const [sources, setSources] = useState<DataSource[] | null>(null);
  const [error, setError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(false);
    api.admin.dataSources
      .list()
      .then((data) => !cancelled && setSources(data))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  return (
    <div className="max-w-4xl mx-auto px-8 py-8">
      <div className="text-[0.75rem] text-muted mb-2" dir="auto">
        {clientLabel || "Workspace"} <span className="text-faint">›</span> Organization admin
      </div>

      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">Data sources</h1>
          <p className="text-[0.82rem] text-muted mt-1">
            Where SEMA's data comes from, and how fresh it is. Read-only — connections are managed
            at the platform level.
          </p>
        </div>
        <button
          onClick={() => setReloadKey((k) => k + 1)}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[0.82rem] text-ink hover:border-primary hover:text-primary transition"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
        {error ? (
          <p className="text-sm text-muted py-8 text-center col-span-2">
            Couldn't load data sources. Please try again.
          </p>
        ) : !sources ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : sources.length === 0 ? (
          <p className="text-sm text-muted py-8 text-center col-span-2">No data sources configured.</p>
        ) : (
          sources.map((s) => <SourceCard key={s.id} source={s} />)
        )}
      </div>
    </div>
  );
}
