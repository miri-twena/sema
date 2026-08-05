import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { KeyRound, Loader2 } from "lucide-react";
import { BrandPanel } from "../login/BrandPanel";
import { PILOT_GATE_COPY as t } from "../../lib/pilotGateCopy";
import { usePilotAccess } from "../../hooks/usePilotAccess";

function FullPageLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-bg">
      <Loader2 size={22} className="animate-spin text-primary" aria-hidden />
    </div>
  );
}

/**
 * Wraps the whole app (main.tsx): renders `children` once access is
 * granted, otherwise a key-entry screen. THIS IS AN INTERNAL-PILOT ACCESS
 * GATE, NOT REAL AUTHENTICATION -- see lib/pilotAccess.ts and
 * docs/deployment.md's Render section. It reuses the login split shell's
 * BrandPanel (login_redesign_prompt.md) rather than the mocked email/OTP
 * LoginPage itself, which is an unrelated fake flow with no backend behind
 * it yet.
 */
export function PilotAccessGate({ children }: { children: ReactNode }) {
  const { status, submitKey } = usePilotAccess();
  const [key, setKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Distinguishes the ONE silent boot-time probe (full-page loader, no form
  // yet -- we don't know if a key is even needed) from a "checking" state
  // that follows a submit (the form must stay mounted so the button's own
  // loading state reads naturally instead of the whole screen flashing).
  const [everLocked, setEverLocked] = useState(false);

  useEffect(() => {
    if (status === "locked") setEverLocked(true);
  }, [status]);

  if (status === "granted") return <>{children}</>;
  if (status === "checking" && !everLocked) return <FullPageLoader />;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = key.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setError(null);
    const result = await submitKey(trimmed);
    setSubmitting(false);
    if (!result.ok) {
      setError(result.reason === "invalid" ? t.invalidKey : t.checkFailed);
      setKey("");
    }
  };

  return (
    <div dir="ltr" className="min-h-screen flex items-center justify-center bg-bg p-6">
      <div className="w-[min(92vw,420px)] md:w-[min(92vw,860px)] md:min-h-[520px] flex flex-col md:flex-row rounded-loginCard border border-line shadow-loginCard overflow-hidden">
        <BrandPanel />
        <div className="flex-1 flex items-center justify-center bg-surface px-6 py-10">
          <div className="w-full" style={{ maxWidth: "min(84%, 300px)" }}>
            <div className="mb-7">
              <h1 className="text-[17px] font-semibold text-ink">{t.title}</h1>
              <p className="text-[12.5px] text-muted mt-1">{t.subtitle}</p>
            </div>

            <form onSubmit={handleSubmit} noValidate>
              <label htmlFor="pilot-access-key" className="block text-[12.5px] font-medium text-ink mb-[5px]">
                {t.keyLabel}
              </label>
              <div className="relative">
                <input
                  id="pilot-access-key"
                  type="password"
                  autoComplete="off"
                  autoFocus
                  dir="ltr"
                  placeholder={t.keyPlaceholder}
                  value={key}
                  disabled={submitting}
                  onChange={(e) => {
                    setKey(e.target.value);
                    setError(null);
                  }}
                  className="peer w-full h-[42px] rounded-control border border-line bg-surface ps-9 pe-3 text-sm text-ink outline-none focus:border-[1.5px] focus:border-primary focus:ring focus:ring-primaryRing disabled:opacity-60 transition"
                />
                <KeyRound
                  size={15}
                  className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-faint peer-focus:text-primary transition"
                />
              </div>

              {error && (
                <p className="mt-2 text-[12.5px] text-critical-fg" role="alert">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={!key.trim() || submitting}
                className="mt-3 w-full h-[42px] inline-flex items-center justify-center gap-2 rounded-control bg-primary text-sm font-medium text-white shadow-loginCta hover:bg-primary/90 disabled:opacity-50 disabled:shadow-none disabled:cursor-not-allowed transition"
              >
                {submitting ? (
                  <>
                    <Loader2 size={15} className="animate-spin" /> {t.submitLoading}
                  </>
                ) : (
                  t.submitButton
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
