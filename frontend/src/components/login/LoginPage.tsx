import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { api, resolveApiUrl } from "../../lib/api";
import { dirFor, LOGIN_COPY, type Lang } from "../../lib/loginCopy";
import { useLoginFlow } from "../../hooks/useLoginFlow";
import { EmailStep } from "./EmailStep";
import { CodeStep } from "./CodeStep";
import { ErrorScreen } from "./ErrorScreen";
import { DevStatePanel } from "./DevStatePanel";

type OrgContext = { name: string; logoUrl: string | null } | null;

/** ?client_id=ecommerce on the login URL simulates arriving via an invite
 * link (spec §2.1: the inviting org's logo + "Joining X" shown above the
 * SSO buttons). Reads the SAME public, non-admin-gated org-settings endpoint
 * the main app's sidebar already uses -- not new backend surface, just an
 * existing read. Absent entirely outside of this simulated-invite case. */
function useInviteOrgContext(): OrgContext {
  const [org, setOrg] = useState<OrgContext>(null);
  useEffect(() => {
    const clientId = new URLSearchParams(window.location.search).get("client_id");
    if (!clientId) return;
    let cancelled = false;
    api
      .orgSettings(clientId)
      .then((s) => !cancelled && setOrg({ name: s.name, logoUrl: resolveApiUrl(s.logo_path) }))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return org;
}

/**
 * The login page (SEMA-Login-Spec.pdf v1.2 §2), Part 0 of auth_login_prompt.md:
 * every visual/interaction state, driven entirely by a local mocked state
 * machine (useLoginFlow) -- NO backend call, NO session, NO cookies. Lives
 * OUTSIDE the chat app shell (wired directly in main.tsx by URL path), so the
 * app itself stays reachable with today's mock identity, unaffected.
 */
export function LoginPage() {
  // Always English/LTR (AGENTS.md: "UI is English, always" -- supersedes Part
  // 0's original browser-language detection). LOGIN_COPY.he and
  // detectBrowserLang stay in lib/loginCopy.ts, unused here for now, in case
  // per-org login language is reinstated later.
  const lang: Lang = "en";
  const dir = dirFor(lang);
  const t = LOGIN_COPY[lang];
  const orgContext = useInviteOrgContext();
  const { state, submitEmail, setCode, resend, changeEmail, forcePreset, dispatch } = useLoginFlow();

  const troubleHref = `mailto:?subject=${encodeURIComponent(t.troubleMailtoSubject)}`;

  // Part 0 has no real destination to land on -- the app itself is already
  // freely reachable with the mock identity (spec §2.1), so the mocked
  // "successful" verify demonstrates the real arc by returning there after a
  // beat, instead of dead-ending on a static "you're in!" screen.
  useEffect(() => {
    if (state.step !== "redirecting") return;
    const id = window.setTimeout(() => {
      window.location.href = "/";
    }, 900);
    return () => window.clearTimeout(id);
  }, [state.step]);

  return (
    <div dir={dir} className="min-h-screen flex items-center justify-center bg-bg px-6 py-12">
      {state.step === "email" && (
        <EmailStep
          lang={lang}
          submitting={state.emailSubmitting}
          orgContext={orgContext}
          onSubmit={submitEmail}
          troubleHref={troubleHref}
        />
      )}

      {state.step === "code" && (
        <CodeStep
          lang={lang}
          state={state}
          onCodeChange={setCode}
          onResend={resend}
          onChangeEmail={changeEmail}
        />
      )}

      {state.step === "error" && state.errorKind && (
        <ErrorScreen
          lang={lang}
          kind={state.errorKind}
          email={state.email}
          onRetry={changeEmail}
          onChangeEmail={changeEmail}
        />
      )}

      {state.step === "redirecting" && (
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={22} className="animate-spin text-primary" />
          <p className="text-sm text-muted">{t.redirecting}</p>
        </div>
      )}

      {import.meta.env.DEV && (
        <DevStatePanel onForce={forcePreset} onReset={() => dispatch({ type: "RESET" })} />
      )}
    </div>
  );
}
