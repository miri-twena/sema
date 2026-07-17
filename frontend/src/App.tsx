import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api, type Client, type Alert, type Overview, type PopularQuestion } from "./lib/api";
import { useChat } from "./hooks/useChat";
import { useQuestionHistory } from "./hooks/useQuestionHistory";
import { Sidebar } from "./components/Sidebar";
import { ChatInput } from "./components/ChatInput";
import { HomeDashboard } from "./components/HomeDashboard";
import { TurnView } from "./components/TurnView";
import type { DrillContext } from "./components/DrillChat";

// Recharts + the drill panel are the heaviest parts; load them on demand.
const DrillChat = lazy(() => import("./components/DrillChat").then((m) => ({ default: m.DrillChat })));

export default function App() {
  const [clients, setClients] = useState<Client[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [popularQuestions, setPopularQuestions] = useState<PopularQuestion[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  // The user's chosen period, tagged with the client it belongs to -- so
  // switching clients falls back to that client's default (its latest
  // complete month) instead of carrying over a period it may not even have.
  const [period, setPeriod] = useState<{ clientId: string; start: string; end: string } | null>(null);
  const [dbConnected, setDbConnected] = useState(true);
  const [agentConfigured, setAgentConfigured] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [drill, setDrill] = useState<DrillContext | null>(null);

  const chat = useChat({ clientId: activeId, persistKey: "sema:chat" });
  const questionHistory = useQuestionHistory(activeId);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.health()
      .then((h) => {
        setDbConnected(h.db_connected);
        setAgentConfigured(h.agent_configured);
        setActiveId((cur) => cur || h.active_client);
      })
      .catch(() => setDbConnected(false));
    api.clients()
      .then((cs) => {
        setClients(cs);
        setActiveId((cur) => cur || cs[0]?.id || "");
      })
      .catch((e) => setLoadError(String(e)));
  }, []);

  useEffect(() => {
    if (!activeId) return;
    api.alerts(activeId).then(setAlerts).catch(() => setAlerts([]));
    api.popularQuestions(activeId).then(setPopularQuestions).catch(() => setPopularQuestions([]));
  }, [activeId]);

  // A period from a different client is ignored, so the server picks that
  // client's own default instead.
  const activePeriod = period && period.clientId === activeId ? period : null;

  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    setOverview(null); // skeleton while this client's / period's KPIs load
    api
      .overview(activeId, activePeriod?.start, activePeriod?.end)
      .then((o) => !cancelled && setOverview(o))
      .catch(() => !cancelled && setOverview({ client_id: activeId, kpis: [], as_of: null, start: null, end: null, available_months: [] }));
    return () => {
      cancelled = true;
    };
  }, [activeId, activePeriod]);

  const onPeriodChange = useCallback(
    (start: string, end: string) => setPeriod({ clientId: activeId, start, end }),
    [activeId],
  );

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [chat.turns, chat.loading]);

  const activeClient = clients.find((c) => c.id === activeId);

  const switchClient = useCallback(
    (id: string) => {
      chat.reset();
      setActiveId(id);
    },
    [chat],
  );

  // Top-level questions (typed or picked from the sidebar) are logged to this
  // browser's per-client history; drill-down follow-ups and alert-triggered
  // questions are scoped/synthesized, not a real "question I asked", so they
  // don't get recorded here.
  const sendQuestion = useCallback(
    (q: string) => {
      const trimmed = q.trim();
      if (trimmed) questionHistory.record(trimmed);
      chat.send(q);
    },
    [chat, questionHistory],
  );

  const onDrill = useCallback((ctx: DrillContext) => setDrill(ctx), []);
  const onRetry = useCallback((i: number) => chat.retry(i), [chat]);

  const onAlertClick = useCallback(
    (a: Alert) => chat.send(`Why is "${a.alert_label}" flagged right now? ${a.message}`),
    [chat],
  );

  const empty = chat.turns.length === 0;

  return (
    <div className="flex h-screen bg-bg text-ink">
      <Sidebar
        clients={clients}
        activeId={activeId}
        onClientChange={switchClient}
        suggested={activeClient?.suggested_questions ?? []}
        questionHistory={questionHistory.items}
        popularQuestions={popularQuestions}
        onPick={sendQuestion}
        onNewConversation={chat.reset}
        dbConnected={dbConnected}
      />

      <main className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center justify-between px-8 py-5 border-b border-line bg-bg/80 backdrop-blur">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">SEMA</h1>
            <p className="text-sm text-muted">Ask your business anything.</p>
          </div>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-auto sema-scroll px-8 py-6">
          <div className="max-w-3xl mx-auto">
            {loadError && (
              <div className="mb-4 flex items-center gap-2 rounded-xl border border-critical-fg/30 bg-critical-bg px-4 py-3 text-sm text-critical-fg">
                <AlertTriangle size={16} className="shrink-0" /> Couldn't reach the server. Is the API running?
              </div>
            )}

            {empty && !chat.loading && (
              <HomeDashboard
                clientLabel={activeClient?.label ?? ""}
                suggested={activeClient?.suggested_questions ?? []}
                alerts={alerts}
                overview={overview}
                dbConnected={dbConnected}
                agentConfigured={agentConfigured}
                onPick={sendQuestion}
                onDrill={onDrill}
                onInvestigate={onAlertClick}
                onPeriodChange={onPeriodChange}
              />
            )}

            {chat.turns.map((turn, i) => (
              <TurnView key={i} turn={turn} index={i} isFirst={i === 0} onDrill={onDrill} onRetry={onRetry} />
            ))}
          </div>
        </div>

        <div className="px-8 py-4 border-t border-line bg-bg">
          <div className="max-w-3xl mx-auto">
            <ChatInput onSend={sendQuestion} onStop={chat.stop} loading={chat.loading} />
          </div>
        </div>
      </main>

      {drill && (
        <Suspense fallback={null}>
          <DrillChat widget={drill} clientId={activeId} onClose={() => setDrill(null)} />
        </Suspense>
      )}
    </div>
  );
}
