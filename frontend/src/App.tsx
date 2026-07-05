import { useEffect, useState, useRef } from "react";
import { AlertTriangle } from "lucide-react";
import { api, type Client, type Alert, type ChatResponse, type Message } from "./lib/api";
import { isRtl } from "./lib/rtl";
import { Sidebar } from "./components/Sidebar";
import { AlertsPanel } from "./components/AlertsPanel";
import { ChatInput } from "./components/ChatInput";
import { ChatMessage } from "./components/ChatMessage";
import { AssistantResponseCard } from "./components/AssistantResponseCard";

interface Turn {
  question: string;
  response: ChatResponse | null; // null while loading
  dir: "rtl" | "ltr";
}

export default function App() {
  const [clients, setClients] = useState<Client[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [history, setHistory] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [dbConnected, setDbConnected] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  // Initial load: health + clients.
  useEffect(() => {
    api.health().then((h) => {
      setDbConnected(h.db_connected);
      setActiveId((cur) => cur || h.active_client);
    }).catch(() => setDbConnected(false));
    api.clients().then((cs) => {
      setClients(cs);
      setActiveId((cur) => cur || cs[0]?.id || "");
    }).catch((e) => setError(String(e)));
  }, []);

  // Load alerts whenever the active client changes.
  useEffect(() => {
    if (!activeId) return;
    api.alerts(activeId).then(setAlerts).catch(() => setAlerts([]));
  }, [activeId]);

  // Auto-scroll to the newest message.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, loading]);

  const activeClient = clients.find((c) => c.id === activeId);

  function switchClient(id: string) {
    setActiveId(id);
    setTurns([]);
    setHistory([]);
    setError(null);
  }

  function newConversation() {
    setTurns([]);
    setHistory([]);
    setError(null);
  }

  async function send(question: string) {
    if (loading) return;
    const dir = isRtl(question) ? "rtl" : "ltr";
    setError(null);
    setTurns((t) => [...t, { question, response: null, dir }]);
    setLoading(true);
    try {
      const resp = await api.chat(question, history, activeId);
      setTurns((t) => {
        const copy = [...t];
        copy[copy.length - 1] = { question, response: resp, dir };
        return copy;
      });
      setHistory((h) => [
        ...h,
        { role: "user", content: question },
        { role: "assistant", content: resp.answer },
      ]);
    } catch (e) {
      setTurns((t) => {
        const copy = [...t];
        copy[copy.length - 1] = {
          question,
          dir,
          response: { answer: "", kpis: [], chart: null, table: null, actions: [], sql_used: null, confidence: null, status: "error", error: String(e) },
        };
        return copy;
      });
    } finally {
      setLoading(false);
    }
  }

  const empty = turns.length === 0;

  return (
    <div className="flex h-screen bg-bg text-ink">
      <Sidebar
        clients={clients}
        activeId={activeId}
        onClientChange={switchClient}
        suggested={activeClient?.suggested_questions ?? []}
        onPick={send}
        onNewConversation={newConversation}
        dbConnected={dbConnected}
      />

      <main className="flex-1 flex flex-col min-w-0">
        {/* header */}
        <header className="flex items-center justify-between px-8 py-5 border-b border-line bg-bg/80 backdrop-blur">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">SEMA</h1>
            <p className="text-sm text-muted">Ask your business anything.</p>
          </div>
        </header>

        {/* transcript */}
        <div ref={scrollRef} className="flex-1 overflow-auto sema-scroll px-8 py-6">
          <div className="max-w-3xl mx-auto">
            {error && (
              <div className="mb-4 flex items-center gap-2 rounded-xl border border-critical-fg/30 bg-critical-bg px-4 py-3 text-sm text-critical-fg">
                <AlertTriangle size={16} className="shrink-0" /> {error}
              </div>
            )}

            {empty && !loading && (
              <div className="text-center py-20">
                <div className="inline-block w-14 h-14 rounded-2xl bg-gradient-to-br from-primary via-sky to-mint mb-4" />
                <div className="text-lg font-semibold">Ask your business anything.</div>
                <div className="text-sm text-muted mt-1">
                  Pick a question from the sidebar, or type one below.
                </div>
              </div>
            )}

            {turns.map((turn, i) => (
              <div key={i} className={i > 0 ? "border-t border-line pt-4 mt-4" : ""}>
                <ChatMessage text={turn.question} dir={turn.dir} />
                {turn.response ? (
                  <AssistantResponseCard response={turn.response} dir={turn.dir} />
                ) : (
                  <div className="flex items-center gap-2 text-sm text-muted px-1 py-3">
                    <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                    SEMA is analyzing…
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* input */}
        <div className="px-8 py-4 border-t border-line bg-bg">
          <div className="max-w-3xl mx-auto">
            <ChatInput onSend={send} disabled={loading} />
          </div>
        </div>
      </main>

      <AlertsPanel alerts={alerts} />
    </div>
  );
}
