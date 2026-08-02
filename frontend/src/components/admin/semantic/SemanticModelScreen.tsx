import { useState } from "react";
import { History } from "lucide-react";
import { useSemanticModel } from "../../../hooks/useSemanticModel";
import { MetricsTab } from "./MetricsTab";
import { RulesTab } from "./RulesTab";
import { KnowledgeTab } from "./KnowledgeTab";
import { EntitiesTab } from "./EntitiesTab";
import { GlossaryTab } from "./GlossaryTab";
import { HistorySlideOver } from "./HistorySlideOver";

type TabId = "metrics" | "entities" | "rules" | "knowledge" | "glossary";

/**
 * The "Semantic model" screen: Draft -> Validate -> Publish over the agent's
 * grounding (sql/semantic/*.yaml). Header shows the published version + draft
 * count (updates as individual items across tabs get published); each tab
 * owns its own editing UI, but they all share one `useSemanticModel` snapshot
 * so a draft made in one tab is immediately reflected everywhere (e.g. the
 * header's draft count).
 */
export function SemanticModelScreen({ clientLabel }: { clientLabel: string }) {
  const semantic = useSemanticModel();
  const [tab, setTab] = useState<TabId>("metrics");
  const [historyOpen, setHistoryOpen] = useState(false);

  const { model, loading, error } = semantic;

  const tabs: Array<{ id: TabId; label: string; count?: number }> = [
    { id: "metrics", label: "Metrics", count: model?.metrics.length },
    { id: "entities", label: "Entities" },
    { id: "rules", label: "Business rules", count: model?.rules.length },
    { id: "knowledge", label: "Calendar & knowledge", count: model?.knowledge.length },
    { id: "glossary", label: "Glossary", count: model?.glossary.length },
  ];

  return (
    <div className="max-w-4xl xl:max-w-6xl 2xl:max-w-7xl mx-auto px-8 py-8">
      <div className="text-[0.75rem] text-muted mb-2" dir="auto">
        {clientLabel || "Workspace"} <span className="text-faint">›</span> Organization admin
      </div>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">Semantic model</h1>
          <p className="text-[0.82rem] text-muted mt-1">
            {model ? (
              <>
                Published v{model.published_version}
                {model.draft_count > 0 && (
                  <> · {model.draft_count} draft{model.draft_count === 1 ? "" : "s"}</>
                )}
              </>
            ) : (
              "Loading…"
            )}
          </p>
        </div>
        <button
          onClick={() => setHistoryOpen(true)}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-xl border border-line px-3.5 py-2 text-sm text-muted hover:text-ink hover:bg-surfaceAlt transition"
        >
          <History size={15} /> History
        </button>
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-1 mt-5 border-b border-line overflow-x-auto">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            aria-current={tab === t.id ? "page" : undefined}
            className={`shrink-0 px-3 py-2 text-[0.82rem] font-medium border-b-2 -mb-px transition ${
              tab === t.id
                ? "border-primary text-primary-dark"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t.label}
            {typeof t.count === "number" && (
              <span className="ms-1.5 text-[0.7rem] text-faint">{t.count}</span>
            )}
          </button>
        ))}
      </div>

      <div className="mt-5">
        {loading ? (
          <div className="py-10 text-center text-sm text-muted">Loading…</div>
        ) : error || !model ? (
          <div className="py-10 text-center text-sm text-muted">
            Couldn't load the semantic model. Please try again.
          </div>
        ) : (
          <>
            {tab === "metrics" && <MetricsTab model={model} semantic={semantic} />}
            {tab === "entities" && <EntitiesTab />}
            {tab === "rules" && <RulesTab model={model} semantic={semantic} />}
            {tab === "knowledge" && <KnowledgeTab model={model} semantic={semantic} />}
            {tab === "glossary" && <GlossaryTab model={model} semantic={semantic} />}
          </>
        )}
      </div>

      {historyOpen && <HistorySlideOver onClose={() => setHistoryOpen(false)} semantic={semantic} />}
    </div>
  );
}
