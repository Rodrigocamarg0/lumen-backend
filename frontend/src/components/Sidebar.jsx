import { useEffect, useState } from "react";
import FlameIcon from "./FlameIcon.jsx";
import { fetchHealth, PERSONAS } from "../lib/api.js";

function HealthDot() {
  const [status, setStatus] = useState("checking");

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const data = await fetchHealth();
        if (!cancelled) setStatus(data.status === "ok" ? "ok" : "degraded");
      } catch {
        if (!cancelled) setStatus("offline");
      }
    }
    check();
    const id = setInterval(check, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const colors = {
    checking: "bg-gray-400",
    ok: "bg-green-500",
    degraded: "bg-yellow-400",
    offline: "bg-red-500",
  };
  const labels = {
    checking: "Verificando…",
    ok: "Sistema online",
    degraded: "Modo degradado",
    offline: "Backend inacessível",
  };

  return (
    <div className="flex items-center gap-2">
      <div className={`w-2 h-2 rounded-full ${colors[status]}`} />
      <span className="text-xs text-gray-500 dark:text-gray-400">
        {labels[status]}
      </span>
    </div>
  );
}

export default function Sidebar({
  open,
  onClose,
  currentPersona,
  onPersonaChange,
  conversations,
  onNewChat,
  onSelectConversation,
  activeConversationId,
}) {
  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-10 md:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={[
          "w-64 bg-gray-50 dark:bg-gray-800",
          "border-r border-gray-200 dark:border-gray-700",
          "flex flex-col z-20 h-full",
          "absolute md:relative transition-transform duration-300",
          open ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        ].join(" ")}
      >
        {/* Logo */}
        <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FlameIcon className="w-6 h-6 text-orange-400 flame" />
            <span className="font-semibold text-lg">Lumen</span>
          </div>
          <button
            onClick={onClose}
            className="md:hidden text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition"
            aria-label="Fechar menu"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* New chat */}
        <div className="p-3">
          <button
            onClick={onNewChat}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border
                       border-gray-300 dark:border-gray-600
                       hover:bg-gray-100 dark:hover:bg-gray-700
                       transition text-sm font-medium"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4v16m8-8H4"
              />
            </svg>
            Nova conversa
          </button>
        </div>

        {/* Conversation history */}
        <div
          className="flex-1 overflow-y-auto px-3 py-2 space-y-1"
          id="history-list"
        >
          {conversations.length > 0 && (
            <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1">
              Hoje
            </div>
          )}
          {conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => onSelectConversation(conv.id)}
              className={[
                "w-full text-left px-2 py-1.5 rounded text-sm truncate transition",
                conv.id === activeConversationId
                  ? "bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700",
              ].join(" ")}
              title={conv.title}
            >
              {conv.title}
            </button>
          ))}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400">
          <HealthDot />
          <div className="mt-1">Base: Obras de referência espírita</div>
        </div>
      </aside>
    </>
  );
}
