import { useEffect } from "react";

export default function CitationModal({ citation, onClose }) {
  useEffect(() => {
    const handler = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  if (!citation) return null;

  const lines = [
    citation.parte && { label: "Parte", value: citation.parte },
    citation.capitulo && { label: "Capítulo", value: citation.capitulo },
    citation.questao && { label: "Questão", value: String(citation.questao) },
  ].filter(Boolean);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center
                 bg-black/50 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
                   rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <p className="text-[10px] uppercase tracking-widest text-orange-500 mb-1">
              Fonte
            </p>
            <h3 className="text-base font-medium text-gray-900 dark:text-gray-100 leading-snug">
              {citation.obra}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition mt-0.5 p-1 -mr-1"
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

        {/* Metadata */}
        {lines.length > 0 && (
          <div className="px-6 pt-3 pb-2 flex flex-wrap gap-x-6 gap-y-1.5">
            {lines.map(({ label, value }) => (
              <div key={label}>
                <span className="text-[10px] text-gray-500 uppercase tracking-wider">
                  {label}{" "}
                </span>
                <span className="text-xs text-gray-700 dark:text-gray-300">
                  {value}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Excerpt */}
        {citation.excerpt && (
          <blockquote className="px-6 pb-5 pt-3">
            <div className="border-l-2 border-orange-400/50 pl-4">
              <p className="text-sm leading-relaxed text-gray-600 dark:text-gray-400 italic">
                {citation.excerpt}
              </p>
            </div>
          </blockquote>
        )}

        {!citation.excerpt && <div className="pb-4" />}
      </div>
    </div>
  );
}
