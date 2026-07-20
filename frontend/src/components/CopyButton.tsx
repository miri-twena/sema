import { useEffect, useRef, useState, type ReactNode } from "react";
import { Copy, Check, ChevronDown, AlertCircle } from "lucide-react";

/** One entry in a block's copy menu. `run` does the actual clipboard write and
 * must be called synchronously from the click so the user gesture is intact. */
export interface CopyAction {
  label: string;
  icon?: ReactNode;
  run: () => Promise<void>;
}

type State = "idle" | "copied" | "error";

/**
 * Per-block copy control. With one action it's a plain icon button; with more
 * (charts: image vs. underlying data) the primary click runs the first action
 * and a caret opens the rest. Feedback is a 1.5s checkmark, or an error icon
 * plus a message when the clipboard refuses.
 */
export function CopyButton({
  actions,
  title = "Copy",
}: {
  actions: CopyAction[];
  title?: string;
}) {
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  // Close the menu on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  const flash = (next: State, msg: string | null = null) => {
    setState(next);
    setMessage(msg);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      setState("idle");
      setMessage(null);
    }, next === "error" ? 2600 : 1500);
  };

  const run = async (action: CopyAction) => {
    setOpen(false);
    try {
      await action.run();
      flash("copied");
    } catch (err) {
      flash("error", err instanceof Error ? err.message : "Copy failed");
    }
  };

  // KPI cards and chart blocks are themselves clickable (drill-down), so every
  // handler here must stop the event from reaching the parent.
  const stop = (e: React.MouseEvent | React.KeyboardEvent) => {
    e.stopPropagation();
  };

  const icon =
    state === "copied" ? (
      <Check size={13} className="text-emerald-600" />
    ) : state === "error" ? (
      <AlertCircle size={13} className="text-orange-700" />
    ) : (
      <Copy size={13} />
    );

  const base =
    "flex items-center justify-center rounded-md border border-line bg-surface/95 backdrop-blur-sm text-muted hover:text-primary hover:border-primary transition shadow-sm";

  return (
    <div ref={wrapRef} dir="ltr" className="relative flex items-center" onClick={stop} onKeyDown={stop}>
      <div className="flex items-center">
        <button
          type="button"
          onClick={(e) => {
            stop(e);
            void run(actions[0]);
          }}
          aria-label={state === "copied" ? "Copied" : title}
          title={title}
          className={`${base} w-7 h-7 ${actions.length > 1 ? "rounded-e-none border-e-0" : ""}`}
        >
          {icon}
        </button>

        {actions.length > 1 && (
          <button
            type="button"
            onClick={(e) => {
              stop(e);
              setOpen((v) => !v);
            }}
            aria-label="More copy options"
            aria-expanded={open}
            aria-haspopup="menu"
            className={`${base} w-5 h-7 rounded-s-none`}
          >
            <ChevronDown size={11} />
          </button>
        )}
      </div>

      {open && (
        <div
          role="menu"
          className="absolute top-8 end-0 z-30 min-w-[11rem] rounded-lg border border-line bg-surface shadow-pop py-1"
        >
          {actions.map((a) => (
            <button
              key={a.label}
              role="menuitem"
              type="button"
              onClick={(e) => {
                stop(e);
                void run(a);
              }}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-start text-xs text-ink hover:bg-surfaceAlt transition"
            >
              {a.icon}
              {a.label}
            </button>
          ))}
        </div>
      )}

      {message && (
        <span className="absolute top-8 end-0 z-30 whitespace-nowrap rounded-md border border-line bg-surface px-2 py-1 text-[0.68rem] text-orange-700 shadow-sm">
          {message}
        </span>
      )}
    </div>
  );
}

/**
 * Wraps a content block and floats its copy control in the top-right corner:
 * hidden until hover/focus on pointer devices, always visible on touch (see
 * .sema-copy-affordance in index.css).
 */
export function CopyableBlock({
  actions,
  title,
  className,
  dir,
  children,
}: {
  actions: CopyAction[];
  title?: string;
  className?: string;
  /** Pass "ltr" for code blocks: it both isolates the block from surrounding
   * RTL text and makes the `end-1` below resolve to the RIGHT edge, so the
   * button stays visually top-right even inside a Hebrew answer. */
  dir?: "ltr" | "rtl";
  children: ReactNode;
}) {
  return (
    <div dir={dir} className={`sema-copy-host ${className ?? ""}`}>
      {children}
      <div className="sema-copy-affordance absolute top-1 end-1 z-20">
        <CopyButton actions={actions} title={title} />
      </div>
    </div>
  );
}
