const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export const PERSONAS = [
  {
    id: "kardec",
    name: "Allan Kardec",
    subtitle: "Codificador do Espiritismo",
    description:
      "O codificador da Doutrina Espírita responde com rigor científico e filosófico, citando as cinco obras fundamentais.",
  },
  {
    id: "andreluiz",
    name: "André Luiz",
    subtitle: "Autor de Nosso Lar",
    description:
      "Espírito que revelou os detalhes da vida no mundo espiritual através das obras psicografadas por Chico Xavier.",
  },
  {
    id: "emmanuel",
    name: "Emmanuel",
    subtitle: "Mentor de Chico Xavier",
    description:
      "Espírito de elevada hierarquia que orientou Chico Xavier por décadas, com sabedoria e fraternidade.",
  },
  {
    id: "joana",
    name: "Joanna de Ângelis",
    subtitle: "Psicologia e espiritualidade",
    description:
      "Psicóloga espiritual que une ciência e fé nas obras psicografadas por Divaldo Franco.",
  },
];

export function getPersona(id) {
  return PERSONAS.find((p) => p.id === id) ?? PERSONAS[0];
}

/* ─── Health ────────────────────────────────────────────── */

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/* ─── SSE Chat ──────────────────────────────────────────── */

/**
 * Streams a chat request and calls callbacks for each SSE event type.
 * History is managed server-side by Agno; do not send it from the client.
 *
 * @param {{
 *   message: string,
 *   persona_id: string,
 *   session_id: string|null,
 *   onToken: (token:string) => void,
 *   onCitations: (citations:object[]) => void,
 *   onStats: (stats:object) => void,
 *   signal: AbortSignal,
 * }} params
 * @returns {Promise<string>} full generated text
 */
export async function streamChat({
  message,
  persona_id,
  session_id,
  onToken,
  onCitations,
  onStats,
  signal,
}) {
  const body = {
    message,
    persona_id,
    session_id,
    options: {
      max_new_tokens: 1024,
      top_k_chunks: 5,
      temperature: 0.7,
    },
  };

  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    // Pydantic validation errors return detail as an array of objects
    const detail = Array.isArray(err.detail)
      ? err.detail
          .map((e) => `${e.loc?.slice(-1)[0] ?? ""}: ${e.msg}`)
          .join("; ")
      : (err.detail ?? `HTTP ${response.status}`);
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let eventType = null;
  let fullText = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") return fullText;

        let data;
        try {
          data = JSON.parse(raw);
        } catch {
          continue;
        }

        if (eventType === "token") {
          fullText += data.token;
          onToken(data.token);
        } else if (eventType === "citations") {
          onCitations(data.citations ?? []);
        } else if (eventType === "stats") {
          onStats(data.stats ?? {});
        } else if (eventType === "error") {
          throw new Error(data.detail ?? "Unknown error");
        }

        eventType = null;
      }
    }
  }

  return fullText;
}

/* ─── Sessions ──────────────────────────────────────────── */

/**
 * Fetch all sessions, optionally filtered by persona.
 * @param {string|null} personaId
 * @returns {Promise<object[]>} list of SessionSummary
 */
export async function fetchSessions(personaId = null) {
  const url = personaId
    ? `${API_BASE}/api/sessions?persona_id=${encodeURIComponent(personaId)}`
    : `${API_BASE}/api/sessions`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/**
 * Fetch the full turn history for a session.
 * @param {string} sessionId
 * @returns {Promise<{session_id:string, persona_id:string, turns:object[]}>}
 */
export async function fetchSessionDetail(sessionId) {
  const res = await fetch(
    `${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/**
 * Delete a session and its history.
 * @param {string} sessionId
 */
export async function deleteSession(sessionId) {
  const res = await fetch(
    `${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
  if (!res.ok && res.status !== 404) throw new Error(`HTTP ${res.status}`);
}

/* ─── Semantic Search ───────────────────────────────────── */

export async function search(query, top_k = 10) {
  const res = await fetch(`${API_BASE}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
