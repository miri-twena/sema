import { useCallback, useEffect, useState } from "react";
import { api, type AuditEvent } from "../lib/api";

/**
 * State + fetching for the admin Audit log screen (spec §3).
 *
 * Filtering and pagination are SERVER-SIDE (unlike the Users screen, the log
 * can grow unbounded) -- every filter change refetches page 1. `search` is
 * debounced the same way UsersScreen debounces its own search (200ms).
 */
export function useAuditLog() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [actor, setActor] = useState("");
  const [category, setCategory] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState(""); // debounced copy that actually filters

  useEffect(() => {
    const id = window.setTimeout(() => setQ(search.trim()), 200);
    return () => window.clearTimeout(id);
  }, [search]);

  // Any filter change (not a page change by itself) jumps back to page 1 --
  // otherwise a narrower filter could land on a now-nonexistent page.
  useEffect(() => {
    setPage(1);
  }, [actor, category, dateFrom, dateTo, q]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.admin.audit.list({
        actor: actor || undefined,
        category: category || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        q: q || undefined,
        page,
      });
      setEvents(data.events);
      setTotal(data.total);
      setPage(data.page);
      setPageSize(data.page_size);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [actor, category, dateFrom, dateTo, q, page]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const exportUrl = api.admin.audit.exportUrl({
    actor: actor || undefined,
    category: category || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    q: q || undefined,
  });

  const filtering = !!(actor || category || dateFrom || dateTo || q);
  const clearFilters = () => {
    setActor("");
    setCategory("");
    setDateFrom("");
    setDateTo("");
    setSearch("");
  };

  return {
    events,
    total,
    page,
    pageSize,
    loading,
    error,
    filtering,
    actor,
    setActor,
    category,
    setCategory,
    dateFrom,
    setDateFrom,
    dateTo,
    setDateTo,
    search,
    setSearch,
    setPage,
    clearFilters,
    exportUrl,
    refresh,
  };
}
