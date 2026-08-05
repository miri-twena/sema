import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Menu, X } from "lucide-react";
import {
  api,
  resolveApiUrl,
  type AdminUser,
  type Client,
  type Alert,
  type DailyBrief as DailyBriefResponse,
  type ImpersonationState,
  type Overview,
  type PopularQuestion,
  type PublicOrgSettings,
} from "./lib/api";
import { ImpersonationBanner } from "./components/ImpersonationBanner";
import { configureFormatting } from "./lib/format";
import { detectBrowserLang } from "./lib/loginCopy";
import { firstUserMessage } from "./lib/conversations";
import { shouldFocusAskInput } from "./lib/homeShortcut";
import { useChat } from "./hooks/useChat";
import { useChatScroll } from "./hooks/useChatScroll";
import { useConversations } from "./hooks/useConversations";
import { useProtectedImageSrc } from "./hooks/useProtectedImageSrc";
import { useThreads } from "./hooks/useThreads";
import { ScrollToLatest } from "./components/ScrollToLatest";
import { Sidebar } from "./components/Sidebar";
import type { ConversationActions } from "./components/ConversationItem";
import { ChatInput } from "./components/ChatInput";
import { HomeDashboard } from "./components/HomeDashboard";
import { NewConversationCanvas } from "./components/NewConversationCanvas";
import { TurnView } from "./components/TurnView";
import type { DrillContext } from "./components/DrillChat";

// Recharts + the drill panel are the heaviest parts; load them on demand.
const DrillChat = lazy(() => import("./components/DrillChat").then((m) => ({ default: m.DrillChat })));
// The admin panel is a separate full-page surface -- lazy so its screens and
// their code never weigh on the main chat bundle (same rationale as DrillChat).
const AdminPanel = lazy(() => import("./components/admin/AdminPanel").then((m) => ({ default: m.AdminPanel })));

export default function App() {
  const [clients, setClients] = useState<Client[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [popularQuestions, setPopularQuestions] = useState<PopularQuestion[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [brief, setBrief] = useState<DailyBriefResponse | null>(null);
  const [orgSettings, setOrgSettings] = useState<PublicOrgSettings | null>(null);
  // Fetched WITH the pilot access key and re-served as a blob URL -- the
  // logo lives behind a protected /api/* route, and a plain <img src> can't
  // carry a custom header (see useProtectedImageSrc's docstring).
  const orgLogoUrl = useProtectedImageSrc(resolveApiUrl(orgSettings?.logo_path ?? null));
  const [me, setMe] = useState<AdminUser | null>(null);
  // impersonation_prompt.md: fetched once at boot (the frontend polls
  // nothing new -- Start/Stop each hard-reload the whole app, so a fresh
  // GET here on every real page load is all that's needed). Resolved
  // against the REAL admin identity server-side, so this still answers
  // correctly even while `me` above is null (impersonating a non-admin
  // makes GET /api/admin/me 403, but this endpoint stays reachable).
  const [impersonation, setImpersonation] = useState<ImpersonationState | null>(null);
  // The user's chosen period, tagged with the client it belongs to -- so
  // switching clients falls back to that client's default (its latest
  // complete month) instead of carrying over a period it may not even have.
  const [period, setPeriod] = useState<{ clientId: string; start: string; end: string } | null>(null);
  const [dbConnected, setDbConnected] = useState(true);
  const [agentConfigured, setAgentConfigured] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [drill, setDrill] = useState<DrillContext | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false); // mobile sidebar drawer
  const [adminOpen, setAdminOpen] = useState(false); // organization admin panel
  // Which empty-state screen to show (new_conversation_canvas_prompt.md):
  // "home" is the dashboard (brief/KPIs/etc, home_ask_bar_top_prompt.md's own
  // ask bar); "canvas" is the clean ask-only screen "New conversation" opens.
  // Both are gated on chat.turns being empty (see showHome/showCanvas below)
  // -- this state only decides WHICH of the two to show when that's true.
  // Defaults to "home" so a fresh load/refresh always lands there (item 8's
  // "home is the app's anchor" rule).
  const [homeView, setHomeView] = useState<"home" | "canvas">("home");

  const conversations = useConversations(activeId);
  const chat = useChat({
    clientId: activeId,
    // Home is the app's anchor (home_hebrew_polish_prompt.md item 8): every
    // fresh load/refresh always lands there, never auto-reopening whatever
    // conversation was on screen last -- the sidebar (a real server fetch
    // via openConversation) is how you return to one. No persistKey means
    // no localStorage restore-on-mount at all, not just a cleared one (a
    // reset()-on-mount would still flash the old transcript for one paint
    // before clearing it, since the hook's initial state reads localStorage
    // synchronously on first render).
    persistKey: null,
    // Refresh the sidebar whenever a turn creates or updates a conversation.
    onConversationChanged: conversations.refresh,
  });
  const { scrollRef, lastAnswerRef, onScroll, showScrollToLatest, scrollToLatest, reattach } =
    useChatScroll(chat.turns);
  // Drill-down thread summaries for the open conversation -- badges widgets
  // that already have a follow-up thread, and lets onDrill (below) resolve
  // which thread to resume when one exists.
  const threads = useThreads(activeId, chat.conversationId);

  // UI-chrome language (org_settings_gapfix_prompt.md Part 2) -- browser
  // default until the org is identified, matching the login page's own
  // precedence (lib/loginCopy.detectBrowserLang). Sets ONLY <html lang> for
  // now (screen-reader pronunciation, spell-check) -- see AGENTS.md's Agent
  // Voice "Layout is anchored" rule: the shell/body must NEVER flip to
  // dir="rtl" even when the org's chrome language is Hebrew (sidebar always
  // left; no chrome string translation exists yet either). Per-message
  // direction is unaffected either way: each turn keeps setting its OWN dir
  // from the question (see useChat.ts/lib/rtl.ts), independent of chrome.
  useEffect(() => {
    document.documentElement.lang = detectBrowserLang(navigator.language);
  }, []);

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

  // The signed-in person's identity (mock today, real once auth Part A
  // lands) -- same endpoint UserFooter's sidebar row already reads, fetched
  // independently here so the home greeting doesn't have to reach across
  // components for it. A failed/unresolved fetch just keeps `me` null,
  // which HomeDashboard treats as "fall back to the org name."
  useEffect(() => {
    let cancelled = false;
    api.admin
      .me()
      .then((u) => !cancelled && setMe(u))
      .catch(() => !cancelled && setMe(null));
    return () => {
      cancelled = true;
    };
  }, []);

  // impersonation_prompt.md: the app-wide banner's data, fetched once at
  // boot alongside `me` above. A failed/unresolved fetch just keeps it null
  // (banner renders nothing), same fallback style as `me`.
  useEffect(() => {
    let cancelled = false;
    api.admin.impersonation
      .state()
      .then((s) => !cancelled && setImpersonation(s))
      .catch(() => !cancelled && setImpersonation(null));
    return () => {
      cancelled = true;
    };
  }, []);

  // Org settings (name/logo/currency/number format) drive the sidebar brand
  // and the shared KPI/table/chart formatting util -- fetched per active
  // client, same pattern as alerts/popularQuestions above. A failed fetch
  // just keeps the built-in defaults (US-style "$", initials avatar) rather
  // than breaking the app.
  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    api
      .orgSettings(activeId)
      .then((s) => {
        if (cancelled) return;
        setOrgSettings(s);
        configureFormatting(s);
        // Org setting wins over the browser-default fallback above, once
        // known -- lang only, never dir (see the mount effect's comment).
        document.documentElement.lang = s.language;
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
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

  // The Daily Brief runs in its own effect: a slow or failing brief must
  // never delay or blank the KPI cards. Unlike the overview, it is NOT
  // period-scoped -- it always describes "since yesterday", so it only
  // refetches when the client changes, never when the period picker does.
  // A brief that can't load degrades to an empty one (the section hides
  // itself) rather than an error, since it is supplementary to the home screen.
  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    setBrief(null); // skeleton while this client's brief loads
    api
      .brief(activeId)
      .then((b) => !cancelled && setBrief(b))
      .catch(
        () => !cancelled && setBrief({ client_id: activeId, as_of: null, pulse: [], insights: [] }),
      );
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const onPeriodChange = useCallback(
    (start: string, end: string) => setPeriod({ clientId: activeId, start, end }),
    [activeId],
  );

  const activeClient = clients.find((c) => c.id === activeId);
  // First whitespace-separated token of the signed-in person's display name
  // (greeting_user_name_prompt.md): "Miri Levi" -> "Miri". Falls back to the
  // org name below whenever the identity hasn't resolved or has no name set.
  const userFirstName = me?.name?.trim().split(/\s+/)[0] || null;

  const switchClient = useCallback(
    (id: string) => {
      chat.reset();
      setHomeView("home");
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

  // The wordmark/"Back to SEMA" action (home_hebrew_polish_prompt.md item 8):
  // clear the view (previous conversations stay in the sidebar), close the
  // mobile drawer, and land on the DASHBOARD specifically -- distinct from
  // "New conversation" below, which lands on the clean ask canvas instead.
  const goHome = useCallback(() => {
    chat.reset();
    setHomeView("home");
    setDrawerOpen(false);
  }, [chat]);

  // Sidebar's "+ New conversation" (new_conversation_canvas_prompt.md): same
  // reset, but opens the clean ask-only canvas instead of the dashboard --
  // the two are separate entry points into the same empty chat state.
  const startNewConversation = useCallback(() => {
    chat.reset();
    setHomeView("canvas");
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

  // Rerun (rerun_conversation_prompt.md): fetch the source conversation's
  // FIRST user message (MVP scope -- it's what defines the chat; replaying
  // every follow-up would drift, since they depend on earlier answers) and
  // submit it fresh through the normal ask flow in a brand-NEW conversation.
  // `chat.reset()` clears the current view/conversationId synchronously (it
  // writes conversationIdRef, not just state) so the immediately-following
  // `chat.send()` is guaranteed to start a new server conversation rather
  // than appending to whatever was open. The source conversation (and its
  // drill threads, which belong to ITS widgets) are never touched.
  const rerunConversation = useCallback(
    async (id: string) => {
      const detail = await api.conversation(id, activeId).catch(() => null);
      const firstQuestion = detail && firstUserMessage(detail);
      if (!firstQuestion) return;
      chat.reset();
      reattach();
      chat.send(firstQuestion);
      setDrawerOpen(false);
    },
    [activeId, chat, reattach],
  );

  const conversationActions: ConversationActions = {
    onOpen: openConversation,
    onRename: conversations.rename,
    onTogglePin: conversations.togglePin,
    // Archiving or deleting the conversation that's currently open leaves the
    // chat view showing an orphan, so clear it back to a new chat -- HOME
    // specifically (a sensible default now that home/canvas are two separate
    // screens), not whichever one happened to be selected last.
    onArchive: (id) => {
      conversations.archive(id);
      if (id === chat.conversationId) {
        chat.reset();
        setHomeView("home");
      }
    },
    onUnarchive: conversations.unarchive,
    onDelete: (id) => {
      conversations.remove(id);
      if (id === chat.conversationId) {
        chat.reset();
        setHomeView("home");
      }
    },
    onRerun: (id) => void rerunConversation(id),
  };

  // Same actions, but for rows in the sidebar's separate "Archived" view: a
  // delete there must clear the ARCHIVED list's local state, not the main
  // (non-archived) one -- otherwise the row lingers until the view is reopened.
  const archivedConversationActions: ConversationActions = {
    ...conversationActions,
    onDelete: (id) => {
      conversations.removeArchived(id);
      if (id === chat.conversationId) {
        chat.reset();
        setHomeView("home");
      }
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
  const showHome = empty && !chat.loading && homeView === "home";
  const showCanvas = empty && !chat.loading && homeView === "canvas";

  // "/" focuses the hero ask input on EITHER empty-state screen (home
  // dashboard: home_ask_bar_top_prompt.md item 5; the ask canvas:
  // new_conversation_canvas_prompt.md, which reuses the same shortcut) from
  // anywhere on the page, EXCEPT: not while a modal/drawer is covering it
  // (the mobile sidebar drawer or the drill-down panel -- the admin panel
  // returns early above and unmounts this whole tree, so it never needs
  // checking here), and never while focus is already inside an
  // input/textarea/contenteditable (typing "/" into the search box, a
  // textarea, etc. must type the character, not hijack focus).
  const askInputRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!showHome && !showCanvas) return;
    const onKey = (e: KeyboardEvent) => {
      const active = document.activeElement;
      const shouldFocus = shouldFocusAskInput({
        key: e.key,
        metaKey: e.metaKey,
        ctrlKey: e.ctrlKey,
        altKey: e.altKey,
        modalOpen: drawerOpen || !!drill,
        activeElementTag: active?.tagName,
        activeElementEditable: !!(active as HTMLElement | null)?.isContentEditable,
      });
      if (!shouldFocus) return;
      e.preventDefault();
      askInputRef.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showHome, showCanvas, drawerOpen, drill]);

  const renderSidebar = () => (
    <Sidebar
      clients={clients}
      activeClientId={activeId}
      dbConnected={dbConnected}
      orgLogoUrl={orgLogoUrl}
      conversations={conversations.conversations}
      activeConversationId={chat.conversationId}
      conversationsLoading={conversations.loading}
      conversationsError={conversations.error}
      archivedConversations={conversations.archived}
      archivedLoading={conversations.archivedLoading}
      onLoadArchived={conversations.loadArchived}
      conversationActions={conversationActions}
      archivedActions={archivedConversationActions}
      onSwitchClient={switchClient}
      onNewConversation={startNewConversation}
      onGoHome={goHome}
      // impersonation_prompt.md: hide the admin gear while impersonating a
      // non-admin -- GET /api/admin/me 403s in that case (require_client_admin
      // resolves the TARGET's own, lesser role), so `me` is already null; the
      // gear simply follows the same signal rather than needing its own.
      onOpenAdmin={
        me?.role === "client_admin"
          ? () => {
              setAdminOpen(true);
              setDrawerOpen(false);
            }
          : undefined
      }
    />
  );

  // impersonation_prompt.md: the persistent "seatbelt" banner, shown above
  // BOTH the admin panel and the chat shell below -- an app-wide concern, not
  // scoped to either surface.
  const banner = impersonation?.active ? <ImpersonationBanner state={impersonation} /> : null;

  // The admin panel is its own full-page surface (spec §4: "opens as a full
  // page, not a modal"), so it replaces the whole chat shell rather than
  // overlaying it. State-based, like the rest of the app's navigation.
  if (adminOpen) {
    return (
      <div className="flex flex-col h-screen bg-bg">
        {banner}
        <div className="flex-1 min-h-0">
          <Suspense fallback={<div className="h-full bg-bg" />}>
            <AdminPanel
              clientLabel={activeClient?.label ?? ""}
              onClose={() => {
                // "Back to SEMA" aligns with the rest of the app's brand-wordmark
                // navigation (home_hebrew_polish_prompt.md item 8): it lands on
                // HOME, not just whatever chat state happened to be underneath.
                goHome();
                setAdminOpen(false);
              }}
            />
          </Suspense>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-bg text-ink">
      {banner}
      <div className="flex flex-1 min-h-0">
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
        {/* Mobile-only drawer toggle. The title bar (SEMA heading + tagline)
            that used to live here is gone -- identity/navigation already
            live in the sidebar's brand button and bottom workspace switcher,
            and the bar was pure vertical space above the fold. No bar
            styling (border/backdrop) on purpose: this row shouldn't read as
            a header on mobile, just a floating control. */}
        <div className="md:hidden px-5 py-3">
          <button
            onClick={() => setDrawerOpen((o) => !o)}
            aria-label="Toggle chat history"
            className="w-9 h-9 -ms-1 rounded-lg flex items-center justify-center text-ink hover:bg-surfaceAlt transition"
          >
            {drawerOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>

        {/* relative: anchors the floating "back to latest" button. */}
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="relative flex-1 overflow-auto sema-scroll px-8 py-6"
        >
          <div className="max-w-3xl xl:max-w-5xl 2xl:max-w-6xl mx-auto">
            {loadError && (
              <div className="mb-4 flex items-center gap-2 rounded-xl border border-critical-fg/30 bg-critical-bg px-4 py-3 text-sm text-critical-fg">
                <AlertTriangle size={16} className="shrink-0" /> Couldn't reach the server. Is the API running?
              </div>
            )}

            {showHome && (
              <HomeDashboard
                clientLabel={activeClient?.label ?? ""}
                userName={userFirstName}
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
                onAsk={sendQuestion}
                onStopAsk={chat.stop}
                asking={chat.loading}
                askInputRef={askInputRef}
                autoFocusAsk
              />
            )}

            {showCanvas && (
              <NewConversationCanvas
                suggested={activeClient?.suggested_questions ?? []}
                popularQuestions={popularQuestions}
                onAsk={sendQuestion}
                onStopAsk={chat.stop}
                asking={chat.loading}
                askInputRef={askInputRef}
              />
            )}

            {chat.turns.map((turn, i) => (
              <TurnView
                key={i}
                turn={turn}
                index={i}
                isFirst={i === 0}
                answerRef={i === chat.turns.length - 1 ? lastAnswerRef : undefined}
                conversationId={chat.conversationId ?? undefined}
                getThreadCount={threads.getThreadCount}
                onDrill={onDrill}
                onRetry={onRetry}
                // Clarification choices / cannot-answer alternatives continue
                // the SAME conversation (chat.send keeps conversation_id).
                onAsk={sendQuestion}
                onFeedback={chat.setFeedback}
                clientId={activeId}
              />
            ))}
          </div>
          {showScrollToLatest && <ScrollToLatest onClick={scrollToLatest} />}
        </div>

        {/* Home and the "New conversation" canvas each have their own
            prominent ask input (home_ask_bar_top_prompt.md;
            new_conversation_canvas_prompt.md) -- one ask entry, not two, so
            this bottom bar is hidden for exactly the same two conditions
            that show those screens above. Conversation state (once a turn
            exists) is unchanged: input stays at the bottom, same as before. */}
        {!showHome && !showCanvas && (
          <div className="px-8 py-4 border-t border-line bg-bg">
            <div className="max-w-3xl xl:max-w-5xl 2xl:max-w-6xl mx-auto">
              <ChatInput
                onSend={sendQuestion}
                onStop={chat.stop}
                loading={chat.loading}
                suggestion={chat.followUp}
              />
            </div>
          </div>
        )}
      </main>

      {drill && (
        <Suspense fallback={null}>
          <DrillChat
            widget={drill}
            clientId={activeId}
            onClose={() => setDrill(null)}
            onThreadUpdated={() => {
              // A drill turn only refreshed the in-chart ThreadBadge
              // (threads.refresh) -- the sidebar's own drill_count badge
              // (ConversationItem) reads from the separate `conversations`
              // list, which nothing was telling to refresh, so it stayed
              // stale until something else happened to refetch it (a
              // top-level message, navigating home, a reload).
              threads.refresh();
              conversations.refresh();
            }}
          />
        </Suspense>
      )}
      </div>
    </div>
  );
}
