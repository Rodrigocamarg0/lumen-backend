const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const ENABLED_PERSONAS = parseEnabledPersonas(
  import.meta.env.VITE_ENABLED_PERSONAS ?? "kardec",
);

function authHeaders(accessToken, extra = {}) {
  return {
    ...extra,
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  };
}

async function parseApiError(response) {
  const err = await response.json().catch(() => ({}));
  if (response.status === 401) {
    return err.detail ?? "Sessão expirada. Entre novamente para continuar.";
  }
  return Array.isArray(err.detail)
    ? err.detail.map((e) => `${e.loc?.slice(-1)[0] ?? ""}: ${e.msg}`).join("; ")
    : (err.detail ?? `HTTP ${response.status}`);
}

export const PERSONA_CATALOG = [
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
    id: "joanna",
    name: "Joanna de Ângelis",
    subtitle: "Psicologia e espiritualidade",
    description:
      "Psicóloga espiritual que une ciência e fé nas obras psicografadas por Divaldo Franco.",
  },
];

export const PERSONAS = PERSONA_CATALOG.filter((persona) =>
  ENABLED_PERSONAS.has(persona.id),
);

export function isPersonaEnabled(id) {
  return ENABLED_PERSONAS.has(id);
}

function parseEnabledPersonas(value) {
  const items = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (!items.length) return new Set(["kardec"]);
  if (items.includes("all"))
    return new Set(PERSONA_CATALOG.map((persona) => persona.id));
  return new Set(items);
}

export function getPersona(id) {
  return PERSONAS.find((p) => p.id === id) ?? PERSONAS[0];
}

/* ─── Health ────────────────────────────────────────────── */

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/* ─── Terms Acceptance ──────────────────────────────────── */

/**
 * Record LGPD-compliant terms acceptance on the server (audit trail).
 * Must be called BEFORE updating Supabase user metadata.
 * @param {string} termsVersion
 * @param {string} accessToken
 * @returns {Promise<{accepted: boolean, terms_version: string, accepted_at: string}>}
 */
export async function acceptTerms(termsVersion, accessToken) {
  const res = await fetch(`${API_BASE}/api/me/terms-acceptance`, {
    method: "POST",
    headers: authHeaders(accessToken, { "Content-Type": "application/json" }),
    body: JSON.stringify({ terms_version: termsVersion }),
  });
  if (!res.ok) throw new Error(await parseApiError(res));
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
 *   onSession: (session:object) => void,
 *   accessToken: string,
 *   signal: AbortSignal,
 * }} params
 * @returns {Promise<string>} full generated text
 */
export async function streamChat({
  message,
  persona_id,
  session_id,
  incognito = false,
  onToken,
  onCitations,
  onStats,
  onSession,
  accessToken,
  signal,
}) {
  const body = {
    message,
    persona_id,
    session_id: incognito ? null : session_id,
    options: {
      max_new_tokens: 1024,
      top_k_chunks: 5,
      temperature: 0.7,
      incognito,
    },
  };

  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: authHeaders(accessToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    throw new Error(await parseApiError(response));
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
        } else if (eventType === "session") {
          onSession?.(data);
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
export async function fetchSessions(personaId = null, accessToken) {
  const url = personaId
    ? `${API_BASE}/api/sessions?persona_id=${encodeURIComponent(personaId)}`
    : `${API_BASE}/api/sessions`;
  const res = await fetch(url, { headers: authHeaders(accessToken) });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

/**
 * Fetch the full turn history for a session.
 * @param {string} sessionId
 * @returns {Promise<{session_id:string, persona_id:string, turns:object[]}>}
 */
export async function fetchSessionDetail(sessionId, accessToken) {
  const res = await fetch(
    `${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}`,
    { headers: authHeaders(accessToken) },
  );
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

/**
 * Delete a session and its history.
 * @param {string} sessionId
 */
export async function deleteSession(sessionId, accessToken) {
  const res = await fetch(
    `${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE", headers: authHeaders(accessToken) },
  );
  if (!res.ok && res.status !== 404) throw new Error(await parseApiError(res));
}

/* ─── Memories ──────────────────────────────────────────── */

/**
 * List the current user's stored memories, optionally filtered by persona.
 * @param {string|null} personaId
 * @param {string} accessToken
 */
export async function fetchMemories(personaId, accessToken) {
  const url = personaId
    ? `${API_BASE}/api/memories?persona_id=${encodeURIComponent(personaId)}`
    : `${API_BASE}/api/memories`;
  const res = await fetch(url, { headers: authHeaders(accessToken) });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

/**
 * Soft-delete a stored memory by id.
 * @param {string} memoryId
 * @param {string} accessToken
 */
export async function deleteMemory(memoryId, accessToken) {
  const res = await fetch(
    `${API_BASE}/api/memories/${encodeURIComponent(memoryId)}`,
    { method: "DELETE", headers: authHeaders(accessToken) },
  );
  if (!res.ok && res.status !== 404) throw new Error(await parseApiError(res));
}

/* ─── Semantic Search ───────────────────────────────────── */

export async function search(
  query,
  top_k = 10,
  accessToken,
  persona_id = getPersona()?.id ?? "kardec",
) {
  const res = await fetch(`${API_BASE}/api/search`, {
    method: "POST",
    headers: authHeaders(accessToken, { "Content-Type": "application/json" }),
    body: JSON.stringify({ query, top_k, persona_id }),
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}
