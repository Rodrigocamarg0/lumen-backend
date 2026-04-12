import { useCallback, useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import WelcomeScreen from "./components/WelcomeScreen.jsx";
import ChatArea from "./components/ChatArea.jsx";
import InputArea from "./components/InputArea.jsx";
import { useChat } from "./hooks/useChat.js";
import { getPersona } from "./lib/api.js";

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

  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const convFirstMessageRef = useRef(null);

  const { messages, isStreaming, sessionId, sendMessage, clearMessages } =
    useChat();

  useEffect(() => {
    if (
      messages.length === 1 &&
      messages[0].role === "user" &&
      !convFirstMessageRef.current
    ) {
      const id = crypto.randomUUID();
      convFirstMessageRef.current = id;
      setActiveConvId(id);
      setConversations((prev) => [
        { id, title: messages[0].content.slice(0, 48) },
        ...prev,
      ]);
    }
  }, [messages]);

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
    convFirstMessageRef.current = null;
    setActiveConvId(null);
    setSidebarOpen(false);
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
        conversations={conversations}
        onNewChat={handleNewChat}
        onSelectConversation={(id) => {
          setActiveConvId(id);
          setSidebarOpen(false);
        }}
        activeConversationId={activeConvId}
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
