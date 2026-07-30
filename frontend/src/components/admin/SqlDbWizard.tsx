import { useState } from "react";
import { AlertTriangle, Check, Loader2, X } from "lucide-react";
import { useDismiss } from "../../hooks/useDismiss";
import { api, ApiError, type SqlConnectorType, type TestConnectionResponse } from "../../lib/api";
import { useToast } from "./toast-context";

const DEFAULT_PORT: Record<SqlConnectorType, number> = { postgres: 5432, mysql: 3306, mssql: 1433 };
const LABEL: Record<SqlConnectorType, string> = { postgres: "PostgreSQL", mysql: "MySQL", mssql: "Microsoft SQL Server" };

type Step = "details" | "test" | "schema" | "done";

const inputClass =
  "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-primary disabled:opacity-60 transition";
const labelClass = "block text-[0.78rem] font-medium text-ink mb-1";

/**
 * The self-service SQL DB connection wizard (data_sources_add_prompt.md
 * Path A). 4 steps: connection details -> test (with a write-permission
 * warning + ready-to-copy read-only-user SQL when needed) -> schema review
 * -> done. Credentials are write-only: this component never re-displays a
 * password once typed, and the server never returns one back.
 */
export function SqlDbWizard({
  connectorType,
  onClose,
  onDone,
}: {
  connectorType: SqlConnectorType;
  onClose: () => void;
  onDone: () => void;
}) {
  const ref = useDismiss<HTMLDivElement>(true, onClose);
  const toast = useToast();
  const [step, setStep] = useState<Step>("details");

  const [displayName, setDisplayName] = useState(LABEL[connectorType]);
  const [host, setHost] = useState("");
  const [port, setPort] = useState(DEFAULT_PORT[connectorType]);
  const [database, setDatabase] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [sslEnabled, setSslEnabled] = useState(false);

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestConnectionResponse | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);

  const [primaryTable, setPrimaryTable] = useState("");
  const [primaryDateField, setPrimaryDateField] = useState("");
  const [saving, setSaving] = useState(false);

  const detailsValid = host.trim() && port > 0 && database.trim() && username.trim() && password.trim() && displayName.trim();

  const runTest = async () => {
    setTesting(true);
    setTestResult(null);
    setAcknowledged(false);
    try {
      const result = await api.admin.dataSources.test({
        connector_type: connectorType, host: host.trim(), port, database: database.trim(),
        username: username.trim(), password, ssl_enabled: sslEnabled,
      });
      setTestResult(result);
      setStep("test");
    } catch {
      setTestResult({ ok: false, tables: [], write_access: null, error: "Couldn't reach the server. Try again.", readonly_user_sql: null });
      setStep("test");
    } finally {
      setTesting(false);
    }
  };

  const canContinueFromTest = testResult?.ok && (!testResult.write_access || acknowledged);

  const finish = async () => {
    setSaving(true);
    try {
      await api.admin.dataSources.createConnection({
        connector_type: connectorType, display_name: displayName.trim(), host: host.trim(), port,
        database: database.trim(), username: username.trim(), password, ssl_enabled: sslEnabled,
        primary_table: primaryTable || null, primary_date_field: primaryDateField || null,
        write_access_acknowledged: acknowledged,
      });
      setStep("done");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Couldn't save this connection. Try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/25 animate-[sema-fade-in_0.2s_ease-out]" onClick={onClose} aria-hidden />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        className="relative w-full max-w-lg rounded-xl2 border border-line bg-surface shadow-pop p-5"
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h2 className="text-base font-semibold text-ink">Connect {LABEL[connectorType]}</h2>
            <p className="text-[0.78rem] text-muted mt-0.5">
              Step {["details", "test", "schema", "done"].indexOf(step) + 1} of 4
            </p>
          </div>
          <button onClick={onClose} aria-label="Close" className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-muted hover:bg-surfaceAlt hover:text-ink transition">
            <X size={18} />
          </button>
        </div>

        {step === "details" && (
          <div className="flex flex-col gap-3">
            <div>
              <label className={labelClass} htmlFor="db-display-name">Display name</label>
              <input id="db-display-name" className={inputClass} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </div>
            <div className="grid grid-cols-[1fr_auto] gap-3">
              <div>
                <label className={labelClass} htmlFor="db-host">Host</label>
                <input id="db-host" dir="ltr" className={inputClass} value={host} onChange={(e) => setHost(e.target.value)} placeholder="db.example.com" />
              </div>
              <div className="w-24">
                <label className={labelClass} htmlFor="db-port">Port</label>
                <input id="db-port" dir="ltr" type="number" className={inputClass} value={port} onChange={(e) => setPort(Number(e.target.value) || 0)} />
              </div>
            </div>
            <div>
              <label className={labelClass} htmlFor="db-database">Database</label>
              <input id="db-database" dir="ltr" className={inputClass} value={database} onChange={(e) => setDatabase(e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelClass} htmlFor="db-username">Username</label>
                <input id="db-username" dir="ltr" className={inputClass} value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div>
                <label className={labelClass} htmlFor="db-password">Password</label>
                <input id="db-password" dir="ltr" type="password" className={inputClass} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
              </div>
            </div>
            <label className="flex items-center gap-2 text-[0.8rem] text-ink cursor-pointer">
              <input type="checkbox" checked={sslEnabled} onChange={(e) => setSslEnabled(e.target.checked)} className="w-4 h-4 rounded border-line accent-primary" />
              Require SSL
            </label>
            <button
              type="button"
              onClick={runTest}
              disabled={!detailsValid || testing}
              className="mt-2 w-full inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50 transition"
            >
              {testing ? <Loader2 size={15} className="animate-spin" /> : null}
              {testing ? "Testing…" : "Test connection"}
            </button>
          </div>
        )}

        {step === "test" && testResult && (
          <div className="flex flex-col gap-3">
            {testResult.ok ? (
              <div className="flex items-start gap-2.5 rounded-lg border border-line bg-primary/[0.04] px-3 py-2.5">
                <Check size={16} className="shrink-0 mt-0.5 text-emerald-600" />
                <p className="text-[0.82rem] text-ink">
                  Connected — found {testResult.tables.length} table{testResult.tables.length === 1 ? "" : "s"}.
                </p>
              </div>
            ) : (
              <div className="flex items-start gap-2.5 rounded-lg border border-critical-fg/25 bg-critical-bg px-3 py-2.5">
                <AlertTriangle size={16} className="shrink-0 mt-0.5 text-critical-fg" />
                <p className="text-[0.82rem] text-ink">{testResult.error}</p>
              </div>
            )}

            {testResult.ok && testResult.write_access && (
              <div className="rounded-lg border border-warning-fg/30 bg-warning-bg/40 px-3 py-2.5">
                <p className="text-[0.8rem] font-medium text-ink flex items-center gap-1.5">
                  <AlertTriangle size={14} className="shrink-0 text-warning-fg" /> This user has write access
                </p>
                <p className="text-[0.75rem] text-muted mt-1">
                  For safety, connect with a read-only user instead. Here's a ready-to-run snippet:
                </p>
                <pre dir="ltr" className="mt-2 rounded-md bg-ink/5 p-2 text-[0.68rem] text-ink overflow-auto whitespace-pre-wrap">
                  {testResult.readonly_user_sql}
                </pre>
                <label className="flex items-start gap-2 text-[0.78rem] text-ink cursor-pointer mt-2">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={(e) => setAcknowledged(e.target.checked)}
                    className="mt-0.5 w-4 h-4 rounded border-line accent-primary"
                  />
                  I understand the risk and want to continue with this user anyway.
                </label>
              </div>
            )}

            <div className="flex gap-2 mt-2">
              <button
                type="button"
                onClick={() => setStep("details")}
                className="rounded-lg border border-line px-3 py-1.5 text-[0.82rem] text-ink hover:bg-surfaceAlt transition"
              >
                Back
              </button>
              {testResult.ok && (
                <button
                  type="button"
                  onClick={() => setStep("schema")}
                  disabled={!canContinueFromTest}
                  className="flex-1 rounded-lg bg-primary px-3 py-1.5 text-[0.82rem] font-medium text-white hover:bg-primary/90 disabled:opacity-50 transition"
                >
                  Continue
                </button>
              )}
              {!testResult.ok && (
                <button
                  type="button"
                  onClick={runTest}
                  className="flex-1 rounded-lg bg-primary px-3 py-1.5 text-[0.82rem] font-medium text-white hover:bg-primary/90 transition"
                >
                  Try again
                </button>
              )}
            </div>
          </div>
        )}

        {step === "schema" && testResult && (
          <div className="flex flex-col gap-3">
            <p className="text-[0.8rem] text-muted">
              {testResult.tables.length} table{testResult.tables.length === 1 ? "" : "s"} found. Optionally pick the
              main one SEMA should use for "data age" freshness readings.
            </p>
            <div>
              <label className={labelClass} htmlFor="db-primary-table">Primary table (optional)</label>
              <select
                id="db-primary-table"
                className={inputClass}
                value={primaryTable}
                onChange={(e) => setPrimaryTable(e.target.value)}
              >
                <option value="">None</option>
                {testResult.tables.map((tbl) => (
                  <option key={tbl} value={tbl}>{tbl}</option>
                ))}
              </select>
            </div>
            {primaryTable && (
              <div>
                <label className={labelClass} htmlFor="db-primary-date-field">Date column (optional)</label>
                <input
                  id="db-primary-date-field"
                  dir="ltr"
                  className={inputClass}
                  value={primaryDateField}
                  onChange={(e) => setPrimaryDateField(e.target.value)}
                  placeholder="e.g. created_at"
                />
              </div>
            )}
            <div className="flex gap-2 mt-2">
              <button
                type="button"
                onClick={() => setStep("test")}
                className="rounded-lg border border-line px-3 py-1.5 text-[0.82rem] text-ink hover:bg-surfaceAlt transition"
              >
                Back
              </button>
              <button
                type="button"
                onClick={finish}
                disabled={saving}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-3 py-1.5 text-[0.82rem] font-medium text-white hover:bg-primary/90 disabled:opacity-50 transition"
              >
                {saving ? <Loader2 size={14} className="animate-spin" /> : null}
                {saving ? "Saving…" : "Save connection"}
              </button>
            </div>
          </div>
        )}

        {step === "done" && (
          <div className="flex flex-col items-center gap-3 py-4 text-center">
            <span className="inline-flex items-center justify-center w-11 h-11 rounded-full bg-emerald-50 text-emerald-600">
              <Check size={22} />
            </span>
            <p className="text-[0.85rem] text-ink">{displayName} is connected and live.</p>
            <button
              type="button"
              onClick={onDone}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 transition"
            >
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
