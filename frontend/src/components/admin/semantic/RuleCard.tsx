import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { ApiError, type SemanticRuleItem, type SemanticValidateResult } from "../../../lib/api";
import type { SemanticModelHook } from "../../../hooks/useSemanticModel";
import { ActionErrorBanner, ValidationBanner } from "./ValidationBanner";

const STATUS_STYLE: Record<string, string> = {
  certified: "bg-emerald-50 text-emerald-700",
  draft: "bg-warning-bg text-warning-fg",
  deprecated: "bg-surfaceAlt text-muted",
};

/**
 * One business rule, collapsed to a summary row or expanded into an inline
 * edit form (spec §6.4: "no separate page"). Same Discard/Run validation/
 * Publish shape as MetricEditor, over rule fields instead of metric fields.
 */
export function RuleCard({
  rule,
  expanded,
  onToggle,
  semantic,
}: {
  rule: SemanticRuleItem;
  expanded: boolean;
  onToggle: () => void;
  semantic: SemanticModelHook;
}) {
  const [definition, setDefinition] = useState(rule.definition);
  const [logic, setLogic] = useState(rule.logic ?? "");
  const [appliesToText, setAppliesToText] = useState(rule.applies_to.join(", "));
  const [status, setStatus] = useState(rule.status);
  const [busy, setBusy] = useState<"validate" | "publish" | "discard" | null>(null);
  const [result, setResult] = useState<SemanticValidateResult | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setDefinition(rule.definition);
    setLogic(rule.logic ?? "");
    setAppliesToText(rule.applies_to.join(", "));
    setStatus(rule.status);
    setResult(null);
    setActionError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rule.name]);

  const dirty =
    definition !== rule.definition ||
    (logic.trim() || null) !== (rule.logic ?? null) ||
    appliesToText.trim() !== rule.applies_to.join(", ") ||
    status !== rule.status;
  const canPublish = rule.is_draft && rule.validated && !dirty;
  const canDiscard = (dirty || rule.is_draft) && busy === null;

  const runValidation = async () => {
    if (!definition.trim()) {
      setActionError("Definition is required.");
      return;
    }
    setBusy("validate");
    setActionError(null);
    const appliesTo = appliesToText.split(",").map((s) => s.trim()).filter(Boolean);
    try {
      // Preserve "create" for a not-yet-published new rule -- defaulting to
      // "edit" here would silently overwrite that action and make the item
      // vanish from the merged view (nothing published to overlay it onto).
      await semantic.saveDraft(
        "rule", rule.name,
        { definition, logic: logic.trim() || null, applies_to: appliesTo, status },
        rule.is_new ? "create" : "edit",
      );
      setResult(await semantic.validateDraft("rule", rule.name));
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : "Couldn't save or validate this rule.");
    } finally {
      setBusy(null);
    }
  };

  const publish = async () => {
    setBusy("publish");
    setActionError(null);
    try {
      await semantic.publishDraft("rule", rule.name);
      setResult(null);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : "Couldn't publish this rule.");
    } finally {
      setBusy(null);
    }
  };

  const discard = async () => {
    if (!rule.is_draft) {
      setDefinition(rule.definition);
      setLogic(rule.logic ?? "");
      setAppliesToText(rule.applies_to.join(", "));
      setStatus(rule.status);
      setResult(null);
      setActionError(null);
      return;
    }
    setBusy("discard");
    setActionError(null);
    try {
      await semantic.discardDraft("rule", rule.name);
      setResult(null);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : "Couldn't discard this rule.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="rounded-xl2 border border-line bg-surface overflow-hidden">
      <button
        onClick={onToggle}
        aria-expanded={expanded}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-start hover:bg-surfaceAlt/60 transition"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {rule.is_draft && (
              <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-primary" title="Has unpublished draft" />
            )}
            <span className="font-medium text-ink truncate">{rule.name}</span>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-[0.66rem] font-semibold ${STATUS_STYLE[rule.status] ?? ""}`}>
              {rule.status}
            </span>
          </div>
          {!expanded && <p className="text-[0.8rem] text-muted mt-1 truncate">{rule.definition}</p>}
        </div>
        {expanded ? (
          <ChevronUp size={16} className="shrink-0 text-muted" />
        ) : (
          <ChevronDown size={16} className="shrink-0 text-muted" />
        )}
      </button>

      {!expanded && (
        <div className="px-4 pb-3 -mt-1">
          {rule.logic && (
            <code className="sema-code-inline block w-fit mb-1.5 max-w-full truncate" dir="ltr">
              {rule.logic}
            </code>
          )}
          <p className="text-[0.72rem] text-muted">
            Applies to: {rule.applies_to.length ? rule.applies_to.join(", ") : "—"} · cited in answers
            as an assumption
          </p>
        </div>
      )}

      {expanded && (
        <div className="px-4 pb-4 pt-1 border-t border-lineSoft">
          <label className="block text-[0.78rem] font-medium text-ink mt-3 mb-1" htmlFor={`rule-def-${rule.name}`}>
            Definition (plain language)
          </label>
          <textarea
            id={`rule-def-${rule.name}`}
            value={definition}
            onChange={(e) => setDefinition(e.target.value)}
            rows={2}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[0.85rem] text-ink outline-none focus:border-primary transition resize-y"
          />

          <label className="block text-[0.78rem] font-medium text-ink mt-3 mb-1" htmlFor={`rule-logic-${rule.name}`}>
            Logic (SQL, optional)
          </label>
          <textarea
            id={`rule-logic-${rule.name}`}
            value={logic}
            onChange={(e) => setLogic(e.target.value)}
            dir="ltr"
            rows={3}
            spellCheck={false}
            style={{ unicodeBidi: "isolate" }}
            className="sema-code w-full text-[0.78rem] outline-none focus:border-primary transition resize-y"
          />

          <div className="flex items-start gap-3 mt-3">
            <div className="flex-1 min-w-0">
              <label className="block text-[0.78rem] font-medium text-ink mb-1" htmlFor={`rule-applies-${rule.name}`}>
                Applies to (metric names)
              </label>
              <input
                id={`rule-applies-${rule.name}`}
                type="text"
                value={appliesToText}
                onChange={(e) => setAppliesToText(e.target.value)}
                placeholder="comma-separated, e.g. vip_customers, churn_risk"
                className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
              />
            </div>
            <div className="w-32 shrink-0">
              <label className="block text-[0.78rem] font-medium text-ink mb-1" htmlFor={`rule-status-${rule.name}`}>
                Status
              </label>
              <select
                id={`rule-status-${rule.name}`}
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

          {result && <ValidationBanner result={result} />}
          {actionError && <ActionErrorBanner text={actionError} />}

          <div className="flex items-center justify-end gap-2 mt-4">
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
      )}
    </div>
  );
}
