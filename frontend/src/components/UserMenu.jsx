import { useState } from "react";
import { useAuth } from "../auth/useAuth.js";

function initials(email) {
  return (email || "?").slice(0, 1).toUpperCase();
}

export default function UserMenu({ onSignOut, onOpenMemories }) {
  const [open, setOpen] = useState(false);
  const { user, signOut } = useAuth();
  const email = user?.email ?? "";

  async function handleSignOut() {
    await signOut();
    onSignOut?.();
    setOpen(false);
  }

  function handleOpenMemories() {
    setOpen(false);
    onOpenMemories?.();
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-2 rounded-full border border-gray-200 dark:border-gray-700 px-2 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-800 transition"
        aria-label="Menu do usuário"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-orange-500 text-xs font-semibold text-white">
          {initials(email)}
        </span>
        <span className="hidden sm:block max-w-40 truncate text-gray-600 dark:text-gray-300">
          {email}
        </span>
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-64 rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-2 shadow-xl z-30 animate-fade-in">
          <div className="px-3 py-2">
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Conta
            </div>
            <div className="mt-0.5 truncate text-sm font-medium">{email}</div>
          </div>
          <button
            type="button"
            onClick={handleOpenMemories}
            className="w-full rounded-xl px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
          >
            Minhas memórias
          </button>
          <button
            type="button"
            onClick={handleSignOut}
            className="w-full rounded-xl px-3 py-2 text-left text-sm text-red-600 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-950/40 transition"
          >
            Sair
          </button>
        </div>
      )}
    </div>
  );
}
