import { useEffect, useMemo, useState } from "react";
import { Loader2, Pencil, Plus, Trash2, X } from "lucide-react";
import { useDismiss } from "../../hooks/useDismiss";
import { useUiLang } from "../../lib/useUiLang";
import { ALERT_BUILDER, DEFAULT_PARAMS, METRIC_LABEL_HE } from "../../lib/alertCopy";
import {
  api,
  ApiError,
  type AlertMetricCatalogItem,
  type AlertRuleInfo,
  type AlertTemplateCatalogItem,
  type AlertTemplateType,
  type AlertTestResult,
} from "../../lib/api";
import { useToast } from "./toast-context";

/** Template-based alert builder (alert_templates_prompt.md): replaces the
 * disabled "coming soon" popover from product_placeholders_prompt.md with a
 * real create/edit/delete flow. Org-owned alerts are fully editable here;
 * the remaining YAML/system alerts (that couldn't be expressed as a
 * template) are listed read-only with a "System" tag -- both kinds evaluate
 * through the same backend engine, this is purely a display split. */
export function AlertBuilder() {
  const lang = useUiLang();
  const t = ALERT_BUILDER[lang];
  const toast = useToast();
  const [rows, setRows] = useState<AlertRuleInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<AlertRuleInfo | "new" | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  // Only org-owned (editable) alerts render here -- the remaining system/
  // YAML alerts (not expressible as a template) already have their own
  // toggle+threshold cards in the accordion below this section; showing
  // them again here, read-only, would just be a confusing duplicate.
  const reload = () =>
    api.admin.alerts
      .list()
      .then((all) => setRows(all.filter((r) => !r.system)))
      .catch(() => setRows([]));

  useEffect(() => {
    reload().finally(() => setLoading(false));
  }, []);

  const onDelete = async (id: string) => {
    try {
      await api.admin.alerts.remove(id);
      setConfirmDeleteId(null);
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Couldn't delete this alert.");
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[0.78rem] font-medium text-ink">{t.heading}</span>
        <button
          type="button"
          onClick={() => setEditing("new")}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-[0.75rem] font-medium text-ink hover:border-primary hover:text-primary transition"
        >
          <Plus size={13} /> {t.newAlert}
        </button>
      </div>

      {loading ? (
        <Loader2 size={16} className="animate-spin text-muted" />
      ) : rows.length === 0 ? (
        <p className="text-[0.78rem] text-muted py-1">{t.noOrgAlerts}</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {rows.map((r) => (
            <div key={r.id} className="rounded-lg border border-line px-2.5 py-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-[0.82rem] text-ink">{r.name}</span>
                    {!r.enabled && (
                      <span className="shrink-0 rounded-full bg-surfaceAlt px-1.5 py-0.5 text-[0.62rem] font-medium text-faint">
                        {lang === "he" ? "מנוטרלת" : "Disabled"}
                      </span>
                    )}
                  </div>
                  <div className="text-[0.72rem] text-muted truncate">
                    {lang === "he" ? r.summary_he : r.summary_en}
                  </div>
                  {r.disabled_reason && (
                    <div className="text-[0.68rem] text-amber-600 mt-0.5">{t.disabledReason(r.disabled_reason)}</div>
                  )}
                </div>
                <div className="shrink-0 flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setEditing(r)}
                    aria-label={t.edit}
                    className="w-7 h-7 rounded-lg flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink transition"
                  >
                    <Pencil size={13} />
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmDeleteId(r.id)}
                    aria-label={t.delete}
                    className="w-7 h-7 rounded-lg flex items-center justify-center text-muted hover:bg-red-50 hover:text-red-600 transition"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
              {confirmDeleteId === r.id && (
                <div className="mt-1.5 flex items-center justify-end gap-2 border-t border-lineSoft pt-1.5">
                  <span className="text-[0.72rem] text-muted">{t.deleteConfirm}</span>
                  <button
                    type="button"
                    onClick={() => setConfirmDeleteId(null)}
                    className="text-[0.72rem] text-muted hover:text-ink"
                  >
                    {t.cancel}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(r.id)}
                    className="text-[0.72rem] font-medium text-red-600 hover:text-red-700"
                  >
                    {t.delete}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {editing !== null && (
        <AlertFormModal
          existing={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

function AlertFormModal({
  existing,
  onClose,
  onSaved,
}: {
  existing: AlertRuleInfo | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const lang = useUiLang();
  const t = ALERT_BUILDER[lang];
  const ref = useDismiss<HTMLDivElement>(true, onClose);

  const [templates, setTemplates] = useState<AlertTemplateCatalogItem[]>([]);
  const [metrics, setMetrics] = useState<AlertMetricCatalogItem[]>([]);
  const [name, setName] = useState(existing?.name ?? "");
  const [metric, setMetric] = useState(existing?.metric ?? "");
  const [template, setTemplate] = useState<AlertTemplateType | "">((existing?.template as AlertTemplateType) ?? "");
  const [params, setParams] = useState<Record<string, unknown>>(existing?.params ?? {});
  const [severity, setSeverity] = useState<"critical" | "warning">(existing?.severity ?? "warning");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<AlertTestResult | null>(null);
  const [testedKey, setTestedKey] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.admin.alerts.templates().then(setTemplates).catch(() => setTemplates([]));
    api.admin.alerts.metrics().then((list) => {
      setMetrics(list);
      if (!existing && !metric && list.length > 0) setMetric(list[0].metric);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const currentKey = useMemo(() => JSON.stringify({ metric, template, params }), [metric, template, params]);
  const isTested = testedKey === currentKey && testResult?.ok === true;

  const setTemplateAndDefaults = (tpl: AlertTemplateType) => {
    setTemplate(tpl);
    setParams(DEFAULT_PARAMS[tpl] ?? {});
    setTestResult(null);
    setTestedKey(null);
  };

  const updateParam = (key: string, value: unknown) => {
    setParams((p) => ({ ...p, [key]: value }));
    setTestResult(null);
    setTestedKey(null);
  };

  const runTest = async () => {
    if (!metric || !template) return;
    setTesting(true);
    setError(null);
    try {
      const result = await api.admin.alerts.test({ metric, template, params });
      setTestResult(result);
      setTestedKey(currentKey);
    } catch {
      setTestResult({ ok: false, fire_count: 0, fire_dates: [], error: t.testError });
      setTestedKey(currentKey);
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    if (!metric || !template || !name.trim() || !isTested) return;
    setSaving(true);
    setError(null);
    try {
      if (existing) {
        await api.admin.alerts.update(existing.id, { name, metric, template, params, severity });
      } else {
        await api.admin.alerts.create({ name, metric, template, params, severity });
      }
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't save this alert.");
    } finally {
      setSaving(false);
    }
  };

  const metricLabel = (m: string) => (lang === "he" ? METRIC_LABEL_HE[m] ?? m : metrics.find((x) => x.metric === m)?.label ?? m);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/25 animate-[sema-fade-in_0.2s_ease-out]" onClick={onClose} aria-hidden />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        className="relative w-full max-w-lg rounded-xl2 border border-line bg-surface shadow-pop p-5 max-h-[85vh] overflow-y-auto sema-scroll"
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <h2 className="text-base font-semibold text-ink">{existing ? t.edit : t.newAlert}</h2>
          <button onClick={onClose} aria-label={t.cancel} className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink transition">
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[0.75rem] text-muted">{t.fields.name}</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.85rem] text-ink outline-none focus:border-primary transition"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[0.75rem] text-muted">{t.fields.metric}</span>
            <select
              value={metric}
              onChange={(e) => {
                setMetric(e.target.value);
                setTestResult(null);
                setTestedKey(null);
              }}
              className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.85rem] text-ink outline-none focus:border-primary transition"
            >
              {metrics.map((m) => (
                <option key={m.metric} value={m.metric}>
                  {metricLabel(m.metric)}
                </option>
              ))}
            </select>
          </label>

          <div className="flex flex-col gap-1.5">
            <span className="text-[0.75rem] text-muted">{t.fields.templateType}</span>
            <div className="grid grid-cols-2 gap-2">
              {templates.map((tpl) => (
                <button
                  key={tpl.template}
                  type="button"
                  onClick={() => setTemplateAndDefaults(tpl.template)}
                  className={`text-start rounded-lg border px-2.5 py-2 transition ${
                    template === tpl.template ? "border-primary bg-primary/[0.04]" : "border-line hover:border-primary/50"
                  }`}
                >
                  <div className="text-[0.78rem] font-medium text-ink">{lang === "he" ? tpl.label_he : tpl.label}</div>
                  <div className="text-[0.68rem] text-muted leading-snug mt-0.5">
                    {lang === "he" ? tpl.description_he : tpl.description}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {template && (
            <ParamFields template={template} params={params} onChange={updateParam} lang={lang} />
          )}

          <label className="flex flex-col gap-1">
            <span className="text-[0.75rem] text-muted">{t.fields.severity}</span>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value as "critical" | "warning")}
              className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.85rem] text-ink outline-none focus:border-primary transition"
            >
              <option value="warning">{t.severity.warning}</option>
              <option value="critical">{t.severity.critical}</option>
            </select>
          </label>

          <button
            type="button"
            onClick={runTest}
            disabled={!metric || !template || testing}
            className="rounded-lg border border-line px-3 py-1.5 text-[0.8rem] font-medium text-ink hover:border-primary hover:text-primary disabled:opacity-50 transition self-start"
          >
            {testing ? t.testing : t.runTest}
          </button>

          {testResult && testedKey === currentKey && (
            <div
              className={`rounded-lg px-3 py-2 text-[0.78rem] ${
                !testResult.ok
                  ? "bg-red-50 text-red-700"
                  : testResult.fire_count > 0
                    ? "bg-emerald-50 text-emerald-700"
                    : "bg-amber-50 text-amber-700"
              }`}
            >
              {!testResult.ok ? testResult.error : testResult.fire_count > 0 ? t.testFiredPlural(testResult.fire_count) : t.testFiredZero}
            </div>
          )}

          {error && <p className="text-[0.78rem] text-red-600">{error}</p>}
          {!isTested && <p className="text-[0.7rem] text-faint">{t.saveBlocked}</p>}

          <div className="flex items-center justify-end gap-2 mt-1">
            <button type="button" onClick={onClose} className="text-[0.8rem] text-muted hover:text-ink px-2 py-1.5">
              {t.cancel}
            </button>
            <button
              type="button"
              onClick={save}
              disabled={!isTested || !name.trim() || saving}
              className="rounded-lg bg-primary px-4 py-1.5 text-[0.8rem] font-medium text-white hover:bg-primary/90 disabled:opacity-50 transition"
            >
              {t.save}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ParamFields({
  template,
  params,
  onChange,
  lang,
}: {
  template: AlertTemplateType;
  params: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  lang: "en" | "he";
}) {
  const t = ALERT_BUILDER[lang];
  const p = t.params;

  const selectClass =
    "rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.85rem] text-ink outline-none focus:border-primary transition";
  const numberClass = selectClass + " w-28";

  if (template === "pct_change") {
    return (
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1">
          <span className="text-[0.72rem] text-muted">{p.window}</span>
          <select value={String(params.window ?? "mom")} onChange={(e) => onChange("window", e.target.value)} className={selectClass}>
            <option value="dod">{p.windowOptions.dod}</option>
            <option value="wow">{p.windowOptions.wow}</option>
            <option value="mom">{p.windowOptions.mom}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[0.72rem] text-muted">{p.direction}</span>
          <select value={String(params.direction ?? "drop")} onChange={(e) => onChange("direction", e.target.value)} className={selectClass}>
            <option value="drop">{p.directionOptions.drop}</option>
            <option value="rise">{p.directionOptions.rise}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 col-span-2">
          <span className="text-[0.72rem] text-muted">{p.thresholdPct}</span>
          <input
            type="number"
            min={0.1}
            max={100}
            step={0.1}
            value={Number(params.threshold_pct ?? 10)}
            onChange={(e) => onChange("threshold_pct", Number(e.target.value))}
            className={numberClass}
          />
        </label>
      </div>
    );
  }

  if (template === "absolute_threshold") {
    return (
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1">
          <span className="text-[0.72rem] text-muted">{p.operator}</span>
          <select value={String(params.operator ?? "above")} onChange={(e) => onChange("operator", e.target.value)} className={selectClass}>
            <option value="above">{p.operatorOptions.above}</option>
            <option value="below">{p.operatorOptions.below}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[0.72rem] text-muted">{p.value}</span>
          <input
            type="number"
            value={Number(params.value ?? 0)}
            onChange={(e) => onChange("value", Number(e.target.value))}
            className={numberClass}
          />
        </label>
      </div>
    );
  }

  if (template === "anomaly") {
    return (
      <label className="flex flex-col gap-1 w-40">
        <span className="text-[0.72rem] text-muted">{p.nSigma}</span>
        <input
          type="number"
          min={0.5}
          max={10}
          step={0.5}
          value={Number(params.n_sigma ?? 2)}
          onChange={(e) => onChange("n_sigma", Number(e.target.value))}
          className={numberClass}
        />
      </label>
    );
  }

  // streak
  return (
    <div className="grid grid-cols-2 gap-2">
      <label className="flex flex-col gap-1">
        <span className="text-[0.72rem] text-muted">{p.nDays}</span>
        <input
          type="number"
          min={2}
          max={30}
          value={Number(params.n_days ?? 3)}
          onChange={(e) => onChange("n_days", Number(e.target.value))}
          className={numberClass}
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-[0.72rem] text-muted">{p.direction}</span>
        <select value={String(params.direction ?? "drop")} onChange={(e) => onChange("direction", e.target.value)} className={selectClass}>
          <option value="drop">{p.directionOptions.drop}</option>
          <option value="rise">{p.directionOptions.rise}</option>
        </select>
      </label>
    </div>
  );
}
