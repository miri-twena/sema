// Bilingual copy for the login page (SEMA-Login-Spec.pdf v1.2 §2). Same
// Record<Lang, {...}> shape as lib/evidence.ts's EV_LABELS, kept in its own
// module so the state machine (useLoginFlow) and the components can both
// import it without a circular dependency, and so tests can assert every
// key exists in both languages without rendering anything.

export type Lang = "he" | "en";

export type ErrorKind = "uninvited" | "suspended" | "expired_invite" | "provider_cancelled" | "network_error";

/** Browser language on first paint (spec §2.1: "לפי שפת הדפדפן בכניסה
 * ראשונה") -- there is no known org yet at this point, so this is the ONLY
 * signal available. Any Hebrew-tagged browser locale (he, he-IL, ...) -> he;
 * everything else -> en. */
export function detectBrowserLang(navigatorLanguage: string | undefined): Lang {
  return (navigatorLanguage ?? "").toLowerCase().startsWith("he") ? "he" : "en";
}

interface LoginCopy {
  headline: string;
  emailLabel: string;
  emailPlaceholder: string;
  continueButton: string;
  continueLoading: string;
  divider: string;
  comingSoonTooltip: string;
  troubleLink: string;
  troubleMailtoSubject: string;
  joiningOrg: (org: string) => string;
  codeSentTo: (email: string) => string;
  codeLabel: string;
  verifying: string;
  resend: string;
  resendCooldown: (seconds: number) => string;
  changeEmail: string;
  wrongCode: (attemptsLeft: number) => string;
  codeExhausted: string;
  codeExpired: string;
  redirecting: string;
  tryAgain: string;
  errors: Record<ErrorKind, (email: string) => string>;
}

export const LOGIN_COPY: Record<Lang, LoginCopy> = {
  en: {
    headline: "AI Business Advisor",
    emailLabel: "Email",
    emailPlaceholder: "you@company.com",
    continueButton: "Continue",
    continueLoading: "Sending…",
    divider: "or",
    comingSoonTooltip: "Coming soon",
    troubleLink: "Having trouble?",
    troubleMailtoSubject: "Trouble signing in to SEMA",
    joiningOrg: (org) => `Joining ${org}`,
    codeSentTo: (email) => `We sent a 6-digit code to ${email}`,
    codeLabel: "Verification code",
    verifying: "Verifying…",
    resend: "Resend",
    resendCooldown: (seconds) => `Resend (${seconds}s)`,
    changeEmail: "Change email",
    wrongCode: (attemptsLeft) =>
      attemptsLeft > 0
        ? `Incorrect code. ${attemptsLeft} attempt${attemptsLeft === 1 ? "" : "s"} left.`
        : "Too many incorrect attempts. Request a new code.",
    codeExhausted: "Too many incorrect attempts. Request a new code.",
    codeExpired: "The code has expired. Request a new one.",
    redirecting: "Signing in…",
    tryAgain: "Try again",
    errors: {
      uninvited: (email) => `The account ${email} is not invited to SEMA. Contact your organization admin.`,
      suspended: () => "Your account has been suspended. Contact your organization admin.",
      expired_invite: () => "The invite link has expired. Ask your admin to resend it.",
      provider_cancelled: () => "Something went wrong. Try again.",
      network_error: () => "Something went wrong. Try again.",
    },
  },
  he: {
    // "AI Business Advisor" -- the English brand phrase, deliberately NOT
    // translated (spec 0.2), even in the Hebrew half of this dictionary.
    // Currently dead: LoginPage.tsx hardcodes lang="en" (AGENTS.md: "UI is
    // English, always"), kept here so the dictionary stays the single
    // source of truth if per-org login language is ever reinstated.
    headline: "AI Business Advisor",
    emailLabel: "אימייל",
    emailPlaceholder: "you@company.com",
    continueButton: "המשך",
    continueLoading: "שולח…",
    divider: "או",
    comingSoonTooltip: "בקרוב",
    troubleLink: "נתקלת בבעיה?",
    troubleMailtoSubject: "בעיה בכניסה ל-SEMA",
    joiningOrg: (org) => `מצטרף/ת ל-${org}`,
    codeSentTo: (email) => `שלחנו קוד בן 6 ספרות ל-${email}`,
    codeLabel: "קוד אימות",
    verifying: "מאמת…",
    resend: "שלח שוב",
    resendCooldown: (seconds) => `שלח שוב (${seconds})`,
    changeEmail: "החלף אימייל",
    wrongCode: (attemptsLeft) =>
      attemptsLeft > 0 ? `קוד שגוי. נותרו ${attemptsLeft} ניסיונות.` : "יותר מדי ניסיונות שגויים. בקש קוד חדש.",
    codeExhausted: "יותר מדי ניסיונות שגויים. בקש קוד חדש.",
    codeExpired: "פג תוקף הקוד. בקש קוד חדש.",
    redirecting: "מתחברים…",
    tryAgain: "נסה שוב",
    errors: {
      uninvited: (email) => `החשבון ${email} אינו מוזמן ל-SEMA. פנה לאדמין הארגון שלך.`,
      suspended: () => "החשבון שלך הושעה. פנה לאדמין הארגון.",
      expired_invite: () => "קישור ההזמנה פג. בקש מהאדמין לשלוח מחדש.",
      provider_cancelled: () => "משהו השתבש. נסה שוב.",
      network_error: () => "משהו השתבש. נסה שוב.",
    },
  },
};

export function dirFor(lang: Lang): "rtl" | "ltr" {
  return lang === "he" ? "rtl" : "ltr";
}
