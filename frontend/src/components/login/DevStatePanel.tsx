import type { DevPreset } from "../../hooks/useLoginFlow";

const PRESETS: { id: DevPreset; label: string }[] = [
  { id: "code_sent", label: "Code sent" },
  { id: "wrong_code", label: "Wrong code" },
  { id: "code_expired", label: "Code expired" },
  { id: "uninvited", label: "Uninvited email" },
  { id: "suspended", label: "Suspended" },
  { id: "expired_invite", label: "Expired invite" },
  { id: "network_error", label: "Network error" },
];

/**
 * Dev-only panel (auth_login_prompt.md Part 0, item 0.3): forces the state
 * machine directly to any reviewable state without driving the mocked async
 * flow by hand. Never rendered in a production build (import.meta.env.DEV),
 * and deliberately NOT localized -- it's an internal review tool, not
 * user-facing UI.
 */
export function DevStatePanel({
  onForce,
  onReset,
}: {
  onForce: (preset: DevPreset) => void;
  onReset: () => void;
}) {
  return (
    <div className="fixed bottom-3 start-3 z-50 rounded-xl border border-line bg-surface/95 backdrop-blur p-3 shadow-pop max-w-[220px]">
      <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint mb-2">
        Dev: force state
      </p>
      <div className="flex flex-wrap gap-1.5">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => onForce(p.id)}
            className="rounded-md border border-line px-2 py-1 text-[0.68rem] text-ink hover:border-primary hover:text-primary transition"
          >
            {p.label}
          </button>
        ))}
        <button
          type="button"
          onClick={onReset}
          className="rounded-md border border-line px-2 py-1 text-[0.68rem] text-muted hover:text-ink transition"
        >
          Reset
        </button>
      </div>
    </div>
  );
}
