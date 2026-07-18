import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Menu, X } from "lucide-react";
import { api, type Client, type Alert, type Overview, type PopularQuestion } from "./lib/api";
import { useChat } from "./hooks/useChat";
import { useConversations } from "./hooks/useConversations";
import { Sidebar } from "./components/Sidebar";
import type { ConversationActions } from "./components/ConversationItem";
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
  const [drawerOpen, setDrawerOpen] = useState(false); // mobile sidebar drawer

  const conversations = useConversations(activeId);
  const chat = useChat({
    clientId: activeId,
    persistKey: "sema:chat",
    // Refresh the sidebar whenever a turn creates or updates a conversation.
    onConversationChanged: conversations.refresh,
  });
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

  const sendQuestion = useCallback((q: string) => chat.send(q), [chat]);

  // New chat: clear the view (previous conversations stay in the sidebar) and
  // close the mobile drawer.
  const newChat = useCallback(() => {
    chat.reset();
    setDrawerOpen(false);
  }, [chat]);

  // Reopen a stored conversation with its full transcript.
  const openConversation = useCallback(
    (id: string) => {
      void chat.openConversation(id);
      setDrawerOpen(false);
    },
    [chat],
  );

  const conversationActions: ConversationActions = {
    onOpen: openConversation,
    onRename: conversations.rename,
    onTogglePin: conversations.togglePin,
    // Archiving or deleting the conversation that's currently open leaves the
    // chat view showing an orphan, so clear it back to a new chat.
    onArchive: (id) => {
      conversations.archive(id);
      if (id === chat.conversationId) chat.reset();
    },
    onDelete: (id) => {
      conversations.remove(id);
      if (id === chat.conversationId) chat.reset();
    },
  };

  const onDrill = useCallback((ctx: DrillContext) => setDrill(ctx), []);
  const onRetry = useCallback((i: number) => chat.retry(i), [chat]);

  const onAlertClick = useCallback(
    (a: Alert) => chat.send(`Why is "${a.alert_label}" flagged right now? ${a.message}`),
    [chat],
  );

  const empty = chat.turns.length === 0;

  const sidebar = (
    <Sidebar
      clients={clients}
      activeId={activeId}
      onClientChange={switchClient}
      suggested={activeClient?.suggested_questions ?? []}
      popularQuestions={popularQuestions}
      conversations={conversations.conversations}
      activeConversationId={chat.conversationId}
      conversationsLoading={conversations.loading}
      conversationsError={conversations.error}
      conversationActions={conversationActions}
      onPick={sendQuestion}
      onNewConversation={newChat}
      dbConnected={dbConnected}
    />
  );

  return (
    <div className="flex h-screen bg-bg text-ink">
      {/* Desktop: persistent sidebar. */}
      <div className="hidden md:block">{sidebar}</div>

      {/* Mobile: off-canvas drawer + backdrop, mounted only while open.
          Uses a slide-in KEYFRAME (not a state-toggled transition): the same
          choice index.css documents for the drill panel -- a toggled transform
          transition can leave a fixed element stuck off-screen, whereas a
          keyframe's resting state is on-screen. */}
      {drawerOpen && (
        <div className="md:hidden">
          <div
            className="fixed inset-0 z-40 bg-ink/25 animate-[sema-fade-in_0.2s_ease-out]"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="fixed inset-y-0 start-0 z-50 animate-[sema-slide-in-left_0.2s_ease-out]">
            {sidebar}
          </div>
        </div>
      )}

      <main className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center justify-between px-5 md:px-8 py-5 border-b border-line bg-bg/80 backdrop-blur">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setDrawerOpen((o) => !o)}
              aria-label="Toggle chat history"
              className="md:hidden w-9 h-9 -ms-1 rounded-lg flex items-center justify-center text-ink hover:bg-surfaceAlt transition"
            >
              {drawerOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">SEMA</h1>
              <p className="text-sm text-muted">Ask your business anything.</p>
            </div>
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
            <ChatInput
              onSend={sendQuestion}
              onStop={chat.stop}
              loading={chat.loading}
              suggestion={chat.followUp}
            />
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
