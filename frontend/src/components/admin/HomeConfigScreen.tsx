import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Eye, Plus, RotateCcw, TrendingUp, Trash2, X } from "lucide-react";
import {
  api,
  type AlertCatalogItem,
  type HomeConfig,
  type HomeConfigKpiId,
  type HomeSensitivity,
} from "../../lib/api";
import { useHomeConfig } from "../../hooks/useHomeConfig";
import { AccordionSection } from "./AccordionSection";
import { HomeDashboard } from "../HomeDashboard";
import { timeAgo } from "../../lib/time";
import { AlertBuilder } from "./AlertBuilder";

const KPI_LABELS: Record<HomeConfigKpiId, string> = {
  revenue: "Revenue",
  orders: "Orders",
  aov: "AOV",
  churn_risk: "At-Risk Customers",
};
const KPI_SUPPORTS_DELTA: Record<HomeConfigKpiId, boolean> = {
  revenue: true,
  orders: true,
  aov: true,
  churn_risk: false,
};
const ALL_KPI_IDS: HomeConfigKpiId[] = ["revenue", "orders", "aov", "churn_risk"];

const SENSITIVITY_OPTIONS: { id: HomeSensitivity; label: string; hint: string }[] = [
  { id: "conservative", label: "Conservative", hint: "Fewer cards -- only major moves" },
  { id: "balanced", label: "Balanced", hint: "The default threshold" },
  { id: "sensitive", label: "Sensitive", hint: "Surfaces smaller moves too" },
];

const PERIOD_OPTIONS: { months: 1 | 3 | 6 | 12; label: string }[] = [
  { months: 1, label: "Last month" },
  { months: 3, label: "Last 3 months" },
  { months: 6, label: "Last 6 months" },
  { months: 12, label: "Last 12 months" },
];

type Updater = (patch: Partial<HomeConfig> | ((prev: HomeConfig) => HomeConfig)) => void;
type Section = "brief" | "overview" | "questions" | "alerts";

const PREVIEW_ANCHOR: Record<Section, string> = {
  brief: "home-preview-daily-brief",
  overview: "home-preview-overview",
  questions: "home-preview-questions",
  alerts: "home-preview-alerts",
};

function StatusChip({
  hasDraft,
  publishedAt,
  version,
}: {
  hasDraft: boolean;
  publishedAt: string | null;
  version: number;
}) {
  if (hasDraft) {
    return (
      <span className="inline-flex items-center rounded-full bg-warning-bg px-2.5 py-1 text-[0.72rem] font-semibold text-warning-fg">
        Draft · not published
      </span>
    );
  }
  if (!publishedAt) {
    return (
      <span className="inline-flex items-center rounded-full bg-surfaceAlt px-2.5 py-1 text-[0.72rem] font-medium text-muted">
        Never published
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-mint/25 px-2.5 py-1 text-[0.72rem] font-semibold text-ink">
      Published {timeAgo(publishedAt)} · v{version}
    </span>
  );
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-center gap-2.5 py-1.5 cursor-pointer select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-4 h-4 rounded border-line accent-primary"
      />
      <span className="text-[0.82rem] text-ink">{label}</span>
    </label>
  );
}

function DailyBriefAccordion({ config, update }: { config: HomeConfig; update: Updater }) {
  return (
    <div className="flex flex-col gap-1">
      <Toggle
        checked={config.daily_brief.pulse_enabled}
        onChange={(v) => update((p) => ({ ...p, daily_brief: { ...p.daily_brief, pulse_enabled: v } }))}
        label="Show the pulse strip (yesterday's revenue/orders/conversion)"
      />
      <Toggle
        checked={config.daily_brief.insights_enabled}
        onChange={(v) => update((p) => ({ ...p, daily_brief: { ...p.daily_brief, insights_enabled: v } }))}
        label="Show insight cards (anomalies, pacing, VIP churn, ...)"
      />
      <div className="mt-3">
        <div className="text-[0.72rem] font-semibold uppercase tracking-wide text-faint mb-1.5">
          Insight sensitivity
        </div>
        <div className="flex flex-col gap-1.5">
          {SENSITIVITY_OPTIONS.map((opt) => (
            <label key={opt.id} className="flex items-start gap-2.5 py-1 cursor-pointer">
              <input
                type="radio"
                name="sensitivity"
                checked={config.daily_brief.sensitivity === opt.id}
                onChange={() => update((p) => ({ ...p, daily_brief: { ...p.daily_brief, sensitivity: opt.id } }))}
                className="mt-0.5 accent-primary"
              />
              <span>
                <span className="block text-[0.82rem] text-ink">{opt.label}</span>
                <span className="block text-[0.72rem] text-muted">{opt.hint}</span>
              </span>
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}

function OverviewAccordion({ config, update }: { config: HomeConfig; update: Updater }) {
  const order = config.kpis.order;
  const included = order.filter((id) => ALL_KPI_IDS.includes(id));
  const excluded = ALL_KPI_IDS.filter((id) => !included.includes(id));

  const toggle = (id: HomeConfigKpiId) =>
    update((p) => {
      const has = p.kpis.order.includes(id);
      return { ...p, kpis: { ...p.kpis, order: has ? p.kpis.order.filter((x) => x !== id) : [...p.kpis.order, id] } };
    });

  const move = (id: HomeConfigKpiId, dir: -1 | 1) =>
    update((p) => {
      const idx = p.kpis.order.indexOf(id);
      const swapWith = idx + dir;
      if (idx < 0 || swapWith < 0 || swapWith >= p.kpis.order.length) return p;
      const next = [...p.kpis.order];
      [next[idx], next[swapWith]] = [next[swapWith], next[idx]];
      return { ...p, kpis: { ...p.kpis, order: next } };
    });

  const setDelta = (id: HomeConfigKpiId, v: boolean) =>
    update((p) => ({ ...p, kpis: { ...p.kpis, deltas: { ...p.kpis.deltas, [id]: v } } }));

  return (
    <div>
      <div className="text-[0.72rem] font-semibold uppercase tracking-wide text-faint mb-1.5">
        KPIs, in order
      </div>
      <div className="flex flex-col gap-1.5">
        {included.map((id, i) => (
          <div key={id} className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-2">
            <div className="flex flex-col shrink-0">
              <button
                type="button"
                onClick={() => move(id, -1)}
                disabled={i === 0}
                aria-label={`Move ${KPI_LABELS[id]} up`}
                className="text-faint hover:text-ink disabled:opacity-30 disabled:cursor-not-allowed transition"
              >
                <ArrowUp size={13} />
              </button>
              <button
                type="button"
                onClick={() => move(id, 1)}
                disabled={i === included.length - 1}
                aria-label={`Move ${KPI_LABELS[id]} down`}
                className="text-faint hover:text-ink disabled:opacity-30 disabled:cursor-not-allowed transition"
              >
                <ArrowDown size={13} />
              </button>
            </div>
            <span className="flex-1 text-[0.82rem] text-ink">{KPI_LABELS[id]}</span>
            {KPI_SUPPORTS_DELTA[id] && (
              <label className="flex items-center gap-1.5 text-[0.72rem] text-muted cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.kpis.deltas[id] ?? true}
                  onChange={(e) => setDelta(id, e.target.checked)}
                  className="accent-primary"
                />
                Delta
              </label>
            )}
            <button
              type="button"
              onClick={() => toggle(id)}
              aria-label={`Remove ${KPI_LABELS[id]}`}
              className="text-faint hover:text-critical-fg transition"
            >
              <X size={14} />
            </button>
          </div>
        ))}
        {included.length === 0 && (
          <p className="text-[0.78rem] text-muted py-2">No KPIs selected -- add at least one below.</p>
        )}
      </div>

      {excluded.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {excluded.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => toggle(id)}
              className="inline-flex items-center gap-1 rounded-full border border-dashed border-line px-2.5 py-1 text-[0.75rem] text-muted hover:text-primary hover:border-primary transition"
            >
              <Plus size={12} /> {KPI_LABELS[id]}
            </button>
          ))}
        </div>
      )}

      <div className="mt-4">
        <div className="text-[0.72rem] font-semibold uppercase tracking-wide text-faint mb-1.5">
          Default period
        </div>
        <select
          value={config.default_period_months}
          onChange={(e) =>
            update({ default_period_months: Number(e.target.value) as HomeConfig["default_period_months"] })
          }
          className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
        >
          {PERIOD_OPTIONS.map((opt) => (
            <option key={opt.months} value={opt.months}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

/** Minimal, client-side "does this look answerable" heuristic (spec item 11)
 * -- NOT an agent call (that would make every keystroke a paid LLM round
 * trip); a soft nudge shown at save time, not a hard block. Mirrors
 * useChat.ts's own bilingual execution-keyword backstop for follow-up
 * suggestions: flag a question that reads like an instruction/action rather
 * than something SEMA can query data for. */
const _ACTION_WORDS = [
  "send", "launch", "create a campaign", "email", "call", "contact", "recommend a", "suggest a",
  "שלח", "צור קמפיין", "המלץ", "תתקשר",
];
function looksUnanswerable(q: string): boolean {
  const lower = q.trim().toLowerCase();
  if (lower.length < 6) return true;
  return _ACTION_WORDS.some((w) => lower.includes(w));
}

function SuggestedQuestionsAccordion({ config, update }: { config: HomeConfig; update: Updater }) {
  const questions = config.suggested_questions.questions;
  const [draftQuestion, setDraftQuestion] = useState("");

  const setQuestions = (next: string[]) =>
    update((p) => ({ ...p, suggested_questions: { ...p.suggested_questions, questions: next } }));

  const add = () => {
    const q = draftQuestion.trim();
    if (!q || questions.length >= 6) return;
    setQuestions([...questions, q]);
    setDraftQuestion("");
  };

  return (
    <div>
      <p className="text-[0.75rem] text-muted mb-2">
        Replaces the default starter questions on the home screen. Leave empty to keep the defaults.
      </p>
      <div className="flex flex-col gap-1.5">
        {questions.map((q, i) => (
          <div key={i} className="flex items-start gap-2 rounded-lg border border-line px-2.5 py-2">
            <span className="flex-1 text-[0.82rem] text-ink" dir="auto">
              {q}
            </span>
            {looksUnanswerable(q) && (
              <span
                className="shrink-0 text-[0.68rem] text-warning-fg font-medium"
                title="This may not be a data question SEMA can answer -- double-check before publishing."
              >
                ⚠ check
              </span>
            )}
            <button
              type="button"
              onClick={() => setQuestions(questions.filter((_, idx) => idx !== i))}
              aria-label={`Remove "${q}"`}
              className="shrink-0 text-faint hover:text-critical-fg transition"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
      {questions.length < 6 && (
        <div className="flex items-center gap-2 mt-2">
          <input
            type="text"
            value={draftQuestion}
            onChange={(e) => setDraftQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="Add a suggested question"
            dir="auto"
            className="flex-1 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
          />
          <button
            type="button"
            onClick={add}
            disabled={!draftQuestion.trim()}
            className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1.5 text-[0.8rem] text-ink hover:bg-surfaceAlt disabled:opacity-50 transition"
          >
            <Plus size={13} /> Add
          </button>
        </div>
      )}
      <div className="mt-3 pt-3 border-t border-lineSoft">
        <Toggle
          checked={config.suggested_questions.trending_enabled}
          onChange={(v) =>
            update((p) => ({ ...p, suggested_questions: { ...p.suggested_questions, trending_enabled: v } }))
          }
          label="Show trending questions from colleagues"
        />
      </div>
    </div>
  );
}

function AlertsAccordion({
  config,
  update,
  catalog,
}: {
  config: HomeConfig;
  update: Updater;
  catalog: AlertCatalogItem[];
}) {
  const setAlert = (id: string, patch: Partial<{ enabled: boolean; threshold: number | null }>) =>
    update((p) => {
      const current = p.alerts[id] ?? { enabled: true, threshold: null };
      return { ...p, alerts: { ...p.alerts, [id]: { ...current, ...patch } } };
    });

  return (
    <div className="flex flex-col gap-2">
      {catalog.length === 0 && (
        <p className="text-[0.78rem] text-muted py-2">No alerts are defined for this business yet.</p>
      )}
      {catalog.map((a) => {
        const cfg = config.alerts[a.id] ?? { enabled: true, threshold: null };
        return (
          <div key={a.id} className="rounded-lg border border-line px-2.5 py-2">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-[0.82rem] text-ink truncate">{a.label}</div>
                <div className="text-[0.7rem] text-muted truncate">{a.metric_label}</div>
              </div>
              <label className="shrink-0 flex items-center gap-1.5 text-[0.75rem] text-muted cursor-pointer">
                <input
                  type="checkbox"
                  checked={cfg.enabled}
                  onChange={(e) => setAlert(a.id, { enabled: e.target.checked })}
                  className="w-4 h-4 rounded border-line accent-primary"
                />
                Enabled
              </label>
            </div>
            {cfg.enabled && (
              <div className="flex items-center gap-2 mt-1.5">
                <span className="text-[0.72rem] text-muted">Custom threshold</span>
                <input
                  type="number"
                  value={cfg.threshold ?? ""}
                  placeholder="default"
                  onChange={(e) =>
                    setAlert(a.id, { threshold: e.target.value === "" ? null : Number(e.target.value) })
                  }
                  className="w-24 rounded-lg border border-line bg-surface px-2 py-1 text-[0.78rem] text-ink outline-none focus:border-primary transition"
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** The "Home screen" editor (spec §1): a settings column of four accordions
 * + a live preview rendering the REAL HomeDashboard component read-only
 * against the draft config. Opening an accordion scrolls/highlights the
 * matching preview region. */
export function HomeConfigScreen({ clientLabel }: { clientLabel: string }) {
  const {
    draft,
    update,
    version,
    publishedAt,
    warnings,
    loading,
    saving,
    hasDraft,
    publish,
    publishing,
    publishErrors,
    revert,
    preview,
    previewLoading,
  } = useHomeConfig();

  const [openSection, setOpenSection] = useState<Section>("overview");
  const [alertsCatalog, setAlertsCatalog] = useState<AlertCatalogItem[]>([]);
  const [highlighted, setHighlighted] = useState<Section | null>(null);

  useEffect(() => {
    api.admin.alertsCatalog().then(setAlertsCatalog).catch(() => setAlertsCatalog([]));
  }, []);

  // Accordions are single-open; clicking the header (open or not) always
  // scrolls/highlights the matching preview region, per the spec.
  const openAndScroll = (id: Section) => {
    setOpenSection(id);
    document.getElementById(PREVIEW_ANCHOR[id])?.scrollIntoView({ behavior: "smooth", block: "start" });
    setHighlighted(id);
    window.setTimeout(() => setHighlighted((h) => (h === id ? null : h)), 1400);
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-8 py-8">
        <div className="h-8 w-64 rounded bg-surfaceAlt animate-pulse" />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-8 py-8">
      <div className="text-[0.75rem] text-muted mb-2" dir="auto">
        {clientLabel || "Workspace"} <span className="text-faint">›</span> Organization admin
      </div>

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-ink">Home screen</h1>
          <div className="flex items-center gap-2 mt-1.5">
            <StatusChip hasDraft={hasDraft} publishedAt={publishedAt} version={version} />
            {saving && <span className="text-[0.72rem] text-muted">Saving…</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={revert}
            disabled={!hasDraft}
            className="inline-flex items-center gap-1.5 rounded-xl border border-line px-3.5 py-2 text-sm font-medium text-ink hover:bg-surfaceAlt disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            <RotateCcw size={14} /> Revert
          </button>
          <button
            onClick={publish}
            disabled={!hasDraft || publishing}
            className="inline-flex items-center gap-1.5 rounded-xl bg-primary text-white text-sm font-medium px-4 py-2 shadow-bubble hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {publishing ? "Publishing…" : "Publish"}
          </button>
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="mt-4 rounded-xl bg-warning-bg px-3.5 py-2.5 text-[0.8rem] text-warning-fg">
          {warnings.map((w, i) => (
            <div key={i}>{w}</div>
          ))}
        </div>
      )}
      {publishErrors && (
        <div className="mt-4 rounded-xl bg-critical-bg px-3.5 py-2.5 text-[0.8rem] text-critical-fg">
          {publishErrors.map((e, i) => (
            <div key={i}>{e}</div>
          ))}
        </div>
      )}

      <div className="mt-6 flex items-start gap-6">
        {/* Settings column */}
        <div className="w-[380px] shrink-0 flex flex-col gap-3">
          <AccordionSection
            id="brief"
            title="Daily brief"
            subtitle="Layers and sensitivity"
            open={openSection === "brief"}
            onToggle={() => openAndScroll("brief")}
          >
            <DailyBriefAccordion config={draft} update={update} />
          </AccordionSection>

          <AccordionSection
            id="overview"
            title="Business overview"
            subtitle="KPIs, order, and period"
            open={openSection === "overview"}
            onToggle={() => openAndScroll("overview")}
          >
            <OverviewAccordion config={draft} update={update} />
          </AccordionSection>

          <AccordionSection
            id="questions"
            title="Suggested questions"
            subtitle="Starters and trending"
            open={openSection === "questions"}
            onToggle={() => openAndScroll("questions")}
          >
            <SuggestedQuestionsAccordion config={draft} update={update} />
          </AccordionSection>

          <AccordionSection
            id="alerts"
            title="Alerts"
            subtitle="Per-alert threshold"
            open={openSection === "alerts"}
            onToggle={() => openAndScroll("alerts")}
          >
            <AlertBuilder />
            <div className="my-3 border-t border-lineSoft" />
            <AlertsAccordion config={draft} update={update} catalog={alertsCatalog} />
            <p className="mt-3 text-[0.72rem] text-faint">Email / Slack delivery -- coming in a future release.</p>
          </AccordionSection>
        </div>

        {/* Live preview */}
        <div className="flex-1 min-w-0 rounded-xl border border-line bg-bg">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-line bg-surface rounded-t-xl">
            <Eye size={14} className="text-muted" />
            <span className="text-[0.75rem] font-semibold text-muted">Live preview</span>
            {previewLoading && <span className="text-[0.7rem] text-faint">Updating…</span>}
          </div>
          <div className="px-6 pb-6 max-h-[calc(100vh-220px)] overflow-y-auto sema-scroll">
            {preview ? (
              <div
                className={`transition-shadow rounded-xl ${
                  highlighted ? "ring-2 ring-primary ring-offset-2 ring-offset-bg" : ""
                }`}
              >
                <HomeDashboard
                  clientLabel={clientLabel}
                  suggested={preview.suggested_questions}
                  alerts={preview.alerts}
                  overview={preview.overview}
                  brief={preview.brief}
                  popularQuestions={preview.popular_questions}
                  dbConnected
                  agentConfigured
                  onPick={() => {}}
                />
              </div>
            ) : (
              <div className="py-16 text-center text-sm text-muted">
                <TrendingUp size={20} className="mx-auto mb-2 text-faint" />
                Loading preview…
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
