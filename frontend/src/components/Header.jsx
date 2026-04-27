import LogoFlame from "./LogoFlame.jsx";
import UserMenu from "./UserMenu.jsx";

function SunIcon() {
  return (
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
        d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
      />
    </svg>
  );
}

function IncognitoIcon() {
  return (
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
        d="M3 13l1.5-6a2 2 0 011.94-1.5h11.12A2 2 0 0119.5 7L21 13"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M3 13h18"
      />
      <circle cx="7.5" cy="16.5" r="2.5" strokeWidth={2} />
      <circle cx="16.5" cy="16.5" r="2.5" strokeWidth={2} />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M10 16.5h4"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
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
        d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
      />
    </svg>
  );
}

export default function Header({
  onMenuToggle,
  theme,
  onThemeToggle,
  onSignOut,
  onOpenMemories,
  incognito,
  onIncognitoToggle,
}) {
  return (
    <header
      className="h-14 border-b border-gray-200 dark:border-gray-700
                       bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm
                       flex items-center justify-between px-4 flex-shrink-0 z-10"
    >
      <div className="flex items-center gap-3">
        {/* Mobile menu toggle */}
        <button
          onClick={onMenuToggle}
          className="md:hidden text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition"
          aria-label="Abrir menu"
        >
          <svg
            className="w-6 h-6"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 6h16M4 12h16M4 18h16"
            />
          </svg>
        </button>

        <div className="flex items-center gap-2">
          <LogoFlame className="w-6 h-6" />
          <span className="font-semibold">Lumen</span>
        </div>
      </div>

      {/* Right controls */}
      <div className="flex items-center gap-2">
        <button
          onClick={onIncognitoToggle}
          className={[
            "p-2 rounded-lg transition border",
            incognito
              ? "bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 border-gray-900 dark:border-gray-100"
              : "border-transparent text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
          ].join(" ")}
          title={
            incognito
              ? "Modo anônimo ativo — nada será salvo"
              : "Ativar modo anônimo"
          }
          aria-pressed={incognito}
          aria-label="Modo anônimo"
        >
          <IncognitoIcon />
        </button>
        <button
          onClick={onThemeToggle}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800
                     text-gray-600 dark:text-gray-300 transition"
          title="Alternar tema"
          aria-label="Alternar tema claro/escuro"
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
        <UserMenu onSignOut={onSignOut} onOpenMemories={onOpenMemories} />
      </div>
    </header>
  );
}
