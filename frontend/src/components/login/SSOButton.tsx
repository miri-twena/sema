/** Official Google "G" mark (4-color), unmodified proportions. */
function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.98v2.33A9 9 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.18.29-1.72V4.95H.98A9 9 0 0 0 0 9c0 1.45.35 2.83.98 4.05l2.99-2.33z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.51.46 3.44 1.35l2.59-2.59C13.46.89 11.43 0 9 0A9 9 0 0 0 .98 4.95l2.99 2.33C4.68 5.16 6.66 3.58 9 3.58z"
      />
    </svg>
  );
}

/** Official Microsoft four-square mark, unmodified colors/proportions. */
function MicrosoftIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
      <rect x="0" y="0" width="8.5" height="8.5" fill="#F25022" />
      <rect x="9.5" y="0" width="8.5" height="8.5" fill="#7FBA00" />
      <rect x="0" y="9.5" width="8.5" height="8.5" fill="#00A4EF" />
      <rect x="9.5" y="9.5" width="8.5" height="8.5" fill="#FFB900" />
    </svg>
  );
}

/**
 * SSO sign-in buttons (spec §2.1): official brand guidelines -- icon, full
 * label, equal size, no "primary" styling among them. Disabled with a
 * "Coming soon" tooltip until Part B ships the real OIDC flow behind a flag.
 */
export function SSOButton({
  provider,
  tooltip,
}: {
  provider: "google" | "microsoft";
  tooltip: string;
}) {
  const label = provider === "google" ? "Continue with Google" : "Continue with Microsoft";
  return (
    <button
      type="button"
      disabled
      title={tooltip}
      aria-label={`${label} (${tooltip})`}
      className="w-full inline-flex items-center justify-center gap-2.5 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm font-medium text-ink opacity-60 cursor-not-allowed"
    >
      {provider === "google" ? <GoogleIcon /> : <MicrosoftIcon />}
      <span dir="ltr">{label}</span>
    </button>
  );
}
