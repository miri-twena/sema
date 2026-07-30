import { useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { useDismiss } from "../../hooks/useDismiss";
import { api, ApiError } from "../../lib/api";
import { useToast } from "./toast-context";

const inputClass =
  "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-primary transition";
const labelClass = "block text-[0.78rem] font-medium text-ink mb-1";

/**
 * Non-secret SaaS request form (data_sources_add_prompt.md Path B --
 * Priority/Salesforce). No credentials at any point: the server itself
 * rejects any field that looks like one (sema_core's _reject_credential_
 * like_fields), this form just keeps to display/contact fields so that
 * server-side check never actually fires in normal use.
 */
export function SaasRequestForm({
  connectorType,
  label,
  onClose,
  onDone,
}: {
  connectorType: string;
  label: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const ref = useDismiss<HTMLDivElement>(true, onClose);
  const toast = useToast();
  const [displayName, setDisplayName] = useState(label);
  const [environment, setEnvironment] = useState("");
  const [technicalContact, setTechnicalContact] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      await api.admin.dataSources.createRequest({
        connector_type: connectorType,
        details: { display_name: displayName, environment, technical_contact: technicalContact, notes },
      });
      setDone(true);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Couldn't send the request. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/25 animate-[sema-fade-in_0.2s_ease-out]" onClick={onClose} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" className="relative w-full max-w-md rounded-xl2 border border-line bg-surface shadow-pop p-5">
        <div className="flex items-start justify-between gap-3 mb-4">
          <h2 className="text-base font-semibold text-ink">Request {label}</h2>
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
              Request sent — {label} will show as "setting up" while the platform team configures it.
            </p>
            <button type="button" onClick={onDone} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 transition">
              Done
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="text-[0.78rem] text-muted">
              No credentials here -- this just tells the platform team you want {label} connected.
            </p>
            <div>
              <label className={labelClass} htmlFor="req-display-name">Display name</label>
              <input id="req-display-name" className={inputClass} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </div>
            <div>
              <label className={labelClass} htmlFor="req-environment">Environment</label>
              <input id="req-environment" dir="ltr" className={inputClass} value={environment} onChange={(e) => setEnvironment(e.target.value)} placeholder="Production / Sandbox" />
            </div>
            <div>
              <label className={labelClass} htmlFor="req-contact">Technical contact</label>
              <input id="req-contact" dir="ltr" className={inputClass} value={technicalContact} onChange={(e) => setTechnicalContact(e.target.value)} placeholder="name@company.com" />
            </div>
            <div>
              <label className={labelClass} htmlFor="req-notes">Notes</label>
              <textarea id="req-notes" className={`${inputClass} min-h-[4.5rem]`} value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
            <button
              type="button"
              onClick={submit}
              disabled={submitting}
              className="mt-1 w-full inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50 transition"
            >
              {submitting ? <Loader2 size={15} className="animate-spin" /> : null}
              {submitting ? "Sending…" : "Send request"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
