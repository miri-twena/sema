import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api, type Client, type Alert } from "./lib/api";
import { useChat } from "./hooks/useChat";
import { Sidebar } from "./components/Sidebar";
import { AlertsPanel } from "./components/AlertsPanel";
import { ChatInput } from "./components/ChatInput";
import { TurnView } from "./components/TurnView";
import type { DrillContext } from "./components/DrillChat";

// Recharts + the drill panel are the heaviest parts; load them on demand.
const DrillChat = lazy(() => import("./components/DrillChat").then((m) => ({ default: m.DrillChat })));

export default function App() {
  const [clients, setClients] = useState<Client[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [dbConnected, setDbConnected] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [drill, setDrill] = useState<DrillContext | null>(null);

  const chat = useChat({ clientId: activeId, persistKey: "sema:chat" });
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.health()
      .then((h) => {
        setDbConnected(h.db_connected);
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
  }, [activeId]);

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
        onPick={chat.send}
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
              <div className="text-center py-20">
                <div className="inline-block w-14 h-14 rounded-2xl bg-gradient-to-br from-primary via-sky to-mint mb-4" />
                <div className="text-lg font-semibold">Ask your business anything.</div>
                <div className="text-sm text-muted mt-1">Pick a question from the sidebar, or type one below.</div>
              </div>
            )}

            {chat.turns.map((turn, i) => (
              <TurnView key={i} turn={turn} index={i} isFirst={i === 0} onDrill={onDrill} onRetry={onRetry} />
            ))}
          </div>
        </div>

        <div className="px-8 py-4 border-t border-line bg-bg">
          <div className="max-w-3xl mx-auto">
            <ChatInput onSend={chat.send} onStop={chat.stop} loading={chat.loading} />
          </div>
        </div>
      </main>

      <AlertsPanel alerts={alerts} onAlertClick={onAlertClick} />

      {drill && (
        <Suspense fallback={null}>
          <DrillChat widget={drill} clientId={activeId} onClose={() => setDrill(null)} />
        </Suspense>
      )}
    </div>
  );
}
