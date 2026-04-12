import { useCallback, useRef, useState } from "react";
import { streamChat } from "../lib/api.js";

/**
 * Manages chat state and SSE streaming.
 *
 * Returns:
 *   messages     — array of message objects
 *   isStreaming   — boolean
 *   sessionId     — string | null
 *   sendMessage   — async (text: string, personaId: string) => void
 *   clearMessages — () => void
 */
export function useChat() {
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(null);

  // history kept as ref (not state) to avoid stale closure in the async stream
  const historyRef = useRef([]);
  const abortRef = useRef(null);

  const clearMessages = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setIsStreaming(false);
    historyRef.current = [];
    setSessionId(null);
  }, []);

  const sendMessage = useCallback(
    async (text, personaId) => {
      if (!text.trim() || isStreaming) return;

      // Append user message
      const userMsg = { id: crypto.randomUUID(), role: "user", content: text };
      setMessages((prev) => [...prev, userMsg]);

      // snapshot history before adding current user turn (API expects prior history)
      const historySnapshot = [...historyRef.current];
      historyRef.current = [
        ...historyRef.current,
        { role: "user", content: text },
      ];

      // Placeholder assistant message (streaming fills it in)
      const assistantId = crypto.randomUUID();
      const assistantMsg = {
        id: assistantId,
        role: "assistant",
        content: "",
        citations: [],
        stats: null,
        streaming: true,
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const fullText = await streamChat({
          message: text,
          persona_id: personaId,
          session_id: sessionId,
          history: historySnapshot,
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
            if (stats.session_id) setSessionId(stats.session_id);
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, stats } : m)),
            );
          },
        });

        // Mark done, push to history
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, streaming: false } : m,
          ),
        );
        historyRef.current = [
          ...historyRef.current,
          { role: "assistant", content: fullText },
        ];
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

  return { messages, isStreaming, sessionId, sendMessage, clearMessages };
}
