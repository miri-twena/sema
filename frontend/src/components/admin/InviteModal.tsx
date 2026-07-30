import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { ApiError, type AdminDataScope, type AdminRole } from "../../lib/api";
import { useDismiss } from "../../hooks/useDismiss";

// Mirrors the server's pragmatic check (api/main.py _EMAIL_RE): one @, a dotted
// domain. Catches typos client-side; the server validates again regardless.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/**
 * Invite-a-user modal (spec §6.1). Email + role + the 7-day validity hint.
 * Client-side email-format validation on submit; server errors (duplicate
 * email, etc.) surface inline under the field, not as a toast. Overlay +
 * backdrop + Escape/outside-click close, matching the DrillChat pattern.
 */
export function InviteModal({
  onClose,
  onInvite,
}: {
  onClose: () => void;
  /** Rejects with an ApiError whose `detail` is shown inline. Resolves on a
   * successful invite (the caller closes the modal). */
  onInvite: (email: string, role: AdminRole, dataScope: AdminDataScope) => Promise<unknown>;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<AdminRole>("analyst");
  // Defaults to the safer non-financial preset (spec item 11) -- matches the
  // server's own DEFAULT_INVITE_SCOPE when a caller omits data_scope.
  const [dataScope, setDataScope] = useState<AdminDataScope>("no_financials");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const ref = useDismiss<HTMLDivElement>(true, onClose);
  const inputRef = useRef<HTMLInputElement>(null);
  const isAdmin = role === "client_admin";

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const value = email.trim();
      if (!EMAIL_RE.test(value)) {
        setError("Enter a valid email address.");
        return;
      }
      setSubmitting(true);
      setError(null);
      try {
        await onInvite(value, role, isAdmin ? "full" : dataScope);
        onClose(); // success is silent -- the new row just appears
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : "Couldn't send the invite.");
        setSubmitting(false);
      }
    },
    [email, role, dataScope, isAdmin, onInvite, onClose],
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-ink/25 animate-[sema-fade-in_0.2s_ease-out]"
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="invite-title"
        className="relative w-full max-w-md rounded-xl2 border border-line bg-surface shadow-pop p-5"
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h2 id="invite-title" className="text-base font-semibold text-ink">
              Invite user
            </h2>
            <p className="text-[0.8rem] text-muted mt-0.5">Invite link is valid for 7 days.</p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 w-8 h-8 -me-1 -mt-1 rounded-lg flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink transition"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={submit}>
          <label className="block text-[0.78rem] font-medium text-ink mb-1" htmlFor="invite-email">
            Email address
          </label>
          <input
            id="invite-email"
            ref={inputRef}
            type="email"
            value={email}
            dir="ltr"
            onChange={(e) => {
              setEmail(e.target.value);
              if (error) setError(null);
            }}
            placeholder="name@company.com"
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-primary transition"
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "invite-error" : undefined}
          />

          <label className="block text-[0.78rem] font-medium text-ink mt-3 mb-1" htmlFor="invite-role">
            Role
          </label>
          <select
            id="invite-role"
            value={role}
            onChange={(e) => setRole(e.target.value as AdminRole)}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-primary transition"
          >
            <option value="analyst">Analyst</option>
            <option value="viewer">Viewer</option>
            <option value="client_admin">Admin</option>
          </select>

          <label className="block text-[0.78rem] font-medium text-ink mt-3 mb-1" htmlFor="invite-data-scope">
            Data access
          </label>
          <select
            id="invite-data-scope"
            value={isAdmin ? "full" : dataScope}
            disabled={isAdmin}
            onChange={(e) => setDataScope(e.target.value as AdminDataScope)}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-primary disabled:opacity-60 disabled:cursor-not-allowed transition"
          >
            <option value="no_financials">No financials</option>
            <option value="sales_only">Sales only</option>
            <option value="full">Full access</option>
          </select>
          {isAdmin && (
            <p className="mt-1 text-[0.72rem] text-muted">Admins always have full data access.</p>
          )}

          {error && (
            <p id="invite-error" className="mt-2.5 text-[0.78rem] text-critical-fg" role="alert">
              {error}
            </p>
          )}

          <div className="mt-5 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-line px-3.5 py-2 text-sm text-muted hover:text-ink hover:bg-surfaceAlt transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded-xl bg-primary text-white text-sm font-medium px-4 py-2 shadow-bubble hover:bg-primary/90 disabled:opacity-60 transition"
            >
              {submitting ? "Sending…" : "Send invite"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
