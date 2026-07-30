import { useEffect, useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { useDismiss } from "../../hooks/useDismiss";
import { api, ApiError } from "../../lib/api";
import { useToast } from "./toast-context";

const inputClass =
  "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-primary transition";

/**
 * Google Sheets connector (data_sources_add_prompt.md Path C item 7). No
 * client credentials at any point -- sharing the sheet with SEMA's own
 * service account IS the access grant. Without SEMA_GSHEETS_SA_EMAIL
 * configured, this still works end-to-end; it just lands the source in a
 * tracked "setting up" state (same spirit as the SaaS request flow) instead
 * of validating access immediately -- the spec's own documented fallback.
 */
export function SheetsFlow({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const ref = useDismiss<HTMLDivElement>(true, onClose);
  const toast = useToast();
  const [saEmail, setSaEmail] = useState<string | null | undefined>(undefined);
  const [sheetUrl, setSheetUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    api.admin.dataSources.sheetsInfo().then((r) => setSaEmail(r.sa_email)).catch(() => setSaEmail(null));
  }, []);

  const submit = async () => {
    setSubmitting(true);
    try {
      await api.admin.dataSources.createRequest({
        connector_type: "google_sheets",
        details: { sheet_url: sheetUrl, display_name: "Google Sheets" },
      });
      setDone(true);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Couldn't submit this sheet. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/25 animate-[sema-fade-in_0.2s_ease-out]" onClick={onClose} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" className="relative w-full max-w-md rounded-xl2 border border-line bg-surface shadow-pop p-5">
        <div className="flex items-start justify-between gap-3 mb-4">
          <h2 className="text-base font-semibold text-ink">Connect Google Sheets</h2>
          <button onClick={onClose} aria-label="Close" className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink transition">
            <X size={18} />
          </button>
        </div>

        {done ? (
          <div className="flex flex-col items-center gap-3 py-4 text-center">
            <span className="inline-flex items-center justify-center w-11 h-11 rounded-full bg-emerald-50 text-emerald-600">
              <Check size={22} />
            </span>
            <p className="text-[0.85rem] text-ink">
              Sheet submitted — it'll show as "setting up" until access is confirmed.
            </p>
            <button type="button" onClick={onDone} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 transition">
              Done
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {saEmail === undefined ? null : saEmail ? (
              <p className="text-[0.78rem] text-ink">
                Share the sheet (read-only is enough) with:{" "}
                <span dir="ltr" className="font-medium">{saEmail}</span>
              </p>
            ) : (
              <p className="text-[0.78rem] text-muted">
                No credentials needed here -- once submitted, the platform team finishes setting up access on
                their side.
              </p>
            )}
            <div>
              <label className="block text-[0.78rem] font-medium text-ink mb-1" htmlFor="sheet-url">
                Sheet URL
              </label>
              <input
                id="sheet-url"
                dir="ltr"
                className={inputClass}
                value={sheetUrl}
                onChange={(e) => setSheetUrl(e.target.value)}
                placeholder="https://docs.google.com/spreadsheets/d/..."
              />
            </div>
            <button
              type="button"
              onClick={submit}
              disabled={submitting || !sheetUrl.trim()}
              className="mt-1 w-full inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50 transition"
            >
              {submitting ? <Loader2 size={15} className="animate-spin" /> : null}
              {submitting ? "Submitting…" : "Submit"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
