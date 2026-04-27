import { useEffect, useState } from "react";
import { deleteMemory, fetchMemories } from "../lib/api.js";

function formatDate(unixTs) {
  if (!unixTs) return "";
  const d = new Date(unixTs * 1000);
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export default function MemoriesModal({ accessToken, personaId, onClose }) {
  const [memories, setMemories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pendingId, setPendingId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchMemories(personaId ?? null, accessToken);
        if (!cancelled) setMemories(data);
      } catch (err) {
        if (!cancelled) setError(err.message ?? "Erro ao carregar memórias.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [accessToken, personaId]);

  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose?.();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleDelete(memoryId) {
    setPendingId(memoryId);
    try {
      await deleteMemory(memoryId, accessToken);
      setMemories((prev) => prev.filter((m) => m.id !== memoryId));
    } catch (err) {
      setError(err.message ?? "Erro ao apagar memória.");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[80vh] flex flex-col rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-lg font-semibold">Suas memórias</h2>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Preferências e fatos que Lumen lembra entre conversas.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 transition"
            aria-label="Fechar"
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

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-2">
          {loading && (
            <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
              Carregando memórias…
            </p>
          )}

          {error && (
            <div className="rounded-lg border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/40 p-3 text-sm text-red-700 dark:text-red-300">
              {error}
            </div>
          )}

          {!loading && !error && memories.length === 0 && (
            <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
              Nenhuma memória salva ainda. Conforme você conversa, Lumen vai
              registrar suas preferências aqui.
            </p>
          )}

          {memories.map((memory) => (
            <div
              key={memory.id}
              className="group flex items-start gap-3 rounded-xl border border-gray-200 dark:border-gray-700 p-3 hover:bg-gray-50 dark:hover:bg-gray-800/60 transition"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-800 dark:text-gray-100 whitespace-pre-wrap">
                  {memory.memory}
                </p>
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <span>{formatDate(memory.updated_at)}</span>
                  {memory.topics?.length > 0 && (
                    <span className="inline-flex flex-wrap gap-1">
                      {memory.topics.map((topic) => (
                        <span
                          key={topic}
                          className="rounded-full bg-orange-100 dark:bg-orange-950/40 px-2 py-0.5 text-orange-700 dark:text-orange-300"
                        >
                          {topic}
                        </span>
                      ))}
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={() => handleDelete(memory.id)}
                disabled={pendingId === memory.id}
                className="shrink-0 p-2 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/40 transition disabled:opacity-50"
                aria-label="Apagar memória"
                title="Apagar"
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
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                  />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
