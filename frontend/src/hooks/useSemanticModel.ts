import { useCallback, useEffect, useState } from "react";
import {
  api,
  type SemanticDraftData,
  type SemanticModelResponse,
  type SemanticSection,
  type SemanticValidateResult,
  type SemanticVersion,
} from "../lib/api";

/**
 * State + mutations for the Semantic model screen (Draft -> Validate ->
 * Publish). Loads the whole model once (the semantic layer is small -- a
 * handful of metrics/rules/knowledge/glossary items per client).
 *
 * Unlike useAdminUsers, nothing here is optimistic: every mutation returns
 * the server's authoritative merged view and callers await it directly. All
 * of save/discard/validate/publish/restore RETHROW on failure -- editors show
 * the specific result inline (a validation banner, a field error) rather than
 * a toast, since "what exactly failed" matters here more than in a role
 * change or an invite.
 */
export function useSemanticModel() {
  const [model, setModel] = useState<SemanticModelResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await api.admin.semantic.get();
      setModel(data);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const saveDraft = useCallback(
    async (
      section: SemanticSection,
      itemKey: string,
      data: SemanticDraftData,
      action: "edit" | "create" | "deprecate" = "edit",
    ) => {
      const updated = await api.admin.semantic.saveDraft(section, itemKey, data, action);
      setModel(updated);
      return updated;
    },
    [],
  );

  const discardDraft = useCallback(async (section: SemanticSection, itemKey: string) => {
    const updated = await api.admin.semantic.discard(section, itemKey);
    setModel(updated);
    return updated;
  }, []);

  const validateDraft = useCallback(
    async (section: SemanticSection, itemKey: string): Promise<SemanticValidateResult> => {
      const result = await api.admin.semantic.validate(section, itemKey);
      // The validate endpoint's response is just the dry-run result, not the
      // merged model -- refresh so the item's `validated` flag (which gates
      // Publish) reflects the server's now-updated state, not the stale
      // validated:false left over from the save that preceded this call.
      await refresh();
      return result;
    },
    [refresh],
  );

  const publishDraft = useCallback(async (section: SemanticSection, itemKey: string) => {
    const updated = await api.admin.semantic.publish([{ section, item_key: itemKey }]);
    setModel(updated);
    return updated;
  }, []);

  const listVersions = useCallback((): Promise<SemanticVersion[]> => api.admin.semantic.versions(), []);

  const restore = useCallback(
    async (versionId: string) => {
      const version = await api.admin.semantic.restore(versionId);
      await refresh(); // the restore itself doesn't return the merged model
      return version;
    },
    [refresh],
  );

  return {
    model,
    loading,
    error,
    refresh,
    saveDraft,
    discardDraft,
    validateDraft,
    publishDraft,
    listVersions,
    restore,
  };
}

/** Convenience type for tabs/editors that take the hook's return value as a prop. */
export type SemanticModelHook = ReturnType<typeof useSemanticModel>;
