import { Loader2 } from "lucide-react";
import { LOGIN_COPY, type Lang } from "../../lib/loginCopy";
import type { LoginState } from "../../hooks/useLoginFlow";

export function CodeStep({
  lang,
  state,
  onCodeChange,
  onResend,
  onChangeEmail,
}: {
  lang: Lang;
  state: LoginState;
  onCodeChange: (code: string) => void;
  onResend: () => void;
  onChangeEmail: () => void;
}) {
  const t = LOGIN_COPY[lang];
  const exhausted = state.codeError === "wrong_code" && state.attemptsLeft <= 0;
  const canResend = state.resendCooldown <= 0 && !state.resending;

  return (
    <div className="w-full max-w-sm">
      <div className="text-center mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">SEMA</h1>
        <p className="text-sm text-muted mt-1.5" dir="ltr" style={{ unicodeBidi: "plaintext" }}>
          {t.codeSentTo(state.email)}
        </p>
      </div>

      <label htmlFor="login-code" className="block text-[0.78rem] font-medium text-ink mb-1">
        {t.codeLabel}
      </label>
      <input
        id="login-code"
        type="text"
        inputMode="numeric"
        autoComplete="one-time-code"
        autoFocus
        dir="ltr"
        maxLength={6}
        disabled={exhausted || state.verifying}
        value={state.code}
        onChange={(e) => onCodeChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
        className="w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-center text-lg tracking-[0.5em] text-ink outline-none focus:border-primary disabled:opacity-60 transition"
      />

      {state.verifying && (
        <p className="mt-2 flex items-center gap-1.5 text-[0.78rem] text-muted">
          <Loader2 size={13} className="animate-spin" /> {t.verifying}
        </p>
      )}
      {state.codeError === "wrong_code" && !state.verifying && (
        <p className="mt-2 text-[0.78rem] text-critical-fg" role="alert">
          {t.wrongCode(state.attemptsLeft)}
        </p>
      )}
      {state.codeError === "code_expired" && !state.verifying && (
        <p className="mt-2 text-[0.78rem] text-critical-fg" role="alert">
          {t.codeExpired}
        </p>
      )}

      <div className="flex items-center justify-between mt-5">
        <button
          type="button"
          onClick={onChangeEmail}
          className="text-[0.8rem] text-muted hover:text-primary transition"
        >
          {t.changeEmail}
        </button>
        <button
          type="button"
          onClick={onResend}
          disabled={!canResend}
          className="text-[0.8rem] font-medium text-primary hover:underline disabled:text-faint disabled:no-underline disabled:cursor-not-allowed transition"
        >
          {state.resendCooldown > 0 ? t.resendCooldown(state.resendCooldown) : t.resend}
        </button>
      </div>
    </div>
  );
}
