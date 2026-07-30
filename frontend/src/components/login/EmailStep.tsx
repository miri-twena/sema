import { useState, type FormEvent } from "react";
import { Loader2, Mail } from "lucide-react";
import { LOGIN_COPY, type Lang } from "../../lib/loginCopy";
import { SSOButton } from "./SSOButton";

export function EmailStep({
  lang,
  submitting,
  orgContext,
  onSubmit,
  troubleHref,
}: {
  lang: Lang;
  submitting: boolean;
  orgContext: { name: string; logoUrl: string | null } | null;
  onSubmit: (email: string) => void;
  troubleHref: string;
}) {
  const t = LOGIN_COPY[lang];
  const [email, setEmail] = useState("");
  const valid = /\S+@\S+\.\S+/.test(email.trim());

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!valid || submitting) return;
    onSubmit(email.trim());
  };

  return (
    <div className="w-full max-w-sm">
      {orgContext && (
        <div className="flex flex-col items-center mb-6">
          {orgContext.logoUrl ? (
            <img src={orgContext.logoUrl} alt={orgContext.name} className="h-10 w-auto mb-2 object-contain" />
          ) : null}
          <p className="text-sm text-muted">{t.joiningOrg(orgContext.name)}</p>
        </div>
      )}

      <div className="text-center mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">SEMA</h1>
        <p className="text-sm text-muted mt-1.5">{t.headline}</p>
      </div>

      <form onSubmit={handleSubmit} noValidate>
        <label htmlFor="login-email" className="block text-[0.78rem] font-medium text-ink mb-1">
          {t.emailLabel}
        </label>
        <div className="relative">
          <Mail size={15} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-faint" />
          <input
            id="login-email"
            type="email"
            inputMode="email"
            autoComplete="email"
            autoFocus
            dir="ltr"
            placeholder={t.emailPlaceholder}
            value={email}
            disabled={submitting}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-line bg-surface ps-9 pe-3 py-2.5 text-sm text-ink outline-none focus:border-primary disabled:opacity-60 transition"
          />
        </div>

        <button
          type="submit"
          disabled={!valid || submitting}
          className="mt-3 w-full inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition"
        >
          {submitting ? (
            <>
              <Loader2 size={15} className="animate-spin" /> {t.continueLoading}
            </>
          ) : (
            t.continueButton
          )}
        </button>
      </form>

      <div className="flex items-center gap-3 my-5">
        <div className="flex-1 h-px bg-line" />
        <span className="text-[0.75rem] text-faint">{t.divider}</span>
        <div className="flex-1 h-px bg-line" />
      </div>

      <div className="flex flex-col gap-2.5">
        <SSOButton provider="google" tooltip={t.comingSoonTooltip} />
        <SSOButton provider="microsoft" tooltip={t.comingSoonTooltip} />
      </div>

      <div className="text-center mt-6">
        <a href={troubleHref} className="text-[0.8rem] text-muted hover:text-primary transition">
          {t.troubleLink}
        </a>
      </div>
    </div>
  );
}
