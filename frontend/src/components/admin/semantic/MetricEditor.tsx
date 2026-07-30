import { useEffect, useState } from "react";
import {
  ApiError,
  type SemanticFormat,
  type SemanticMetricItem,
  type SemanticValidateResult,
} from "../../../lib/api";
import type { SemanticModelHook } from "../../../hooks/useSemanticModel";
import { ActionErrorBanner, ValidationBanner } from "./ValidationBanner";

const STATUS_LABEL: Record<string, string> = {
  certified: "Certified",
  draft: "Draft",
  deprecated: "Deprecated",
};

/**
 * One metric's editor (spec §6.4 mockup): business definition, SQL (mono,
 * LTR-isolated), format, synonyms, status, and the Discard/Run validation/
 * Publish actions. "Run validation" saves the current form as a draft, then
 * dry-runs it; "Publish" only re-uses that already-saved, already-validated
 * draft -- it never re-saves, so `dirty` (local edits since the last save)
 * gates Publish even when the server's `validated` flag is stale True.
 */
export function MetricEditor({
  metric,
  semantic,
}: {
  metric: SemanticMetricItem;
  semantic: SemanticModelHook;
}) {
  const [description, setDescription] = useState(metric.description);
  const [sql, setSql] = useState(metric.sql);
  const [format, setFormat] = useState<SemanticFormat | "">(metric.format ?? "");
  const [synonymsText, setSynonymsText] = useState(metric.synonyms.join(", "));
  const [status, setStatus] = useState(metric.status);
  const [busy, setBusy] = useState<"validate" | "publish" | "discard" | null>(null);
  const [result, setResult] = useState<SemanticValidateResult | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Resync local form state when a DIFFERENT metric is selected (the parent
  // remounts via key={metric.name} on selection change, but this also covers
  // the case where the model reloads with fresh published content).
  useEffect(() => {
    setDescription(metric.description);
    setSql(metric.sql);
    setFormat(metric.format ?? "");
    setSynonymsText(metric.synonyms.join(", "));
    setStatus(metric.status);
    setResult(null);
    setActionError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metric.name]);

  const dirty =
    description !== metric.description ||
    sql !== metric.sql ||
    (format || null) !== metric.format ||
    synonymsText.trim() !== metric.synonyms.join(", ") ||
    status !== metric.status;

  const runValidation = async () => {
    setBusy("validate");
    setActionError(null);
    const synonyms = synonymsText.split(",").map((s) => s.trim()).filter(Boolean);
    try {
      await semantic.saveDraft("metric", metric.name, { description, sql, format: format || null, synonyms, status });
      setResult(await semantic.validateDraft("metric", metric.name));
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : "Couldn't save or validate this draft.");
    } finally {
      setBusy(null);
    }
  };

  const publish = async () => {
    setBusy("publish");
    setActionError(null);
    try {
      await semantic.publishDraft("metric", metric.name);
      setResult(null);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : "Couldn't publish this draft.");
    } finally {
      setBusy(null);
    }
  };

  const discard = async () => {
    if (!metric.is_draft) {
      // No server draft yet -- just revert unsaved local typing.
      setDescription(metric.description);
      setSql(metric.sql);
      setFormat(metric.format ?? "");
      setSynonymsText(metric.synonyms.join(", "));
      setStatus(metric.status);
      setResult(null);
      setActionError(null);
      return;
    }
    setBusy("discard");
    setActionError(null);
    try {
      await semantic.discardDraft("metric", metric.name);
      setResult(null);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : "Couldn't discard this draft.");
    } finally {
      setBusy(null);
    }
  };

  // Publish only reuses the already-saved draft -- if the form has unsaved
  // edits since the last validate-triggered save, the server's `validated`
  // flag no longer describes what's on screen, so Publish stays disabled
  // until the admin re-validates.
  const canPublish = metric.is_draft && metric.validated && !dirty;
  const canDiscard = (dirty || metric.is_draft) && busy === null;

  return (
    <div className="rounded-xl2 border border-line bg-surface p-5">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-base font-semibold text-ink">{metric.label}</h2>
          <p className="text-[0.72rem] text-muted mt-0.5">
            v{metric.is_draft ? "current + unpublished draft" : "published"}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[0.68rem] font-semibold ${
            status === "certified"
              ? "bg-emerald-50 text-emerald-700"
              : status === "deprecated"
                ? "bg-surfaceAlt text-muted"
                : "bg-warning-bg text-warning-fg"
          }`}
        >
          {STATUS_LABEL[status] ?? status}
        </span>
      </div>

      <label className="block text-[0.78rem] font-medium text-ink mb-1" htmlFor="metric-description">
        Business definition
      </label>
      <textarea
        id="metric-description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={3}
        className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[0.85rem] text-ink outline-none focus:border-primary transition resize-y"
      />

      <label className="block text-[0.78rem] font-medium text-ink mt-3 mb-1" htmlFor="metric-sql">
        SQL expression
      </label>
      <textarea
        id="metric-sql"
        value={sql}
        onChange={(e) => setSql(e.target.value)}
        dir="ltr"
        rows={6}
        spellCheck={false}
        style={{ unicodeBidi: "isolate" }}
        className="sema-code w-full text-[0.78rem] outline-none focus:border-primary transition resize-y"
      />

      <div className="flex items-start gap-3 mt-3">
        <div className="w-32 shrink-0">
          <label className="block text-[0.78rem] font-medium text-ink mb-1" htmlFor="metric-format">
            Format
          </label>
          <select
            id="metric-format"
            value={format}
            onChange={(e) => setFormat(e.target.value as SemanticFormat | "")}
            className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
          >
            <option value="">Not set</option>
            <option value="currency">Currency</option>
            <option value="number">Number</option>
            <option value="percent">Percent</option>
            <option value="text">Text</option>
          </select>
        </div>
        <div className="flex-1 min-w-0">
          <label className="block text-[0.78rem] font-medium text-ink mb-1" htmlFor="metric-synonyms">
            Synonyms
          </label>
          <input
            id="metric-synonyms"
            type="text"
            value={synonymsText}
            onChange={(e) => setSynonymsText(e.target.value)}
            placeholder="comma-separated, e.g. average order size, basket value"
            dir="auto"
            className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
          />
        </div>
        <div className="w-32 shrink-0">
          <label className="block text-[0.78rem] font-medium text-ink mb-1" htmlFor="metric-status">
            Status
          </label>
          <select
            id="metric-status"
            value={status}
            onChange={(e) => setStatus(e.target.value as typeof status)}
            className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
          >
            <option value="certified">Certified</option>
            <option value="draft">Draft</option>
            <option value="deprecated">Deprecated</option>
          </select>
        </div>
      </div>

      {result && <ValidationBanner result={result} format={format || null} />}
      {actionError && <ActionErrorBanner text={actionError} />}

      <div className="flex items-center justify-between gap-2 mt-4">
        <p className="text-[0.72rem] text-muted">
          {dirty ? "Unsaved changes" : metric.is_draft ? "Edited, not yet published" : "No pending changes"}
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={discard}
            disabled={!canDiscard}
            className="rounded-xl border border-line px-3.5 py-2 text-sm text-muted hover:text-ink hover:bg-surfaceAlt disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {busy === "discard" ? "Discarding…" : "Discard"}
          </button>
          <button
            onClick={runValidation}
            disabled={busy !== null}
            className="rounded-xl border border-line px-3.5 py-2 text-sm text-ink hover:bg-surfaceAlt disabled:opacity-60 transition"
          >
            {busy === "validate" ? "Validating…" : "Run validation"}
          </button>
          <button
            onClick={publish}
            disabled={!canPublish || busy !== null}
            title={!canPublish ? "Run validation on this draft first." : undefined}
            className="rounded-xl bg-primary text-white text-sm font-medium px-4 py-2 shadow-bubble hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {busy === "publish" ? "Publishing…" : "Publish"}
          </button>
        </div>
      </div>
    </div>
  );
}
