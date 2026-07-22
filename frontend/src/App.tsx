import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { AlertTriangle, Menu, X } from "lucide-react";
import { api, type Client, type Alert, type Brief, type Overview, type PopularQuestion } from "./lib/api";
import { useChat } from "./hooks/useChat";
import { useChatScroll } from "./hooks/useChatScroll";
import { useConversations } from "./hooks/useConversations";
import { useThreads } from "./hooks/useThreads";
import { ScrollToLatest } from "./components/ScrollToLatest";
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
  const [brief, setBrief] = useState<Brief | null>(null);
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
  const { scrollRef, lastAnswerRef, onScroll, showScrollToLatest, scrollToLatest, reattach } =
    useChatScroll(chat.turns);
  // Drill-down thread summaries for the open conversation -- badges widgets
  // that already have a follow-up thread, and lets onDrill (below) resolve
  // which thread to resume when one exists.
  const threads = useThreads(activeId, chat.conversationId);

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

  // The Daily Brief reads the SAME activePeriod the overview does, in its own
  // effect: a slow or failing brief must never delay or blank the KPI cards.
  // A brief that can't load degrades to "no comparison available" rather than
  // an error, since it is supplementary to the rest of the home screen.
  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    setBrief(null); // skeleton while this client's / period's brief loads
    api
      .brief(activeId, activePeriod?.start, activePeriod?.end)
      .then((b) => !cancelled && setBrief(b))
      .catch(
        () =>
          !cancelled &&
          setBrief({
            client_id: activeId,
            as_of: null,
            period: { start: null, end: null },
            comparison_period: null,
            comparison_available: false,
            unavailable_reason: "unavailable",
            insights: [],
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [activeId, activePeriod]);

  const onPeriodChange = useCallback(
    (start: string, end: string) => setPeriod({ clientId: activeId, start, end }),
    [activeId],
  );

  const activeClient = clients.find((c) => c.id === activeId);

  const switchClient = useCallback(
    (id: string) => {
      chat.reset();
      setActiveId(id);
    },
    [chat],
  );

  // Sending or retrying is an explicit "show me what happens next", so it
  // always resumes following the bottom regardless of where the user scrolled.
  const sendQuestion = useCallback(
    (q: string) => {
      reattach();
      chat.send(q);
    },
    [chat, reattach],
  );

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

  // Widgets embed their own anchor (conversationId + turnIndex) when they
  // have one; here we resolve whether that anchor ALREADY has a thread, so
  // DrillChat can load it instead of starting empty. A ctx with no anchor
  // (the home dashboard's ephemeral KPIs) passes through unchanged -- there is
  // nothing to look up and nothing will be persisted.
  const onDrill = useCallback(
    (ctx: DrillContext) => {
      if (ctx.conversationId !== undefined && ctx.turnIndex !== undefined) {
        const existing = threads.find(ctx.turnIndex, ctx.kind, ctx.title);
        setDrill({ ...ctx, threadId: existing?.id });
      } else {
        setDrill(ctx);
      }
    },
    // Depending on threads.find (not the whole `threads` object, a fresh
    // literal every render) is deliberate: threads.find's own identity is
    // already stable via useCallback inside useThreads, so this only changes
    // when the summaries it reads actually change. Depending on `threads`
    // itself would make onDrill's identity churn every render and defeat
    // TurnView's memoization for every past turn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [threads.find],
  );
  const onRetry = useCallback(
    (i: number) => {
      reattach();
      chat.retry(i);
    },
    [chat, reattach],
  );

  const onAlertClick = useCallback(
    (a: Alert) => chat.send(`Why is "${a.alert_label}" flagged right now? ${a.message}`),
    [chat],
  );

  const empty = chat.turns.length === 0;

  const renderSidebar = () => (
    <Sidebar
      clients={clients}
      activeClientId={activeId}
      dbConnected={dbConnected}
      conversations={conversations.conversations}
      activeConversationId={chat.conversationId}
      conversationsLoading={conversations.loading}
      conversationsError={conversations.error}
      conversationActions={conversationActions}
      onSwitchClient={switchClient}
      onNewConversation={newChat}
      onGoHome={newChat}
    />
  );

  return (
    <div className="flex h-screen bg-bg text-ink">
      {/* Desktop: persistent, always-visible sidebar. */}
      <div className="hidden md:block">{renderSidebar()}</div>

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
            {renderSidebar()}
          </div>
        </div>
      )}

      <main className="flex-1 flex flex-col min-w-0">
        {/* Title block only. The active client and its connection status now
            live in the sidebar's bottom workspace switcher, so identity sits
            with navigation instead of being split across two corners. */}
        <header className="flex items-center px-5 md:px-8 py-5 border-b border-line bg-bg/80 backdrop-blur">
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

        {/* relative: anchors the floating "back to latest" button. */}
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="relative flex-1 overflow-auto sema-scroll px-8 py-6"
        >
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
                brief={brief}
                popularQuestions={popularQuestions}
                dbConnected={dbConnected}
                agentConfigured={agentConfigured}
                onPick={sendQuestion}
                onDrill={onDrill}
                onInvestigate={onAlertClick}
                onPeriodChange={onPeriodChange}
              />
            )}

            {chat.turns.map((turn, i) => (
              <TurnView
                key={i}
                turn={turn}
                index={i}
                isFirst={i === 0}
                popularQuestions={popularQuestions}
                answerRef={i === chat.turns.length - 1 ? lastAnswerRef : undefined}
                conversationId={chat.conversationId ?? undefined}
                getThreadCount={threads.getThreadCount}
                onDrill={onDrill}
                onRetry={onRetry}
                // Clarification choices / cannot-answer alternatives continue
                // the SAME conversation (chat.send keeps conversation_id).
                onAsk={sendQuestion}
              />
            ))}
          </div>
          {showScrollToLatest && <ScrollToLatest onClick={scrollToLatest} />}
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
          <DrillChat
            widget={drill}
            clientId={activeId}
            onClose={() => setDrill(null)}
            onThreadUpdated={threads.refresh}
          />
        </Suspense>
      )}
    </div>
  );
}
