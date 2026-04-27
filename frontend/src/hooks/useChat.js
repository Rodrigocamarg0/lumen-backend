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
 *   sessionId     — string | null
 *   sendMessage   — async (text: string, personaId: string) => void
 *   clearMessages — () => void  (starts a new session)
 *   loadSession   — (sessionId: string, turns: object[]) => void
 *   onTurnComplete — ref to a callback invoked after each turn persists
 */
export function useChat({ accessToken, incognito = false }) {
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(null);

  const abortRef = useRef(null);
  // Callers (App.jsx) can set this to be notified when a turn is done
  const onTurnCompleteRef = useRef(null);

  const updateSessionId = (sid) => {
    setSessionId(sid);
  };

  const clearMessages = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setIsStreaming(false);
    updateSessionId(null);
  }, []);

  /** Restore a past session into the chat view. */
  const loadSession = useCallback((sid, turns) => {
    abortRef.current?.abort();
    setIsStreaming(false);
    updateSessionId(sid);
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
      if (!accessToken) {
        throw new Error("Sessão expirada. Entre novamente para continuar.");
      }

      // Use existing sessionId or let the server assign one (returned in stats).
      // In incognito mode the server discards session_id, so we don't reuse one.
      const currentSid = incognito ? null : sessionId;

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
          incognito,
          signal: controller.signal,
          accessToken,

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
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, stats } : m)),
            );
          },

          onSession: (session) => {
            if (incognito) return;
            if (session.session_id) updateSessionId(session.session_id);
          },
        });

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, streaming: false } : m,
          ),
        );

        // Notify App.jsx to refresh the session list (skipped in incognito —
        // the turn was never persisted, so there is nothing new to fetch).
        if (!incognito) onTurnCompleteRef.current?.();
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
    [accessToken, incognito, isStreaming, sessionId],
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
