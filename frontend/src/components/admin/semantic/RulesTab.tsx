import { useState } from "react";
import { Plus } from "lucide-react";
import { ApiError, type SemanticModelResponse } from "../../../lib/api";
import type { SemanticModelHook } from "../../../hooks/useSemanticModel";
import { RuleCard } from "./RuleCard";

/**
 * Business rules tab (spec §6.4): a card list, each collapsible into an
 * inline edit form. "Add rule" seeds an empty draft under the typed name,
 * then expands it -- the new item then renders through the SAME RuleCard as
 * every published one, so there's only one editing code path.
 */
export function RulesTab({
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
      setCreateError("Enter a name for the rule.");
      return;
    }
    if (model.rules.some((r) => r.name === name)) {
      setCreateError("A rule with this name already exists.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await semantic.saveDraft(
        "rule", name,
        { definition: "Describe this rule.", logic: null, applies_to: [], status: "certified" },
        "create",
      );
      setExpandedKey(name);
      setAddingName(null);
    } catch (e) {
      setCreateError(e instanceof ApiError ? e.detail : "Couldn't create this rule.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-4">
        <p className="text-[0.8rem] text-muted">
          Governed rules the agent cites as assumptions when they apply.
        </p>
        {addingName === null ? (
          <button
            onClick={() => setAddingName("")}
            className="shrink-0 inline-flex items-center gap-1.5 rounded-xl bg-primary text-white text-sm font-medium px-3.5 py-2 shadow-bubble hover:bg-primary/90 transition"
          >
            <Plus size={15} /> Add rule
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={addingName}
              onChange={(e) => setAddingName(e.target.value)}
              placeholder="Rule name"
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
        {model.rules.map((r) => (
          <RuleCard
            key={r.name}
            rule={r}
            expanded={expandedKey === r.name}
            onToggle={() => setExpandedKey(expandedKey === r.name ? null : r.name)}
            semantic={semantic}
          />
        ))}
        {model.rules.length === 0 && (
          <p className="text-sm text-muted py-8 text-center">No business rules yet.</p>
        )}
      </div>
    </div>
  );
}
