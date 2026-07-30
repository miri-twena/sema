import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ChevronDown, Database, Flag, Plus, RefreshCw, Upload } from "lucide-react";
import { api, ApiError, type DataSource, type DataSourceStatus } from "../../lib/api";
import { timeAgo } from "../../lib/time";
import { useUiLang } from "../../lib/useUiLang";
import { DATA_SOURCE_GALLERY } from "../../lib/placeholderCopy";
import { AddDataSourceModal } from "./AddDataSourceModal";
import { useToast } from "./toast-context";

const REQUEST_STEPS = ["requested", "configuring", "testing", "active"] as const;
const REQUEST_STEP_LABEL: Record<(typeof REQUEST_STEPS)[number], string> = {
  requested: "Requested", configuring: "Configuring", testing: "Testing", active: "Active",
};

function RequestProgressRail({ step }: { step: DataSource["progress_step"] }) {
  if (step === "rejected") {
    return (
      <p className="mt-3 text-[0.78rem] text-critical-fg" dir="auto">
        This request was declined by the platform team.
      </p>
    );
  }
  const activeIndex = REQUEST_STEPS.indexOf((step ?? "requested") as (typeof REQUEST_STEPS)[number]);
  return (
    <div className="mt-3 flex items-center gap-1.5" dir="ltr">
      {REQUEST_STEPS.map((s, i) => (
        <div key={s} className="flex items-center gap-1.5 flex-1">
          <div className="flex flex-col items-center gap-1 flex-1">
            <span
              className={`w-full h-1.5 rounded-full ${i <= activeIndex ? "bg-primary" : "bg-lineSoft"}`}
              aria-hidden
            />
            <span className={`text-[0.65rem] ${i <= activeIndex ? "text-ink font-medium" : "text-faint"}`}>
              {REQUEST_STEP_LABEL[s]}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

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

function SourceCard({ source, onChanged }: { source: DataSource; onChanged: () => void }) {
  const toast = useToast();
  const [expanded, setExpanded] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [reported, setReported] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const replaceFile = async (file: File) => {
    setReplacing(true);
    try {
      await api.admin.dataSources.replaceUpload(source.id, file);
      toast(`${file.name} uploaded — the table has been refreshed.`);
      onChanged();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Couldn't replace the file. Try again.");
    } finally {
      setReplacing(false);
    }
  };

  const entityCount = source.entities.length;
  const isRequest = source.origin === "request";

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
            {source.fingerprint && (
              <span className="text-[0.7rem] text-faint" dir="ltr">•••• {source.fingerprint}</span>
            )}
          </div>
          {!isRequest && (
            <p className="text-[0.75rem] text-muted mt-1">
              {entityCount} entit{entityCount === 1 ? "y" : "ies"} mapped
            </p>
          )}
        </div>
      </div>

      {isRequest ? (
        <RequestProgressRail step={source.progress_step} />
      ) : (
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
      )}

      {!isRequest && source.status === "error" && (
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

      {!isRequest && (
        <div className="mt-4 border-t border-lineSoft pt-3 flex flex-wrap items-center gap-2">
          {source.origin === "upload" && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void replaceFile(file);
                }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={replacing}
                className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[0.78rem] text-ink hover:border-primary hover:text-primary disabled:opacity-60 transition"
              >
                <Upload size={13} /> {replacing ? "Uploading…" : "Replace file"}
              </button>
            </>
          )}

          {reported ? (
            <p className="text-[0.78rem] text-muted">Reported — the platform team has been notified.</p>
          ) : confirming ? (
            <div className="w-full rounded-lg border border-lineSoft bg-warning-bg/40 px-3 py-2.5 text-[0.78rem] text-ink">
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
      )}
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
  const [galleryOpen, setGalleryOpen] = useState(false);
  const lang = useUiLang();

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
        <div className="shrink-0 flex items-center gap-2">
          <button
            onClick={() => setGalleryOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-[0.82rem] font-medium text-white hover:bg-primary/90 transition"
          >
            <Plus size={14} /> {DATA_SOURCE_GALLERY[lang].addButton}
          </button>
          <button
            onClick={() => setReloadKey((k) => k + 1)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[0.82rem] text-ink hover:border-primary hover:text-primary transition"
          >
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
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
          sources.map((s) => (
            <SourceCard key={s.id} source={s} onChanged={() => setReloadKey((k) => k + 1)} />
          ))
        )}
      </div>

      {galleryOpen && (
        <AddDataSourceModal
          onClose={() => setGalleryOpen(false)}
          onChanged={() => setReloadKey((k) => k + 1)}
        />
      )}
    </div>
  );
}
