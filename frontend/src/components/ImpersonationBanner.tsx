import { useEffect, useState } from "react";
import { UserRoundCog } from "lucide-react";
import { api, type ImpersonationState } from "../lib/api";
import { useT } from "../locales";
import { dirOf } from "../lib/rtl";

/** Minutes remaining until `expiresAt`, clamped to >= 0. */
function minutesRemaining(expiresAt: string): number {
  const ms = new Date(expiresAt).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / 60_000));
}

/**
 * The impersonation feature's "seatbelt" (impersonation_prompt.md): a
 * persistent, unmissable, non-dismissable top banner shown across the ENTIRE
 * app (chat + admin) whenever the real admin is viewing the app as another
 * user. Warning-tinted (existing `warning` tokens, same ones PendingBadge/
 * AuditLogScreen's impersonation highlight already use), always renders the
 * Stop button, RTL/locale-aware. Stopping hard-reloads the whole app (same
 * "simplest correct approach" the Start action uses) so every piece of state
 * -- conversations, home config, data scope -- re-fetches under the restored
 * real identity, with no partial-refresh bugs to chase.
 *
 * Rendered unconditionally at the app shell's root (both the chat view and
 * the admin panel mount it) whenever `state.active` -- callers just pass
 * whatever GET /api/admin/impersonation returned at boot.
 */
export function ImpersonationBanner({ state }: { state: ImpersonationState }) {
  const t = useT();
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState(false);
  // Re-render once a minute so "ends in Nm" actually counts down -- purely
  // cosmetic (the backend enforces the real expiry independent of this).
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 30_000);
    return () => window.clearInterval(id);
  }, []);

  if (!state.active) return null;

  const name = state.target_name || state.target_email || "";
  const roleLabel = state.target_role ? t.common.roles[state.target_role] : "";
  const minutes = state.expires_at ? minutesRemaining(state.expires_at) : null;

  const stop = async () => {
    setStopping(true);
    setError(false);
    try {
      await api.admin.impersonation.stop();
      // Hard reload (same as Start): every piece of app state re-fetches
      // under the restored real identity in one shot.
      window.location.reload();
    } catch (e) {
      setStopping(false);
      setError(true);
      void e;
    }
  };

  return (
    <div
      role="status"
      className="shrink-0 z-[60] flex items-center justify-center gap-2 bg-warning-bg px-4 py-2 text-[0.8rem] text-warning-fg border-b border-warning-fg/20"
    >
      <UserRoundCog size={15} className="shrink-0" aria-hidden />
      <span className="font-medium truncate" dir={dirOf(name)}>
        {t.impersonation.bannerViewingAs(name, roleLabel)}
      </span>
      <span aria-hidden>·</span>
      <span>
        {minutes === null ? null : minutes < 1 ? t.impersonation.endsInUnderAMinute : t.impersonation.endsIn(minutes)}
      </span>
      <button
        onClick={() => void stop()}
        disabled={stopping}
        className="ms-2 shrink-0 rounded-lg border border-warning-fg/40 bg-warning-fg/10 px-2.5 py-1 text-[0.78rem] font-semibold text-warning-fg hover:bg-warning-fg/20 disabled:opacity-60 transition"
      >
        {t.impersonation.stop}
      </button>
      {error && <span className="text-critical-fg">{t.impersonation.stopFailed}</span>}
    </div>
  );
}
