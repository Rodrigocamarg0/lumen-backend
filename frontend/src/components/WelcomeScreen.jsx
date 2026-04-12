import FlameIcon from "./FlameIcon.jsx";
import { PERSONAS } from "../lib/api.js";

export default function WelcomeScreen({
  currentPersona,
  onPersonaSelect,
  onSuggestionClick,
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 max-w-3xl mx-auto">
      <div className="mb-8">
        <FlameIcon className="w-16 h-16 text-orange-400 flame mx-auto mb-4" />
        <h1 className="text-3xl font-semibold text-center mb-2">Lumen</h1>
        <p className="text-gray-600 dark:text-gray-400 text-center">
          Iluminando o estudo da Doutrina Espírita
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-lg">
        {PERSONAS.map((p) => (
          <button
            key={p.id}
            onClick={() => onPersonaSelect(p.id)}
            className={[
              "p-4 rounded-xl border transition text-left group",
              currentPersona === p.id
                ? "border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-900/20"
                : "border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800",
            ].join(" ")}
          >
            <div
              className={[
                "font-medium mb-1 transition",
                currentPersona === p.id
                  ? "text-orange-500"
                  : "group-hover:text-orange-500",
              ].join(" ")}
            >
              {p.name}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {p.subtitle}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
