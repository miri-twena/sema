import { useCallback, useEffect, useRef, useState } from "react";
import { Image as ImageIcon, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { api, ApiError, resolveApiUrl, type CurrencyInfo, type OrgSettings, type RetentionPolicy } from "../../lib/api";
import { configureFormatting } from "../../lib/format";
import { timeAgo } from "../../lib/time";
import { useToast } from "./toast-context";
import { CHART_PALETTE } from "../../lib/tokens";

const RETENTION_LABEL: Record<RetentionPolicy, string> = {
  forever: "Keep forever",
  "90d": "Delete after 90 days",
  "30d": "Delete after 30 days",
};

const LANGUAGE_LABEL: Record<"en" | "he", string> = { en: "English", he: "עברית" };

const NUMBER_FORMAT_LABEL: Record<string, string> = {
  "1,234.56": "1,234.56 (US/UK style)",
  "1.234,56": "1.234,56 (EU style)",
};

/** The "Last cleanup: 6 hours ago · 12 conversations deleted" status line
 * under the retention selector (org_settings_gapfix_prompt.md Part 1) --
 * read-only, reflects the scheduled background sweep's own last run. */
function RetentionStatusLine({ settings }: { settings: OrgSettings }) {
  if (settings.retention_policy === "forever") {
    return <p className="mt-1.5 text-[0.75rem] text-faint">Automatic cleanup is off.</p>;
  }
  if (settings.last_retention_status === "error") {
    return (
      <p className="mt-1.5 text-[0.75rem] text-critical-fg">
        Last cleanup attempt failed ({timeAgo(settings.last_retention_run_at)}): {settings.last_retention_error}
      </p>
    );
  }
  if (!settings.last_retention_run_at) {
    return <p className="mt-1.5 text-[0.75rem] text-faint">No cleanup has run yet.</p>;
  }
  const count = settings.last_retention_deleted_count ?? 0;
  return (
    <p className="mt-1.5 text-[0.75rem] text-faint">
      Last cleanup: {timeAgo(settings.last_retention_run_at)} · {count} conversation{count === 1 ? "" : "s"} deleted
    </p>
  );
}

/** One field group as a ruled card -- the 3px top rule carries the group's
 * identity hue, same device as the KPI/table/accordion cards elsewhere in
 * the redesign. */
function SettingsCard({ title, hue, children }: { title: string; hue: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-surface overflow-hidden">
      <span className="block h-[3px] w-full" style={{ background: hue }} aria-hidden />
      <div className="p-5">
        <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-faint mb-3">{title}</div>
        {children}
      </div>
    </div>
  );
}

function Field({
  label,
  htmlFor,
  error,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string | null;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-4">
      <label className="block text-[0.78rem] font-medium text-ink mb-1" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {hint && !error && <p className="mt-1 text-[0.72rem] text-muted">{hint}</p>}
      {error && (
        <p className="mt-1 text-[0.78rem] text-critical-fg" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

const inputClass =
  "w-full max-w-sm rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-primary transition";

/**
 * Organization settings (spec §2): a single form in four groups (Identity,
 * Time and region, Display, Data). Every field saves itself on change/blur
 * (silent on success -- toast only on failure), matching the rest of the
 * admin panel's optimistic-mutation convention.
 */
export function OrgSettingsScreen({ clientLabel }: { clientLabel: string }) {
  const toast = useToast();
  const [settings, setSettings] = useState<OrgSettings | null>(null);
  const [currencies, setCurrencies] = useState<CurrencyInfo[]>([]);
  const [timezones, setTimezones] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [nameDraft, setNameDraft] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [logoError, setLogoError] = useState<string | null>(null);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  // Timezone changes affect day boundaries going forward only -- a pending
  // selection sits here until the user confirms the warning, rather than
  // saving immediately like every other field.
  const [pendingTimezone, setPendingTimezone] = useState<string | null>(null);
  // Retention changes show a "N conversations will be deleted" preview and
  // require confirmation before saving, same reason.
  const [pendingRetention, setPendingRetention] = useState<RetentionPolicy | null>(null);
  const [retentionPreviewCount, setRetentionPreviewCount] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    Promise.all([api.admin.orgSettings.get(), api.admin.orgSettings.currencies(), api.admin.orgSettings.timezones()])
      .then(([s, c, tz]) => {
        setSettings(s);
        setNameDraft(s.name);
        setCurrencies(c);
        setTimezones(tz);
      })
      .catch(() => toast("Couldn't load organization settings."))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** One field's silent save: applies optimistically, reverts + toasts on
   * failure, and surfaces the server's conflict flag if another admin's
   * change was clobbered (last-write-wins, spec §2.2). */
  const saveField = useCallback(
    async (patch: Record<string, string>) => {
      if (!settings) return;
      const snapshot = settings;
      try {
        const updated = await api.admin.orgSettings.update({
          ...patch,
          expected_updated_at: snapshot.updated_at,
        });
        setSettings(updated);
        const currencyInfo = currencies.find((c) => c.code === updated.currency);
        configureFormatting({
          currency_symbol: currencyInfo?.symbol ?? "$",
          currency_position: currencyInfo?.position ?? "prefix",
          number_format: updated.number_format,
        });
        if (updated.conflict) {
          toast("Someone else changed organization settings while you were editing -- your change was saved.");
        }
      } catch (err) {
        setSettings(snapshot); // revert any optimistic UI (name draft handled separately)
        toast(err instanceof ApiError ? err.detail : "Couldn't save that change.");
      }
    },
    [settings, currencies, toast],
  );

  const saveName = useCallback(async () => {
    const trimmed = nameDraft.trim();
    if (!trimmed) {
      setNameError("Organization name can't be empty.");
      return;
    }
    setNameError(null);
    if (settings && trimmed === settings.name) return;
    await saveField({ name: trimmed });
  }, [nameDraft, settings, saveField]);

  const confirmTimezoneChange = useCallback(async () => {
    if (!pendingTimezone) return;
    await saveField({ timezone: pendingTimezone });
    setPendingTimezone(null);
  }, [pendingTimezone, saveField]);

  const startRetentionChange = useCallback(
    async (policy: RetentionPolicy) => {
      setPendingRetention(policy);
      setRetentionPreviewCount(null);
      try {
        const preview = await api.admin.orgSettings.retentionPreview(policy);
        setRetentionPreviewCount(preview.conversations_to_delete);
      } catch {
        setRetentionPreviewCount(0);
      }
    },
    [],
  );

  const confirmRetentionChange = useCallback(async () => {
    if (!pendingRetention) return;
    await saveField({ retention_policy: pendingRetention });
    setPendingRetention(null);
    setRetentionPreviewCount(null);
  }, [pendingRetention, saveField]);

  const handleLogoSelect = useCallback(
    async (file: File) => {
      setLogoError(null);
      if (file.size > 1024 * 1024) {
        setLogoError("Logo must be 1MB or smaller.");
        return;
      }
      if (!/\.(png|svg)$/i.test(file.name)) {
        setLogoError("Only PNG or SVG logo files are supported.");
        return;
      }
      setUploadingLogo(true);
      try {
        const updated = await api.admin.orgSettings.uploadLogo(file);
        setSettings(updated);
      } catch (err) {
        setLogoError(err instanceof ApiError ? err.detail : "Couldn't upload the logo.");
      } finally {
        setUploadingLogo(false);
      }
    },
    [],
  );

  if (loading || !settings) {
    return (
      <div className="max-w-4xl 2xl:max-w-5xl mx-auto px-8 py-8">
        <div className="h-6 w-48 rounded bg-surfaceAlt animate-pulse mb-6" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-32 rounded-xl bg-surfaceAlt animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const logoUrl = resolveApiUrl(settings.logo_path);

  // Form-heavy screen -- a smaller bump than the table screens (Users/Audit
  // log get the full xl/2xl staged width): individual fields already cap at
  // max-w-sm, so extra room here only gives the two-column card grid a bit
  // more breathing room at 2xl, never stretches a label or hint line.
  return (
    <div className="max-w-4xl 2xl:max-w-5xl mx-auto px-8 py-8">
      <div className="text-[0.75rem] text-muted mb-2" dir="auto">
        {clientLabel || "Workspace"} <span className="text-faint">›</span> Organization admin
      </div>
      <h1 className="text-xl font-semibold text-ink">Organization settings</h1>
      <p className="text-[0.82rem] text-muted mt-1">
        Changes save automatically as you edit each field.
      </p>

      <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-5">
        <SettingsCard title="Identity" hue={CHART_PALETTE[0]}>
          <Field label="Organization name" htmlFor="org-name" error={nameError}>
            <input
              id="org-name"
              value={nameDraft}
              dir="auto"
              onChange={(e) => {
                setNameDraft(e.target.value);
                if (nameError) setNameError(null);
              }}
              onBlur={saveName}
              className={inputClass}
            />
          </Field>

          <Field label="Logo" htmlFor="org-logo" error={logoError} hint="PNG or SVG, 1MB max.">
            <div className="flex items-center gap-3">
              <span className="shrink-0 w-14 h-14 rounded-lg border border-line bg-surfaceAlt flex items-center justify-center overflow-hidden">
                {logoUrl ? (
                  <img src={logoUrl} alt="" className="w-full h-full object-contain" />
                ) : (
                  <ImageIcon size={20} className="text-faint" aria-hidden />
                )}
              </span>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadingLogo}
                className="rounded-xl border border-line px-3.5 py-2 text-sm text-ink hover:bg-surfaceAlt disabled:opacity-60 transition"
              >
                {uploadingLogo ? (
                  <span className="flex items-center gap-1.5">
                    <Loader2 size={14} className="animate-spin" /> Uploading…
                  </span>
                ) : logoUrl ? (
                  "Replace logo"
                ) : (
                  "Upload logo"
                )}
              </button>
              <input
                ref={fileInputRef}
                id="org-logo"
                type="file"
                accept=".png,.svg,image/png,image/svg+xml"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void handleLogoSelect(file);
                  e.target.value = ""; // allow re-selecting the same file next time
                }}
              />
            </div>
          </Field>
        </SettingsCard>

        <SettingsCard title="Time and region" hue={CHART_PALETTE[2]}>
          <Field
            label="Timezone"
            htmlFor="org-timezone"
            hint="Affects day boundaries in reports and the agent's answers, going forward only -- past data is never recalculated."
          >
            <select
              id="org-timezone"
              value={pendingTimezone ?? settings.timezone}
              onChange={(e) => setPendingTimezone(e.target.value)}
              className={inputClass}
            >
              {timezones.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
            {pendingTimezone && pendingTimezone !== settings.timezone && (
              <div className="mt-2 rounded-lg border border-lineSoft bg-warning-bg/40 px-3 py-2.5 text-[0.78rem] text-ink">
                Changing the timezone shifts "day" boundaries in every report and answer from now on --
                nothing is recalculated retroactively.
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={confirmTimezoneChange}
                    className="rounded-lg bg-primary text-white text-[0.78rem] font-medium px-3 py-1.5 hover:bg-primary/90 transition"
                  >
                    Apply going forward
                  </button>
                  <button
                    type="button"
                    onClick={() => setPendingTimezone(null)}
                    className="rounded-lg border border-line text-[0.78rem] text-muted px-3 py-1.5 hover:bg-surfaceAlt transition"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </Field>
        </SettingsCard>

        <SettingsCard title="Display" hue={CHART_PALETTE[1]}>
          <Field label="Currency" htmlFor="org-currency" hint="Display only -- SEMA never converts between currencies.">
            <select
              id="org-currency"
              value={settings.currency}
              onChange={(e) => saveField({ currency: e.target.value })}
              className={inputClass}
            >
              {currencies.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.code} ({c.symbol})
                </option>
              ))}
            </select>
          </Field>

          <Field label="Number format" htmlFor="org-number-format">
            <select
              id="org-number-format"
              value={settings.number_format}
              onChange={(e) => saveField({ number_format: e.target.value })}
              className={inputClass}
            >
              {Object.entries(NUMBER_FORMAT_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Default language"
            htmlFor="org-language"
            hint="Applies to new users; an existing user's own language preference wins."
          >
            <select
              id="org-language"
              value={settings.default_language}
              onChange={(e) => saveField({ default_language: e.target.value })}
              className={inputClass}
            >
              {Object.entries(LANGUAGE_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
        </SettingsCard>

        <SettingsCard title="Data" hue={CHART_PALETTE[4]}>
          <Field label="Conversation retention" htmlFor="org-retention">
            <select
              id="org-retention"
              value={pendingRetention ?? settings.retention_policy}
              onChange={(e) => startRetentionChange(e.target.value as RetentionPolicy)}
              className={inputClass}
            >
              {(Object.keys(RETENTION_LABEL) as RetentionPolicy[]).map((policy) => (
                <option key={policy} value={policy}>
                  {RETENTION_LABEL[policy]}
                </option>
              ))}
            </select>
            <RetentionStatusLine settings={settings} />
            {pendingRetention && pendingRetention !== settings.retention_policy && (
              <div className="mt-2 rounded-lg border border-lineSoft bg-warning-bg/40 px-3 py-2.5 text-[0.78rem] text-ink">
                {retentionPreviewCount === null ? (
                  "Checking how many conversations this affects…"
                ) : retentionPreviewCount > 0 ? (
                  <>
                    {retentionPreviewCount} conversation{retentionPreviewCount === 1 ? "" : "s"} will be
                    deleted on the next retention run.
                  </>
                ) : (
                  "No conversations are old enough to be affected right now."
                )}
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={confirmRetentionChange}
                    disabled={retentionPreviewCount === null}
                    className="rounded-lg bg-primary text-white text-[0.78rem] font-medium px-3 py-1.5 hover:bg-primary/90 disabled:opacity-60 transition"
                  >
                    Confirm
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setPendingRetention(null);
                      setRetentionPreviewCount(null);
                    }}
                    className="rounded-lg border border-line text-[0.78rem] text-muted px-3 py-1.5 hover:bg-surfaceAlt transition"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </Field>
        </SettingsCard>
      </div>
    </div>
  );
}
