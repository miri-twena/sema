import { AlertTriangle } from "lucide-react";
import { LOGIN_COPY, type ErrorKind, type Lang } from "../../lib/loginCopy";

// Only the network/provider-cancel error offers a retry -- uninvited/
// suspended/expired_invite are terminal for this attempt (spec §2.2: the
// user must go contact their admin, not just click a button again).
const RETRYABLE: ErrorKind[] = ["provider_cancelled", "network_error"];

export function ErrorScreen({
  lang,
  kind,
  email,
  onRetry,
  onChangeEmail,
}: {
  lang: Lang;
  kind: ErrorKind;
  email: string;
  onRetry: () => void;
  onChangeEmail: () => void;
}) {
  const t = LOGIN_COPY[lang];
  const message = t.errors[kind](email);
  const retryable = RETRYABLE.includes(kind);

  return (
    <div className="w-full max-w-sm text-center">
      <h1 className="text-2xl font-semibold tracking-tight text-ink mb-6">SEMA</h1>
      <div
        role="alert"
        className="flex flex-col items-center gap-3 rounded-xl border border-critical-fg/25 bg-critical-bg px-5 py-6"
      >
        <AlertTriangle size={22} className="text-critical-fg" />
        <p className="text-sm text-ink" style={{ unicodeBidi: "plaintext" }}>
          {message}
        </p>
        {retryable ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-1 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 transition"
          >
            {t.tryAgain}
          </button>
        ) : (
          <button
            type="button"
            onClick={onChangeEmail}
            className="mt-1 text-[0.8rem] font-medium text-primary hover:underline"
          >
            {t.changeEmail}
          </button>
        )}
      </div>
    </div>
  );
}
