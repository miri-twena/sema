// Copy for PilotAccessGate.tsx. English/LTR only, same precedent as
// lib/loginCopy.ts's own login page (AGENTS.md: "Exceptions that stay
// English always: the login page, brand terms..., and technical
// identifiers") -- kept OUT of the central locale files (frontend/src/
// locales/) deliberately: those exist to switch the app CHROME's language
// once an org's default_language is known (org_settings), but this screen
// renders BEFORE any client/org has been resolved (it gates the very first
// request), so there is no org context to pick a language from yet. A
// dedicated module, not inline strings, so it's still a single edit point
// rather than hardcoded JSX text.

export const PILOT_GATE_COPY = {
  title: "Access key required",
  subtitle: "This is a private internal pilot of SEMA. Enter the access key to continue.",
  keyLabel: "Access key",
  keyPlaceholder: "Enter access key",
  submitButton: "Continue",
  submitLoading: "Checking…",
  invalidKey: "Access key is invalid or has expired.",
  checkFailed: "Couldn't reach SEMA. Check your connection and try again.",
};
