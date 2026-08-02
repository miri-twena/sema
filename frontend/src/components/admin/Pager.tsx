import { ChevronLeft, ChevronRight } from "lucide-react";

/**
 * Shared "Showing X-Y of Z" + prev/next pager for admin-panel tables.
 * Extracted from the Audit log screen (the first table to need server-side
 * paging) so the Users screen (users_pagination_prompt.md) reuses the same
 * component instead of a second hand-rolled pager. The admin panel is
 * English-only/LTR-always by convention, so -- unlike the answer-table pager
 * fixed in table_pager_arrows_prompt.md -- these chevrons never need RTL
 * isolation; they're never rendered inside a dir="rtl" ancestor.
 */
export function Pager({
  page,
  total,
  pageSize,
  onPageChange,
  /** Hide the whole pager (not just disable the arrows) when everything fits
   * on one page -- the Users screen wants zero pager noise for a small org;
   * the Audit log keeps showing it (with both arrows disabled) whenever
   * there's at least one event, its existing behavior. */
  hideWhenSinglePage = false,
}: {
  page: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  hideWhenSinglePage?: boolean;
}) {
  if (total === 0) return null;
  if (hideWhenSinglePage && total <= pageSize) return null;

  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  const canPrev = page > 1;
  const canNext = to < total;

  return (
    <div className="flex items-center justify-between mt-3">
      <p className="text-[0.75rem] text-muted">
        Showing {from}–{to} of {total}
      </p>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={!canPrev}
          aria-label="Previous page"
          className="w-7 h-7 flex items-center justify-center rounded-lg border border-line text-muted hover:text-ink hover:border-primary disabled:opacity-40 disabled:cursor-not-allowed transition"
        >
          <ChevronLeft size={14} />
        </button>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={!canNext}
          aria-label="Next page"
          className="w-7 h-7 flex items-center justify-center rounded-lg border border-line text-muted hover:text-ink hover:border-primary disabled:opacity-40 disabled:cursor-not-allowed transition"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}
