import { useState } from "react";
import { Plus } from "lucide-react";
import { ApiError, type SemanticModelResponse } from "../../../lib/api";
import type { SemanticModelHook } from "../../../hooks/useSemanticModel";
import { KnowledgeCard } from "./KnowledgeCard";

/**
 * Calendar & knowledge tab (spec §6.4): recurring events, incidents, and
 * notes the agent can cite -- an incident overlapping a question's date range
 * adds a caveat to the answer server-side (see response.py). Same
 * seed-then-expand creation pattern as RulesTab.
 */
export function KnowledgeTab({
  model,
  semantic,
}: {
  model: SemanticModelResponse;
  semantic: SemanticModelHook;
}) {
  const [addingName, setAddingName] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  const startCreate = async () => {
    const name = (addingName ?? "").trim();
    if (!name) {
      setCreateError("Enter a name for the event or note.");
      return;
    }
    if (model.knowledge.some((k) => k.name === name)) {
      setCreateError("An item with this name already exists.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await semantic.saveDraft(
        "knowledge", name,
        { type: "note", description: "Describe this event or note.", affects: [], date_range: null, recurrence: null },
        "create",
      );
      setExpandedKey(name);
      setAddingName(null);
    } catch (e) {
      setCreateError(e instanceof ApiError ? e.detail : "Couldn't create this item.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-4">
        <p className="text-[0.8rem] text-muted">
          Recurring events, incidents, and notes the agent uses as context.
        </p>
        {addingName === null ? (
          <button
            onClick={() => setAddingName("")}
            className="shrink-0 inline-flex items-center gap-1.5 rounded-xl bg-primary text-white text-sm font-medium px-3.5 py-2 shadow-bubble hover:bg-primary/90 transition"
          >
            <Plus size={15} /> Add event or note
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={addingName}
              onChange={(e) => setAddingName(e.target.value)}
              placeholder="Name"
              autoFocus
              className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[0.82rem] text-ink outline-none focus:border-primary transition"
            />
            <button
              onClick={startCreate}
              disabled={creating}
              className="rounded-lg bg-primary text-white text-[0.8rem] font-medium px-3 py-1.5 hover:bg-primary/90 disabled:opacity-60 transition"
            >
              {creating ? "Creating…" : "Create"}
            </button>
            <button
              onClick={() => { setAddingName(null); setCreateError(null); }}
              className="text-[0.8rem] text-muted hover:text-ink transition"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
      {createError && <p className="text-[0.78rem] text-critical-fg mb-3">{createError}</p>}

      <div className="flex flex-col gap-3">
        {model.knowledge.map((k) => (
          <KnowledgeCard
            key={k.name}
            item={k}
            expanded={expandedKey === k.name}
            onToggle={() => setExpandedKey(expandedKey === k.name ? null : k.name)}
            semantic={semantic}
          />
        ))}
        {model.knowledge.length === 0 && (
          <p className="text-sm text-muted py-8 text-center">No calendar or knowledge items yet.</p>
        )}
      </div>
    </div>
  );
}
