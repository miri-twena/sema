import { useCallback, useEffect, useState } from "react";
import { RotateCcw, X } from "lucide-react";
import { ApiError, type SemanticVersion } from "../../../lib/api";
import type { SemanticModelHook } from "../../../hooks/useSemanticModel";
import { useDismiss } from "../../../hooks/useDismiss";

function formatWhen(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

/** Inline two-step confirm (same lightweight pattern as UserRow's remove
 * confirm) rather than a second modal on top of the slide-over. */
function RestoreConfirm({ onConfirm, busy }: { onConfirm: () => void; busy: boolean }) {
  const [confirming, setConfirming] = useState(false);
  const close = useCallback(() => setConfirming(false), []);
  const ref = useDismiss<HTMLDivElement>(confirming, close);

  if (!confirming) {
    return (
      <button
        onClick={() => setConfirming(true)}
        className="inline-flex items-center gap-1 text-[0.75rem] font-medium text-primary hover:underline"
      >
        <RotateCcw size={12} /> Restore
      </button>
    );
  }
  return (
    <div ref={ref} className="inline-flex items-center gap-2">
      <span className="text-[0.72rem] text-muted">Restore this version?</span>
      <button
        onClick={() => {
          onConfirm();
          close();
        }}
        disabled={busy}
        className="text-[0.75rem] font-semibold text-critical-fg hover:underline disabled:opacity-60"
      >
        {busy ? "Restoring…" : "Confirm"}
      </button>
    </div>
  );
}

/**
 * Version history slide-over (spec §6.4): author, date, and changed items per
 * version, with Restore behind a confirm. Restoring creates a NEW version
 * (never rewrites history), so the list simply refreshes afterward -- the
 * restored content shows up as the latest entry.
 */
export function HistorySlideOver({
  onClose,
  semantic,
}: {
  onClose: () => void;
  semantic: SemanticModelHook;
}) {
  const [versions, setVersions] = useState<SemanticVersion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const ref = useDismiss<HTMLDivElement>(true, onClose);

  const load = useCallback(() => {
    semantic
      .listVersions()
      .then(setVersions)
      .catch(() => setError("Couldn't load version history."));
  }, [semantic]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const restore = async (versionId: string) => {
    setRestoringId(versionId);
    setError(null);
    try {
      await semantic.restore(versionId);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "Couldn't restore this version.");
    } finally {
      setRestoringId(null);
    }
  };

  return (
    <>
      <div
        className="fixed inset-0 bg-ink/20 z-40 animate-[sema-fade-in_0.2s_ease-out]"
        onClick={onClose}
        aria-hidden
      />
      <aside
        ref={ref}
        className="fixed top-0 end-0 h-full w-[420px] max-w-[92vw] bg-bg border-s border-line shadow-pop z-50 flex flex-col animate-[sema-slide-in-end_0.2s_ease-out]"
      >
        <header className="flex items-center justify-between gap-3 px-5 py-4 border-b border-line bg-surface shrink-0">
          <div>
            <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">
              Semantic model
            </div>
            <div className="text-sm font-semibold text-ink">Version history</div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 w-8 h-8 rounded-lg text-muted hover:bg-surfaceAlt hover:text-ink flex items-center justify-center transition"
          >
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-auto sema-scroll px-5 py-4">
          {error && <p className="text-[0.8rem] text-critical-fg mb-3">{error}</p>}
          {!versions ? (
            <p className="text-sm text-muted">Loading…</p>
          ) : versions.length === 0 ? (
            <p className="text-sm text-muted">No published versions yet.</p>
          ) : (
            <div className="flex flex-col divide-y divide-lineSoft">
              {versions.map((v, i) => (
                <div key={v.id} className="py-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[0.85rem] font-medium text-ink">v{v.version}</span>
                    {/* The latest version is the current state -- nothing to restore to. */}
                    {i > 0 && (
                      <RestoreConfirm onConfirm={() => restore(v.id)} busy={restoringId === v.id} />
                    )}
                  </div>
                  <p className="text-[0.72rem] text-muted mt-0.5">
                    {v.author ?? "System"} · {formatWhen(v.created_at)}
                  </p>
                  {v.changed_items.length > 0 && (
                    <p className="text-[0.75rem] text-ink mt-1" dir="auto">
                      {v.changed_items.join(", ")}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
