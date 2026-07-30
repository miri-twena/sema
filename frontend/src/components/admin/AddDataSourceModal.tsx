import { useEffect, useState } from "react";
import {
  BarChart3,
  Database,
  FileSpreadsheet,
  Megaphone,
  ShoppingBag,
  Sheet,
  Upload,
  X,
  type LucideIcon,
} from "lucide-react";
import { useDismiss } from "../../hooks/useDismiss";
import { useUiLang } from "../../lib/useUiLang";
import { DATA_SOURCE_GALLERY } from "../../lib/placeholderCopy";
import { api, type ConnectorCatalogItem } from "../../lib/api";
import { useToast } from "./toast-context";
import { SqlDbWizard } from "./SqlDbWizard";
import { SaasRequestForm } from "./SaasRequestForm";
import { SheetsFlow } from "./SheetsFlow";
import { CsvUploadFlow } from "./CsvUploadFlow";

const ICONS: Record<string, LucideIcon> = {
  postgres: Database,
  mysql: Database,
  mssql: Database,
  priority: FileSpreadsheet,
  salesforce: FileSpreadsheet,
  google_sheets: Sheet,
  csv: Upload,
  shopify: ShoppingBag,
  google_analytics: BarChart3,
  meta_ads: Megaphone,
};

type Group = "sql" | "business" | "easy" | "soon";

function groupOf(c: ConnectorCatalogItem): Group {
  if (c.availability !== "available") return "soon";
  if (c.kind === "sql_db") return "sql";
  if (c.kind === "saas_request") return "business";
  return "easy";
}

const GROUP_ORDER: Group[] = ["sql", "business", "easy", "soon"];

type ActiveFlow =
  | { kind: "sql_db"; connectorType: "postgres" | "mysql" | "mssql" }
  | { kind: "saas_request"; connectorType: string; label: string }
  | { kind: "sheets" }
  | { kind: "csv" };

/**
 * The connector gallery (client screens spec §4.4 v1.6). Catalog is fetched
 * from the server (data_sources_add_prompt.md item 1) rather than
 * hardcoded, so an availability flip or a new connector never needs a
 * frontend deploy. Routes each card's click to the right add-flow by kind;
 * a non-"available" card only records interest.
 */
export function AddDataSourceModal({
  onClose,
  onChanged,
}: {
  onClose: () => void;
  /** Called after a connection/request/upload is successfully created, so
   * the caller can refresh the Data sources list. */
  onChanged: () => void;
}) {
  const lang = useUiLang();
  const t = DATA_SOURCE_GALLERY[lang];
  const ref = useDismiss<HTMLDivElement>(true, onClose);
  const toast = useToast();
  const [catalog, setCatalog] = useState<ConnectorCatalogItem[] | null>(null);
  const [flow, setFlow] = useState<ActiveFlow | null>(null);

  useEffect(() => {
    api.admin.dataSources.catalog().then(setCatalog).catch(() => setCatalog([]));
  }, []);

  const onCardClick = async (c: ConnectorCatalogItem) => {
    if (c.availability !== "available") {
      try {
        await api.admin.dataSources.recordInterest(c.id);
      } catch {
        // interest-recording is best-effort; the toast still confirms either way
      }
      toast(t.toast);
      return;
    }
    if (c.kind === "sql_db") setFlow({ kind: "sql_db", connectorType: c.id as "postgres" | "mysql" | "mssql" });
    else if (c.kind === "saas_request") setFlow({ kind: "saas_request", connectorType: c.id, label: c.label });
    else if (c.id === "google_sheets") setFlow({ kind: "sheets" });
    else if (c.id === "csv") setFlow({ kind: "csv" });
  };

  const closeFlowAndRefresh = () => {
    setFlow(null);
    onChanged();
    onClose();
  };

  if (flow?.kind === "sql_db") {
    return <SqlDbWizard connectorType={flow.connectorType} onClose={() => setFlow(null)} onDone={closeFlowAndRefresh} />;
  }
  if (flow?.kind === "saas_request") {
    return (
      <SaasRequestForm
        connectorType={flow.connectorType}
        label={flow.label}
        onClose={() => setFlow(null)}
        onDone={closeFlowAndRefresh}
      />
    );
  }
  if (flow?.kind === "sheets") {
    return <SheetsFlow onClose={() => setFlow(null)} onDone={closeFlowAndRefresh} />;
  }
  if (flow?.kind === "csv") {
    return <CsvUploadFlow onClose={() => setFlow(null)} onDone={closeFlowAndRefresh} />;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/25 animate-[sema-fade-in_0.2s_ease-out]" onClick={onClose} aria-hidden />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-source-title"
        className="relative w-full max-w-2xl max-h-[85vh] overflow-auto sema-scroll rounded-xl2 border border-line bg-surface shadow-pop p-5"
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h2 id="add-source-title" className="text-base font-semibold text-ink">
              {t.title}
            </h2>
            <p className="text-[0.8rem] text-muted mt-0.5">{t.subtitle}</p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 w-8 h-8 -me-1 -mt-1 rounded-lg flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink transition"
          >
            <X size={18} />
          </button>
        </div>

        {!catalog ? (
          <p className="text-sm text-muted py-8 text-center">Loading…</p>
        ) : (
          <div className="flex flex-col gap-5">
            {GROUP_ORDER.map((group) => {
              const items = catalog.filter((c) => groupOf(c) === group);
              if (items.length === 0) return null;
              return (
                <div key={group}>
                  <p className="text-[0.68rem] font-semibold uppercase tracking-wide text-faint mb-2">
                    {t.groups[group]}
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {items.map((c) => {
                      const Icon = ICONS[c.id] ?? Database;
                      const pending = c.availability === "driver_pending";
                      return (
                        <button
                          key={c.id}
                          type="button"
                          onClick={() => onCardClick(c)}
                          title={c.availability === "available" ? undefined : t.toast}
                          className="text-start flex items-start gap-2.5 rounded-xl border border-line bg-surface px-3 py-2.5 hover:border-primary transition"
                        >
                          <span className="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10 text-primary">
                            <Icon size={16} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="flex items-center gap-1.5">
                              <span className="block text-[0.82rem] font-medium text-ink">{c.label}</span>
                              {group === "soon" && (
                                <span className="shrink-0 rounded-full bg-surfaceAlt px-1.5 py-0.5 text-[0.6rem] font-medium text-muted">
                                  {pending ? "Driver pending" : t.groups.soon}
                                </span>
                              )}
                            </span>
                            <span className="block text-[0.72rem] text-muted leading-snug">
                              {c.unlocks[lang] ?? c.unlocks.en}
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
