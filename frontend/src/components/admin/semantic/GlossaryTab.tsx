import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { ApiError, type SemanticGlossaryItem, type SemanticModelResponse, type SemanticValidateResult } from "../../../lib/api";
import type { SemanticModelHook } from "../../../hooks/useSemanticModel";
import { ActionErrorBanner, ValidationBanner } from "./ValidationBanner";

/** One editable term -> canonical-mapping row. Always editable (no
 * expand/collapse) -- the spec calls this "a simple two-column editable
 * list". `dir="auto"` on both the term and the input so a Hebrew term reads
 * right-to-left without flipping the row's own layout. */
function GlossaryRow({ item, semantic }: { item: SemanticGlossaryItem; semantic: SemanticModelHook }) {
  const [mapsTo, setMapsTo] = useState(item.maps_to);
  const [language, setLanguage] = useState(item.language ?? "");
  const [busy, setBusy] = useState<"validate" | "publish" | "discard" | null>(null);
  const [result, setResult] = useState<SemanticValidateResult | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setMapsTo(item.maps_to);
    setLanguage(item.language ?? "");
    setResult(null);
    setActionError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.term]);

  const dirty = mapsTo !== item.maps_to || (language || null) !== item.language;
  const canPublish = item.is_draft && item.validated && !dirty;
  const canDiscard = (dirty || item.is_draft) && busy === null;

  const runValidation = async () => {
    if (!mapsTo.trim()) {
      setActionError("Maps-to is required.");
      return;
    }
    setBusy("validate");
    setActionError(null);
    try {
      // Preserve "create" for a not-yet-published new term -- see RuleCard's
      // identical comment for why defaulting to "edit" here would be a bug.
      await semantic.saveDraft(
        "glossary", item.term, { maps_to: mapsTo, language: language || null },
        item.is_new ? "create" : "edit",
      );
      setResult(await semantic.validateDraft("glossary", item.term));
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : "Couldn't save or validate this term.");
    } finally {
      setBusy(null);
    }
  };

  const publish = async () => {
    setBusy("publish");
    setActionError(null);
    try {
      await semantic.publishDraft("glossary", item.term);
      setResult(null);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : "Couldn't publish this term.");
    } finally {
      setBusy(null);
    }
  };

  const discard = async () => {
    if (!item.is_draft) {
      setMapsTo(item.maps_to);
      setLanguage(item.language ?? "");
      setResult(null);
      setActionError(null);
      return;
    }
    setBusy("discard");
    setActionError(null);
    try {
      await semantic.discardDraft("glossary", item.term);
      setResult(null);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.detail : "Couldn't discard this term.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="border-b border-lineSoft py-2.5">
      <div className="flex items-center gap-3">
        <div className="w-1/3 shrink-0 flex items-center gap-1.5 min-w-0">
          {item.is_draft && (
            <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-primary" title="Has unpublished draft" />
          )}
          <span className="text-[0.85rem] text-ink truncate" dir="auto" title={item.term}>
            {item.term}
          </span>
        </div>
        <input
          value={mapsTo}
          onChange={(e) => setMapsTo(e.target.value)}
          dir="auto"
          aria-label={`Maps to, for term ${item.term}`}
          placeholder="metric or entity name"
          className="flex-1 min-w-0 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
        />
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          aria-label={`Language, for term ${item.term}`}
          className="w-16 shrink-0 rounded-lg border border-line bg-surface px-1.5 py-1.5 text-[0.76rem] text-ink outline-none focus:border-primary transition"
        >
          <option value="">—</option>
          <option value="he">HE</option>
          <option value="en">EN</option>
        </select>
        <div className="shrink-0 flex items-center gap-3">
          <button
            onClick={discard}
            disabled={!canDiscard}
            className="text-[0.75rem] text-muted hover:text-ink disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            Discard
          </button>
          <button
            onClick={runValidation}
            disabled={busy !== null}
            className="text-[0.75rem] font-medium text-primary hover:underline disabled:opacity-60 transition"
          >
            {busy === "validate" ? "Validating…" : "Validate"}
          </button>
          <button
            onClick={publish}
            disabled={!canPublish || busy !== null}
            title={!canPublish ? "Run validation on this draft first." : undefined}
            className="text-[0.75rem] font-medium text-primary hover:underline disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {busy === "publish" ? "Publishing…" : "Publish"}
          </button>
        </div>
      </div>
      {result && <ValidationBanner result={result} />}
      {actionError && <ActionErrorBanner text={actionError} />}
    </div>
  );
}

/** Glossary tab (spec §6.4): term -> canonical metric/entity mapping. Hebrew
 * and English terms both supported (`dir="auto"`). Add-row inline: type a
 * term, create it as an empty draft, and it joins the list as an editable row. */
export function GlossaryTab({
  model,
  semantic,
}: {
  model: SemanticModelResponse;
  semantic: SemanticModelHook;
}) {
  const [newTerm, setNewTerm] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const addRow = async () => {
    const term = newTerm.trim();
    if (!term) return;
    if (model.glossary.some((g) => g.term === term)) {
      setCreateError("This term already exists.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      // maps_to is required (like the placeholder text RulesTab/KnowledgeTab
      // seed for their own required fields) -- an empty string here would
      // fail the server's required-field check on this very first save.
      await semantic.saveDraft("glossary", term, { maps_to: "(edit me)", language: null }, "create");
      setNewTerm("");
    } catch (e) {
      setCreateError(e instanceof ApiError ? e.detail : "Couldn't add this term.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div>
      <p className="text-[0.8rem] text-muted mb-4">
        Terms the agent treats as synonyms for a metric or entity -- Hebrew and English both supported.
      </p>

      <div className="flex items-center gap-3 px-0 pb-2 text-[0.68rem] font-semibold uppercase tracking-wide text-faint border-b border-line">
        <span className="w-1/3">Term</span>
        <span className="flex-1">Maps to</span>
        <span className="w-16 shrink-0">Lang</span>
        <span className="shrink-0 w-[9.5rem]" aria-hidden />
      </div>

      {model.glossary.map((g) => (
        <GlossaryRow key={g.term} item={g} semantic={semantic} />
      ))}
      {model.glossary.length === 0 && (
        <p className="text-sm text-muted py-8 text-center">No glossary terms yet.</p>
      )}

      <div className="flex items-center gap-2 mt-4">
        <input
          type="text"
          value={newTerm}
          onChange={(e) => setNewTerm(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addRow()}
          placeholder="New term (e.g. רווח or basket value)"
          dir="auto"
          className="flex-1 max-w-xs rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
        />
        <button
          onClick={addRow}
          disabled={creating || !newTerm.trim()}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-[0.8rem] text-ink hover:bg-surfaceAlt disabled:opacity-50 transition"
        >
          <Plus size={14} /> Add term
        </button>
      </div>
      {createError && <p className="text-[0.78rem] text-critical-fg mt-2">{createError}</p>}
    </div>
  );
}
