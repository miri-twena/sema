import { AlertTriangle, CheckCircle2 } from "lucide-react";
import type { SemanticFormat, SemanticValidateResult } from "../../../lib/api";

function formatValue(value: unknown, format?: SemanticFormat | null): string {
  if (typeof value !== "number") return String(value);
  if (format === "currency") {
    return value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
  }
  if (format === "percent") {
    return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** Green/red result banner for a validation dry run -- shared by every
 * editor (metric SQL, rule logic, knowledge/glossary schema checks). `format`
 * is only meaningful for a metric's numeric value (currency/percent). */
export function ValidationBanner({
  result,
  format,
}: {
  result: SemanticValidateResult;
  format?: SemanticFormat | null;
}) {
  const text = result.ok
    ? result.value !== null && result.value !== undefined
      ? `Read-only dry run${result.period_label ? ` on ${result.period_label}` : ""}: ` +
        `${formatValue(result.value, format)}` +
        `${typeof result.row_count === "number" ? ` across ${result.row_count.toLocaleString()} row${result.row_count === 1 ? "" : "s"}` : ""}` +
        `${typeof result.duration_ms === "number" ? ` · ${(result.duration_ms / 1000).toFixed(1)}s` : ""}`
      : (result.message ?? "Validation passed.")
    : (result.error ?? "Validation failed.");

  return (
    <div
      role="status"
      className={`mt-4 flex items-start gap-2 rounded-lg px-3 py-2.5 text-[0.82rem] ${
        result.ok ? "bg-emerald-50 text-emerald-800" : "bg-critical-bg text-critical-fg"
      }`}
    >
      {result.ok ? (
        <CheckCircle2 size={16} className="shrink-0 mt-0.5" />
      ) : (
        <AlertTriangle size={16} className="shrink-0 mt-0.5" />
      )}
      <span>{text}</span>
    </div>
  );
}

/** Generic failure banner for a save/discard/publish action error. */
export function ActionErrorBanner({ text }: { text: string }) {
  return (
    <div
      role="alert"
      className="mt-4 flex items-start gap-2 rounded-lg bg-critical-bg px-3 py-2.5 text-[0.82rem] text-critical-fg"
    >
      <AlertTriangle size={16} className="shrink-0 mt-0.5" />
      <span>{text}</span>
    </div>
  );
}
