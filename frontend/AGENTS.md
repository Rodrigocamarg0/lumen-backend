# AGENTS.md — Frontend

> Scope: `frontend/`.
> Also read: [`../AGENTS.md`](../AGENTS.md)

---

## Stack

React 18 · Vite 6 · Tailwind CSS v3 · Prettier · Inter font (Google Fonts)

---

## Run

```bash
cd frontend
npm install          # first time only
npm run dev          # dev server :3000, /api proxied to :8000
npm run build        # production build → dist/
npm run preview      # preview production build
```

The backend must be running for chat to work in dev.

---

## Component map

```
src/
├── App.jsx                  ← root: theme, layout, state
├── index.css                ← Tailwind directives + animations + scrollbar
├── main.jsx                 ← React mount
├── components/
│   ├── Sidebar.jsx          ← persona list, conversation history, health dot
│   ├── Header.jsx           ← logo, theme toggle, mobile menu
│   ├── WelcomeScreen.jsx    ← persona cards shown before first message
│   ├── ChatArea.jsx         ← message list, typing indicator, citation pills
│   ├── InputArea.jsx        ← persona selector, textarea, send button
│   ├── CitationModal.jsx    ← source detail modal
│   └── FlameIcon.jsx        ← reusable SVG flame icon
├── hooks/
│   └── useChat.js           ← chat state + SSE streaming
└── lib/
    └── api.js               ← PERSONAS array, streamChat(), fetchHealth()
```

**Reference docs:**
- Design tokens (colors, typography, dark mode, animations): `docs/design-system.md`
- SSE streaming contract (events, error handling): `specs/architecture/api_contract.md`

---

## Code conventions

- Component files: PascalCase (`ChatArea.jsx`); hooks/utils: camelCase (`useChat.js`)
- No inline styles — use Tailwind utility classes only
- No custom `lumen-*` Tailwind classes — use standard `gray-*` / `orange-*`
- No default exports from `lib/` — use named exports
- Prettier formats everything — do not manually adjust indentation or quotes

---

## After any change

1. `npm run build` must pass with zero errors
2. Verify the golden path: welcome screen → send message → streaming response → citation
3. Check both light and dark mode
4. Remove any component, hook, or import no longer referenced

---

## Hygiene checklist (before every commit)

- [ ] `pre-commit run --all-files` — prettier passes on all `src/` files
- [ ] `npm run build` — zero errors, no new bundle size regressions
- [ ] No unused imports or unreferenced components
- [ ] No `console.log` in production code

---

> See also: [`../AGENTS.md`](../AGENTS.md) · [`../docs/design-system.md`](../docs/design-system.md) · [`../specs/architecture/api_contract.md`](../specs/architecture/api_contract.md)
