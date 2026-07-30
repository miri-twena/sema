import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  DEFAULT_HOME_CONFIG,
  type HomeConfig,
  type HomeConfigPreview,
} from "../lib/api";
import { useToast } from "../components/admin/toast-context";

/**
 * State + mutations for the admin Home screen editor (spec §1).
 *
 * `draft` is the client's in-progress edit, seeded from the server's draft
 * (or its published config, or DEFAULT_HOME_CONFIG if neither exists yet) on
 * load. Every change autosaves (debounced 600ms, silent on success) and
 * refetches the live preview -- the two are independent requests so a slow
 * preview never blocks the autosave, and vice versa.
 */
export function useHomeConfig() {
  const toast = useToast();
  const [draft, setDraft] = useState<HomeConfig>(DEFAULT_HOME_CONFIG);
  const [published, setPublished] = useState<HomeConfig | null>(null);
  const [version, setVersion] = useState(0);
  const [publishedAt, setPublishedAt] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishErrors, setPublishErrors] = useState<string[] | null>(null);
  const [hasDraft, setHasDraft] = useState(false);

  const [preview, setPreview] = useState<HomeConfigPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(true);

  const saveTimer = useRef<number | undefined>(undefined);
  const previewTimer = useRef<number | undefined>(undefined);
  // Mirrors `draft` synchronously (state updates are async, and Publish
  // needs the LATEST edit even if it's called in the same tick as a
  // keystroke, before a re-render would have refreshed a closure's `draft`).
  const draftRef = useRef<HomeConfig>(DEFAULT_HOME_CONFIG);

  const refreshPreview = useCallback((config: HomeConfig) => {
    window.clearTimeout(previewTimer.current);
    previewTimer.current = window.setTimeout(() => {
      setPreviewLoading(true);
      api.admin.homeConfig
        .preview(config)
        .then(setPreview)
        .catch(() => setPreview(null))
        .finally(() => setPreviewLoading(false));
    }, 400);
  }, []);

  /** Pull the canonical state from the server and reconcile every piece of
   * local state to it -- used for the initial load AND to resync after a
   * mutation that may have left `hasDraft` lying about what the server
   * actually has (e.g. Revert 409ing because the edit it meant to discard
   * hadn't been autosaved yet: the end state -- no draft -- is still
   * correct, but the client's own `hasDraft` flag has no other way to find
   * that out, since nothing else clears it). */
  const syncFromServer = useCallback(() => {
    return api.admin.homeConfig.get().then((res) => {
      const current = res.draft ?? res.published ?? DEFAULT_HOME_CONFIG;
      draftRef.current = current;
      setDraft(current);
      setHasDraft(res.draft !== null);
      setPublished(res.published);
      setVersion(res.version);
      setPublishedAt(res.published_at);
      setWarnings(res.warnings);
    });
  }, []);

  useEffect(() => {
    syncFromServer()
      .catch(() => toast("Couldn't load the home screen configuration."))
      .finally(() => setLoading(false));
  }, [toast, syncFromServer]);

  useEffect(() => {
    if (loading) return;
    refreshPreview(draft);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, loading]);

  /** Save draftRef.current right now (cancelling any pending debounce timer
   * first) -- the ONE place that actually calls the save endpoint, used both
   * by the debounced autosave and by Publish's flush-before-publish. */
  const doSave = useCallback(async () => {
    window.clearTimeout(saveTimer.current);
    saveTimer.current = undefined;
    setSaving(true);
    try {
      await api.admin.homeConfig.saveDraft(draftRef.current);
    } catch {
      toast("Couldn't save your changes.");
    } finally {
      setSaving(false);
    }
  }, [toast]);

  /** Merge a partial change into the draft and autosave (debounced). */
  const update = useCallback(
    (patch: Partial<HomeConfig> | ((prev: HomeConfig) => HomeConfig)) => {
      setDraft((prev) => {
        const next = typeof patch === "function" ? patch(prev) : { ...prev, ...patch };
        draftRef.current = next;
        return next;
      });
      setPublishErrors(null);
      setHasDraft(true);
      setSaving(true);
      window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => void doSave(), 600);
    },
    [doSave],
  );

  const publish = useCallback(async () => {
    setPublishing(true);
    setPublishErrors(null);
    try {
      // Flush first: Publish must act on the LATEST edit, not whatever the
      // 600ms autosave debounce happened to have saved already -- otherwise
      // a publish right after a quick edit could 409 ("nothing to publish")
      // or promote a stale draft.
      await doSave();
      const res = await api.admin.homeConfig.publish();
      setPublished(res.published);
      setVersion(res.version);
      setPublishedAt(res.published_at);
      setWarnings(res.warnings);
      setHasDraft(res.draft !== null);
      toast("Published -- the home screen is now live for everyone.");
    } catch (e) {
      if (e instanceof ApiError && e.detail) {
        setPublishErrors([e.detail]);
      } else {
        toast("Couldn't publish.");
      }
      // Whatever failed, the server is the source of truth for whether a
      // draft actually exists now -- resync rather than trust local state,
      // the same reasoning as revert()'s catch below.
      void syncFromServer();
    } finally {
      setPublishing(false);
    }
  }, [doSave, syncFromServer, toast]);

  const revert = useCallback(async () => {
    // Cancel (don't flush) any pending autosave: Revert means "discard my
    // unsaved edit too" -- letting that debounce fire after Revert would
    // silently resurrect the very draft the user just asked to discard.
    window.clearTimeout(saveTimer.current);
    saveTimer.current = undefined;
    setSaving(false); // the cancelled autosave will never resolve to clear this itself
    try {
      const res = await api.admin.homeConfig.revert();
      const next = res.draft ?? res.published ?? DEFAULT_HOME_CONFIG;
      draftRef.current = next;
      setDraft(next);
      setHasDraft(res.draft !== null);
      setPublished(res.published);
      setPublishErrors(null);
    } catch (e) {
      toast(e instanceof ApiError ? e.detail : "Couldn't revert.");
      // A 409 here ("nothing to revert") can still mean the END state is
      // right (no draft) even though THIS call didn't do anything -- e.g.
      // the pending autosave this same click cancelled hadn't landed yet.
      // Resync so `hasDraft` never gets stuck lying about what the server
      // actually has.
      void syncFromServer();
    }
  }, [syncFromServer, toast]);

  return {
    draft,
    update,
    published,
    version,
    publishedAt,
    warnings,
    loading,
    saving,
    hasDraft,
    publish,
    publishing,
    publishErrors,
    revert,
    preview,
    previewLoading,
  };
}
