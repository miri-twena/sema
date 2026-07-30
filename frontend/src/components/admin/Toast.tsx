import { useCallback, useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, X } from "lucide-react";
import { ToastContext } from "./toast-context";

/**
 * Minimal failure-only toast for the admin panel. Success is silent (the row
 * just changes) -- per the mockup, only failures interrupt. Self-contained, no
 * dependency: a small context holds one message at a time and auto-dismisses,
 * mirroring CopyButton's local-flash timeout pattern but hoisted so any admin
 * component can raise one after an optimistic action rolls back.
 *
 * The context + useToast hook live in toast-context.ts so this file exports
 * only a component (React Fast Refresh requirement).
 */
const AUTO_DISMISS_MS = 4000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);

  const show = useCallback((m: string) => setMessage(m), []);
  const dismiss = useCallback(() => setMessage(null), []);

  useEffect(() => {
    if (!message) return;
    const id = window.setTimeout(dismiss, AUTO_DISMISS_MS);
    return () => window.clearTimeout(id);
  }, [message, dismiss]);

  return (
    <ToastContext.Provider value={show}>
      {children}
      {message && (
        <div
          role="alert"
          className="fixed bottom-5 start-1/2 -translate-x-1/2 z-[60] flex items-center gap-2.5 rounded-xl border border-critical-fg/30 bg-critical-bg px-4 py-2.5 text-sm text-critical-fg shadow-pop animate-[sema-fade-in_0.2s_ease-out]"
        >
          <AlertTriangle size={16} className="shrink-0" />
          <span style={{ unicodeBidi: "plaintext" }}>{message}</span>
          <button
            onClick={dismiss}
            aria-label="Dismiss"
            className="shrink-0 -me-1 w-6 h-6 rounded-md flex items-center justify-center hover:bg-critical-fg/10 transition"
          >
            <X size={14} />
          </button>
        </div>
      )}
    </ToastContext.Provider>
  );
}
