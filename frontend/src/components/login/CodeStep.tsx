import { Loader2 } from "lucide-react";
import { LOGIN_COPY, type Lang } from "../../lib/loginCopy";
import type { LoginState } from "../../hooks/useLoginFlow";
import { Logo } from "../brand/Logo";

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
  const hasError = state.codeError !== null;

  return (
    <div className="w-full max-w-sm rounded-loginCard border border-line bg-surface px-8 pt-[34px] pb-7 shadow-loginCard">
      <div className="flex flex-col items-center mb-[26px]">
        <Logo size={64} stacked tagline />
        <p className="text-[13.5px] text-muted mt-2" dir="ltr" style={{ unicodeBidi: "plaintext" }}>
          {t.codeSentTo(state.email)}
        </p>
      </div>

      <label htmlFor="login-code" className="block text-[12.5px] font-medium text-ink mb-[5px]">
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
        className={`w-full h-[46px] rounded-control border text-center text-[19px] tracking-[0.5em] indent-[0.5em] text-ink outline-none disabled:opacity-60 transition ${
          hasError
            ? "border-[1.5px] border-critical-fg bg-critical-bgSoft"
            : "border-line bg-surface focus:border-[1.5px] focus:border-primary focus:ring focus:ring-primaryRing"
        }`}
      />

      {state.verifying && (
        <p className="mt-2 flex items-center gap-1.5 text-[12.5px] text-muted">
          <Loader2 size={13} className="animate-spin" /> {t.verifying}
        </p>
      )}
      {state.codeError === "wrong_code" && !state.verifying && (
        <p className="mt-2 text-[12.5px] text-critical-fg" role="alert">
          {t.wrongCode(state.attemptsLeft)}
        </p>
      )}
      {state.codeError === "code_expired" && !state.verifying && (
        <p className="mt-2 text-[12.5px] text-critical-fg" role="alert">
          {t.codeExpired}
        </p>
      )}

      <div className="flex items-center justify-between mt-5">
        <button
          type="button"
          onClick={onChangeEmail}
          className="text-[12.8px] font-medium text-muted hover:text-primary transition"
        >
          {t.changeEmail}
        </button>
        <button
          type="button"
          onClick={onResend}
          disabled={!canResend}
          className="text-[12.8px] font-medium text-primary hover:underline disabled:text-faint disabled:no-underline disabled:cursor-not-allowed transition"
        >
          {state.resendCooldown > 0 ? t.resendCooldown(state.resendCooldown) : t.resend}
        </button>
      </div>
    </div>
  );
}
