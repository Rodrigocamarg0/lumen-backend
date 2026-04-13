import { useCallback, useRef, useState } from "react";
import { streamChat } from "../lib/api.js";

/**
 * Manages chat state and SSE streaming.
 * Chat history is owned server-side by Agno; the client only tracks
 * display messages and the current session_id.
 *
 * Returns:
 *   messages     — array of message objects (display only)
 *   isStreaming   — boolean
 *   sessionId     — string | null  (also persisted to localStorage)
 *   sendMessage   — async (text: string, personaId: string) => void
 *   clearMessages — () => void  (starts a new session)
 *   loadSession   — (sessionId: string, turns: object[]) => void
 *   onTurnComplete — ref to a callback invoked after each turn persists
 */
export function useChat() {
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(
    () => localStorage.getItem("lumen-session-id") || null,
  );

  const abortRef = useRef(null);
  // Callers (App.jsx) can set this to be notified when a turn is done
  const onTurnCompleteRef = useRef(null);

  const _persistSessionId = (sid) => {
    setSessionId(sid);
    if (sid) localStorage.setItem("lumen-session-id", sid);
    else localStorage.removeItem("lumen-session-id");
  };

  const clearMessages = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setIsStreaming(false);
    _persistSessionId(null);
  }, []);

  /** Restore a past session into the chat view. */
  const loadSession = useCallback((sid, turns) => {
    abortRef.current?.abort();
    setIsStreaming(false);
    _persistSessionId(sid);
    setMessages(
      turns.map((t) => ({
        id: crypto.randomUUID(),
        role: t.role,
        content: t.content,
        citations: [],
        stats: null,
        streaming: false,
      })),
    );
  }, []);

  const sendMessage = useCallback(
    async (text, personaId) => {
      if (!text.trim() || isStreaming) return;

      // Use existing sessionId or let the server assign one (returned in stats)
      const currentSid = sessionId;

      const userMsg = { id: crypto.randomUUID(), role: "user", content: text };
      setMessages((prev) => [...prev, userMsg]);

      const assistantId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: "assistant",
          content: "",
          citations: [],
          stats: null,
          streaming: true,
        },
      ]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        await streamChat({
          message: text,
          persona_id: personaId,
          session_id: currentSid,
          signal: controller.signal,

          onToken: (token) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: m.content + token } : m,
              ),
            );
          },

          onCitations: (citations) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, citations } : m)),
            );
          },

          onStats: (stats) => {
            // The server echoes back session_id (existing or newly generated)
            if (stats.session_id) _persistSessionId(stats.session_id);
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, stats } : m)),
            );
          },
        });

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, streaming: false } : m,
          ),
        );

        // Notify App.jsx to refresh the session list
        onTurnCompleteRef.current?.();
      } catch (err) {
        if (err.name === "AbortError") return;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, streaming: false, error: err.message }
              : m,
          ),
        );
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [isStreaming, sessionId],
  );

  return {
    messages,
    isStreaming,
    sessionId,
    sendMessage,
    clearMessages,
    loadSession,
    onTurnCompleteRef,
  };
}
