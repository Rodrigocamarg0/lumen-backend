import { useCallback, useEffect, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import WelcomeScreen from "./components/WelcomeScreen.jsx";
import ChatArea from "./components/ChatArea.jsx";
import InputArea from "./components/InputArea.jsx";
import { useChat } from "./hooks/useChat.js";
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
  const [theme, setTheme] = useState(() => {
    const t = loadTheme();
    applyTheme(t);
    return t;
  });

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [currentPersona, setCurrentPersona] = useState("kardec");
  const [showWelcome, setShowWelcome] = useState(true);
  const [systemNotes, setSystemNotes] = useState([]);

  const [sessions, setSessions] = useState([]);

  const {
    messages,
    isStreaming,
    sessionId,
    sendMessage,
    clearMessages,
    loadSession,
    onTurnCompleteRef,
  } = useChat();

  // Restore welcome state: if we have a session from localStorage, hide welcome
  useEffect(() => {
    if (sessionId && messages.length === 0) {
      // Fetch the last session to pre-populate (optional; just hide welcome)
      setShowWelcome(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshSessions = useCallback(async () => {
    try {
      const data = await fetchSessions(currentPersona);
      setSessions(data);
    } catch {
      // silently ignore — sessions are non-critical
    }
  }, [currentPersona]);

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

  async function handleSelectSession(session) {
    try {
      const detail = await fetchSessionDetail(session.session_id);
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
      await deleteSession(sessionId);
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
        />

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
    </div>
  );
}
