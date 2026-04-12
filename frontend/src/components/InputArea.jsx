import { useEffect, useRef } from "react";
import { PERSONAS } from "../lib/api.js";

export default function InputArea({
  currentPersona,
  onPersonaChange,
  onSend,
  isStreaming,
  autoFocus,
}) {
  const textareaRef = useRef(null);

  useEffect(() => {
    if (autoFocus) textareaRef.current?.focus();
  }, [autoFocus]);

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  function autoResize() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 128) + "px";
  }

  function submit() {
    const text = textareaRef.current?.value.trim();
    if (!text || isStreaming) return;
    onSend(text);
    textareaRef.current.value = "";
    textareaRef.current.style.height = "auto";
  }

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <div className="max-w-3xl mx-auto">
        <div className="relative flex items-end gap-2 bg-gray-100 dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm focus-within:ring-2 focus-within:ring-orange-400/50 focus-within:border-orange-400/50 transition-all">
          {/* Persona select */}
          <div className="relative flex-shrink-0">
            <select
              value={currentPersona}
              onChange={(e) => onPersonaChange(e.target.value)}
              className="appearance-none bg-transparent pl-4 pr-8 py-3.5 text-sm font-medium
                         text-gray-700 dark:text-gray-300 cursor-pointer focus:outline-none
                         border-r border-gray-300 dark:border-gray-600 rounded-l-2xl
                         hover:bg-gray-200 dark:hover:bg-gray-700 transition"
              aria-label="Selecionar persona"
            >
              {PERSONAS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-gray-500">
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
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </div>
          </div>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            rows={1}
            className="flex-1 bg-transparent py-3.5 px-2 text-gray-900 dark:text-gray-100
                       placeholder-gray-500 resize-none focus:outline-none max-h-32 text-sm"
            placeholder="Pergunte sobre a doutrina..."
            onKeyDown={handleKeyDown}
            onInput={autoResize}
            disabled={isStreaming}
            style={{ maxHeight: "128px" }}
          />

          {/* Send button */}
          <button
            onClick={submit}
            disabled={isStreaming}
            className="p-2 m-1.5 rounded-xl bg-orange-500 hover:bg-orange-600 text-white
                       transition disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
            aria-label="Enviar"
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
                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
              />
            </svg>
          </button>
        </div>

        <div className="text-center mt-2 text-xs text-gray-500 dark:text-gray-500">
          Lumen é uma ferramenta de pesquisa. Sempre consulte as obras originais
          para estudo aprofundado.
        </div>
      </div>
    </div>
  );
}
