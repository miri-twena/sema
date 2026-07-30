import { useEffect, useState } from "react";
import { AlertCircle, CalendarClock, ChevronDown, ChevronUp, Lightbulb } from "lucide-react";
import { ApiError, type SemanticKnowledgeItem, type SemanticValidateResult } from "../../../lib/api";
import type { SemanticModelHook } from "../../../hooks/useSemanticModel";
import { ActionErrorBanner, ValidationBanner } from "./ValidationBanner";

const TYPE_ICON: Record<string, typeof CalendarClock> = {
  recurring_event: CalendarClock,
  incident: AlertCircle,
  note: Lightbulb,
};

const TYPE_LABEL: Record<string, string> = {
  recurring_event: "Recurring event",
  incident: "Incident",
  note: "Note",
};

function dateRangeLabel(item: SemanticKnowledgeItem): string {
  if (item.date_range?.start || item.date_range?.end) {
    return `${item.date_range.start ?? "?"} – ${item.date_range.end ?? "?"}`;
  }
  if (item.recurrence) return item.recurrence;
  return "No dates set";
}

function agentEffectNote(item: SemanticKnowledgeItem): string {
  if (item.type === "incident") {
    return "Adds a caveat to any answer whose period overlaps this incident.";
  }
  return "Surfaced to the agent as context; mentioned when relevant.";
}

/**
 * One calendar/knowledge item, collapsed to a summary row or expanded into an
 * inline edit form -- same shape as RuleCard.
 */
export function KnowledgeCard({
  item,
  expanded,
  onToggle,
  semantic,
}: {
  item: SemanticKnowledgeItem;
  expanded: boolean;
  onToggle: () => void;
  semantic: SemanticModelHook;
}) {
  const [type, setType] = useState(item.type);
  const [description, setDescription] = useState(item.description);
  const [start, setStart] = useState(item.date_range?.start ?? "");
  const [end, setEnd] = useState(item.date_range?.end ?? "");
  const [recurrence, setRecurrence] = useState(item.recurrence ?? "");
  const [affectsText, setAffectsText] = useState(item.affects.join(", "));
  const [busy, setBusy] = useState<"validate" | "publish" | "discard" | null>(null);
  const [result, setResult] = useState<SemanticValidateResult | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setType(item.type);
    setDescription(item.description);
    setStart(item.date_range?.start ?? "");
    setEnd(item.date_range?.end ?? "");
    setRecurrence(item.recurrence ?? "");
    setAffectsText(item.affects.join(", "));
    setResult(null);
    setActionError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.name]);

  const dirty =
    type !== item.type ||
    description !== item.description ||
    start !== (item.date_range?.start ?? "") ||
    end !== (item.date_range?.end ?? "") ||
    recurrence !== (item.recurrence ?? "") ||
    affectsText.trim() !== item.affects.join(", ");
  const canPublish = item.is_draft && item.validated && !dirty;
  const canDiscard = (dirty || item.is_draft) && busy === null;

  const buildData = () => {
    const affects = affectsText.split(",").map((s) => s.trim()).filter(Boolean);
    const hasDateRange = start.trim() || end.trim();
    return {
      type,
      description,
      affects,
      date_range: hasDateRange ? { start: start.trim() || null, end: end.trim() || null } : null,
      recurrence: hasDateRange ? null : recurrence.trim() || null,
    };
  };

  const runValidation = async () => {
    if (!description.trim()) {
      setActionError("Description is required.");
      return;
    }
    setBusy("validate");
    setActionError(null);
    try {
      // Preserve "create" for a not-yet-published new item -- see RuleCard's
      // identical comment for why defaulting to "edit" here would be a bug.
      await semantic.saveDraft("knowledge", item.name, buildData(), item.is_new ? "create" : "edit");
      setResult(await semantic.validateDraft("knowledge", item.name));
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : "Couldn't save or validate this item.");
    } finally {
      setBusy(null);
    }
  };

  const publish = async () => {
    setBusy("publish");
    setActionError(null);
    try {
      await semantic.publishDraft("knowledge", item.name);
      setResult(null);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : "Couldn't publish this item.");
    } finally {
      setBusy(null);
    }
  };

  const discard = async () => {
    if (!item.is_draft) {
      setType(item.type);
      setDescription(item.description);
      setStart(item.date_range?.start ?? "");
      setEnd(item.date_range?.end ?? "");
      setRecurrence(item.recurrence ?? "");
      setAffectsText(item.affects.join(", "));
      setResult(null);
      setActionError(null);
      return;
    }
    setBusy("discard");
    setActionError(null);
    try {
      await semantic.discardDraft("knowledge", item.name);
      setResult(null);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : "Couldn't discard this item.");
    } finally {
      setBusy(null);
    }
  };

  const Icon = TYPE_ICON[item.type] ?? Lightbulb;

  return (
    <div className="rounded-xl2 border border-line bg-surface overflow-hidden">
      <button
        onClick={onToggle}
        aria-expanded={expanded}
        className="w-full flex items-center gap-3 px-4 py-3 text-start hover:bg-surfaceAlt/60 transition"
      >
        <span className="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10 text-primary">
          <Icon size={15} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {item.is_draft && (
              <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-primary" title="Has unpublished draft" />
            )}
            <span className="font-medium text-ink truncate">{item.name}</span>
            <span className="shrink-0 rounded-full bg-surfaceAlt px-2 py-0.5 text-[0.64rem] font-medium text-muted">
              {TYPE_LABEL[item.type] ?? item.type}
            </span>
            <span className="shrink-0 text-[0.68rem] text-muted">{dateRangeLabel(item)}</span>
          </div>
          {!expanded && <p className="text-[0.8rem] text-muted mt-0.5 truncate">{item.description}</p>}
        </div>
        {expanded ? (
          <ChevronUp size={16} className="shrink-0 text-muted" />
        ) : (
          <ChevronDown size={16} className="shrink-0 text-muted" />
        )}
      </button>

      {!expanded && (
        <div className="px-4 pb-3 -mt-1 ps-[3.25rem]">
          <p className="text-[0.72rem] text-muted">{agentEffectNote(item)}</p>
        </div>
      )}

      {expanded && (
        <div className="px-4 pb-4 pt-1 border-t border-lineSoft">
          <div className="flex items-start gap-3 mt-3">
            <div className="w-40 shrink-0">
              <label className="block text-[0.78rem] font-medium text-ink mb-1" htmlFor={`k-type-${item.name}`}>
                Type
              </label>
              <select
                id={`k-type-${item.name}`}
                value={type}
                onChange={(e) => setType(e.target.value as typeof type)}
                className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
              >
                <option value="recurring_event">Recurring event</option>
                <option value="incident">Incident</option>
                <option value="note">Note</option>
              </select>
            </div>
            <div className="flex-1">
              <label className="block text-[0.78rem] font-medium text-ink mb-1" htmlFor={`k-start-${item.name}`}>
                Date range (or leave blank and use recurrence below)
              </label>
              <div className="flex items-center gap-2">
                <input
                  id={`k-start-${item.name}`}
                  type="date"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                  className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
                />
                <span className="text-muted text-[0.8rem]">–</span>
                <input
                  type="date"
                  value={end}
                  onChange={(e) => setEnd(e.target.value)}
                  aria-label="End date"
                  className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
                />
              </div>
            </div>
          </div>

          {!(start.trim() || end.trim()) && (
            <>
              <label className="block text-[0.78rem] font-medium text-ink mt-3 mb-1" htmlFor={`k-recur-${item.name}`}>
                Recurrence
              </label>
              <input
                id={`k-recur-${item.name}`}
                type="text"
                value={recurrence}
                onChange={(e) => setRecurrence(e.target.value)}
                placeholder="e.g. every November (Black Friday week)"
                className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
              />
            </>
          )}

          <label className="block text-[0.78rem] font-medium text-ink mt-3 mb-1" htmlFor={`k-desc-${item.name}`}>
            Description
          </label>
          <textarea
            id={`k-desc-${item.name}`}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-[0.85rem] text-ink outline-none focus:border-primary transition resize-y"
          />

          <label className="block text-[0.78rem] font-medium text-ink mt-3 mb-1" htmlFor={`k-affects-${item.name}`}>
            Affects (metrics or tables)
          </label>
          <input
            id={`k-affects-${item.name}`}
            type="text"
            value={affectsText}
            onChange={(e) => setAffectsText(e.target.value)}
            placeholder="comma-separated, e.g. revenue, orders"
            className="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
          />

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
