import { useRef, useState } from "react";
import { Check, Loader2, Upload, X } from "lucide-react";
import { useDismiss } from "../../hooks/useDismiss";
import { api, ApiError, type UploadInfo } from "../../lib/api";
import { useToast } from "./toast-context";

/**
 * Excel/CSV upload connector (data_sources_add_prompt.md Path C item 8): a
 * real queryable table in the client's own analytics DB, no external
 * service involved. There's no client-side "preview before commit" step
 * (that would need a CSV/xlsx parser in the browser -- a new dependency
 * this project avoids where possible); the file is parsed server-side and
 * this shows the RESULTING column plan + row count as confirmation.
 */
export function CsvUploadFlow({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const ref = useDismiss<HTMLDivElement>(true, onClose);
  const toast = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadInfo | null>(null);

  const onFilePicked = async (file: File) => {
    setUploading(true);
    try {
      const info = await api.admin.dataSources.upload(file);
      setResult(info);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Couldn't upload this file. Try again.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/25 animate-[sema-fade-in_0.2s_ease-out]" onClick={onClose} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" className="relative w-full max-w-md rounded-xl2 border border-line bg-surface shadow-pop p-5">
        <div className="flex items-start justify-between gap-3 mb-4">
          <h2 className="text-base font-semibold text-ink">Upload Excel / CSV</h2>
          <button onClick={onClose} aria-label="Close" className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink transition">
            <X size={18} />
          </button>
        </div>

        {result ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-start gap-2.5 rounded-lg border border-line bg-primary/[0.04] px-3 py-2.5">
              <Check size={16} className="shrink-0 mt-0.5 text-emerald-600" />
              <p className="text-[0.82rem] text-ink">
                {result.original_filename}: {result.row_count} rows, {result.columns.length} columns.
              </p>
            </div>
            <div className="max-h-48 overflow-auto sema-scroll rounded-lg border border-line">
              <table className="w-full text-[0.75rem]">
                <thead>
                  <tr className="border-b border-line text-start text-faint">
                    <th className="px-2 py-1.5 text-start font-medium">Column</th>
                    <th className="px-2 py-1.5 text-start font-medium">Type</th>
                  </tr>
                </thead>
                <tbody>
                  {result.columns.map((c) => (
                    <tr key={c.column_name} className="border-b border-lineSoft last:border-0">
                      <td className="px-2 py-1 text-ink" dir="ltr">{c.column_name}</td>
                      <td className="px-2 py-1 text-muted" dir="ltr">{c.sql_type}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button type="button" onClick={onDone} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 transition">
              Done
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="text-[0.78rem] text-muted">.csv or .xlsx, up to 10MB. Column types are inferred automatically.</p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void onFilePicked(file);
              }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-line px-4 py-8 text-muted hover:border-primary hover:text-primary disabled:opacity-50 transition"
            >
              {uploading ? <Loader2 size={22} className="animate-spin" /> : <Upload size={22} />}
              <span className="text-[0.82rem] font-medium">{uploading ? "Uploading…" : "Choose a file"}</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
