import LogoFlame from "./LogoFlame.jsx";
import { PERSONA_CATALOG, isPersonaEnabled } from "../lib/api.js";

export default function WelcomeScreen({
  currentPersona,
  onPersonaSelect,
  onSuggestionClick,
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 max-w-3xl mx-auto">
      <div className="mb-8">
        <LogoFlame className="w-16 h-16 mx-auto mb-4" />
        <h1 className="text-3xl font-semibold text-center mb-2">Lumen</h1>
        <p className="text-gray-600 dark:text-gray-400 text-center">
          Iluminando o estudo da Doutrina Espírita
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-lg">
        {PERSONA_CATALOG.map((p) => {
          const enabled = isPersonaEnabled(p.id);
          const selected = enabled && currentPersona === p.id;
          return (
            <button
              key={p.id}
              type="button"
              onClick={enabled ? () => onPersonaSelect(p.id) : undefined}
              disabled={!enabled}
              aria-disabled={!enabled}
              title={enabled ? undefined : "Em breve"}
              className={[
                "relative p-4 rounded-xl border transition text-left group",
                selected
                  ? "border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-900/20"
                  : "border-gray-200 dark:border-gray-700",
                enabled
                  ? "hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
                  : "opacity-60 cursor-not-allowed",
              ].join(" ")}
            >
              {!enabled && (
                <span
                  className="absolute top-2 right-2 px-2 py-0.5 rounded-full
                             text-[10px] font-semibold uppercase tracking-wide
                             bg-orange-100 text-orange-700
                             dark:bg-orange-900/40 dark:text-orange-300"
                >
                  Em breve
                </span>
              )}
              <div
                className={[
                  "font-medium mb-1 transition",
                  selected
                    ? "text-orange-500"
                    : enabled
                      ? "group-hover:text-orange-500"
                      : "",
                ].join(" ")}
              >
                {p.name}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {p.subtitle}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
