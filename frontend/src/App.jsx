import { useCallback, useEffect, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import WelcomeScreen from "./components/WelcomeScreen.jsx";
import ChatArea from "./components/ChatArea.jsx";
import InputArea from "./components/InputArea.jsx";
import MemoriesModal from "./components/MemoriesModal.jsx";
import IncognitoIcon from "./components/IncognitoIcon.jsx";
import AdminDashboard from "./components/AdminDashboard.jsx";
import { useChat } from "./hooks/useChat.js";
import { useAuth } from "./auth/useAuth.js";
import {
  deleteSession,
  fetchSessionDetail,
  fetchSessions,
  getPersona,
} from "./lib/api.js";

function loadTheme() {
  const saved = localStorage.getItem("lumen-theme");
  if (saved) return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function applyTheme(theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export default function App() {
  const { accessToken, user } = useAuth();
  const [theme, setTheme] = useState(() => {
    const t = loadTheme();
    applyTheme(t);
    return t;
  });

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [currentPersona, setCurrentPersona] = useState("kardec");
  const [showWelcome, setShowWelcome] = useState(true);
  const [systemNotes, setSystemNotes] = useState([]);
  const [incognito, setIncognito] = useState(false);
  const [memoriesOpen, setMemoriesOpen] = useState(false);

  const [sessions, setSessions] = useState([]);
  const isAdminRoute = window.location.pathname === "/admin";

  const {
    messages,
    isStreaming,
    sessionId,
    sendMessage,
    clearMessages,
    loadSession,
    onTurnCompleteRef,
  } = useChat({ accessToken, incognito });

  useEffect(() => {
    clearMessages();
    setSessions([]);
    setShowWelcome(true);
    setSystemNotes([]);
  }, [clearMessages, user?.id]);

  const refreshSessions = useCallback(async () => {
    if (!accessToken) return;
    try {
      const data = await fetchSessions(currentPersona, accessToken);
      setSessions(data);
    } catch {
      setSessions([]);
    }
  }, [accessToken, currentPersona]);

  // Load sessions on mount and when persona changes
  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  // Wire up the post-turn callback so the list refreshes after each message
  useEffect(() => {
    onTurnCompleteRef.current = refreshSessions;
  }, [refreshSessions, onTurnCompleteRef]);

  function handleThemeToggle() {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      applyTheme(next);
      localStorage.setItem("lumen-theme", next);
      return next;
    });
  }

  function handlePersonaChange(id) {
    const prev = currentPersona;
    setCurrentPersona(id);
    if (prev !== id && messages.length > 0) {
      setSystemNotes((n) => [
        ...n,
        `Agora conversando com ${getPersona(id).name}`,
      ]);
    }
  }

  function handleNewChat() {
    clearMessages();
    setShowWelcome(true);
    setSystemNotes([]);
    setSidebarOpen(false);
  }

  function handleIncognitoToggle() {
    setIncognito((prev) => {
      const next = !prev;
      clearMessages();
      setShowWelcome(true);
      setSystemNotes([]);
      return next;
    });
  }

  async function handleSelectSession(session) {
    try {
      const detail = await fetchSessionDetail(session.session_id, accessToken);
      loadSession(session.session_id, detail.turns);
      if (session.persona_id && session.persona_id !== currentPersona) {
        setCurrentPersona(session.persona_id);
      }
      setShowWelcome(false);
      setSidebarOpen(false);
    } catch (err) {
      console.error("Failed to load session:", err);
    }
  }

  async function handleDeleteSession(sessionId) {
    try {
      await deleteSession(sessionId, accessToken);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  }

  async function handleSend(text) {
    if (showWelcome) setShowWelcome(false);
    await sendMessage(text, currentPersona);
  }

  function handleSuggestion(text) {
    setShowWelcome(false);
    sendMessage(text, currentPersona);
  }

  function handlePersonaSelect(id) {
    setCurrentPersona(id);
  }

  if (isAdminRoute) return <AdminDashboard />;

  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 font-sans antialiased transition-colors duration-300">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        currentPersona={currentPersona}
        onPersonaChange={handlePersonaChange}
        sessions={sessions}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
        activeSessionId={sessionId}
      />

      <div className="flex flex-col flex-1 min-w-0 relative">
        <Header
          onMenuToggle={() => setSidebarOpen((o) => !o)}
          currentPersona={currentPersona}
          theme={theme}
          onThemeToggle={handleThemeToggle}
          onSignOut={handleNewChat}
          onOpenMemories={() => setMemoriesOpen(true)}
          incognito={incognito}
          onIncognitoToggle={handleIncognitoToggle}
        />

        {incognito && (
          <div
            role="status"
            className="flex items-center justify-center gap-2 px-4 py-2
                       bg-slate-900 dark:bg-slate-950
                       text-slate-100
                       border-b border-slate-800
                       text-xs tracking-wide shadow-sm"
          >
            <IncognitoIcon className="w-4 h-4 flex-shrink-0 text-slate-300" />
            <span>
              <span className="font-semibold">Modo anônimo</span>
              <span className="text-slate-300">
                {" "}
                — esta conversa não será salva e não atualizará suas memórias.
              </span>
            </span>
          </div>
        )}

        {showWelcome ? (
          <div className="flex-1 overflow-y-auto">
            <WelcomeScreen
              currentPersona={currentPersona}
              onPersonaSelect={handlePersonaSelect}
              onSuggestionClick={handleSuggestion}
            />
          </div>
        ) : (
          <ChatArea
            messages={messages}
            isStreaming={isStreaming}
            systemNotes={systemNotes}
          />
        )}

        <InputArea
          currentPersona={currentPersona}
          onPersonaChange={handlePersonaChange}
          onSend={handleSend}
          isStreaming={isStreaming}
          autoFocus={!showWelcome}
        />
      </div>

      {memoriesOpen && (
        <MemoriesModal
          accessToken={accessToken}
          personaId={currentPersona}
          onClose={() => setMemoriesOpen(false)}
        />
      )}
    </div>
  );
}
