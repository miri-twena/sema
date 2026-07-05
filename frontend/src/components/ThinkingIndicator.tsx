// Staged "thinking" indicator: shows the current phase label with a soft
// pulse, so a long request reads as progress rather than a frozen spinner.
export function ThinkingIndicator({ phase }: { phase?: string }) {
  return (
    <div className="flex items-center gap-2.5 px-1 py-3 text-sm text-muted">
      <span className="relative flex h-2.5 w-2.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/50" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-primary" />
      </span>
      <span className="transition-opacity">{phase ?? "Thinking"}…</span>
    </div>
  );
}
