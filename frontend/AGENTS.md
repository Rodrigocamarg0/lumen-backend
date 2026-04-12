# AGENTS.md — Frontend

> Scope: everything under `frontend/`.
> Also read the root [`../AGENTS.md`](../AGENTS.md) for project-wide rules.

---

## Stack

| Layer | Technology |
|---|---|
| Framework | React 18 |
| Build tool | Vite 6 |
| Styling | Tailwind CSS v3 |
| Language | JavaScript (ESM) |
| Formatting | Prettier (via pre-commit) |
| Font | Inter (Google Fonts) |

---

## Running the frontend

```bash
cd frontend
npm install          # first time only
npm run dev          # dev server on :3000 with /api proxy to :8000
npm run build        # production build → dist/
npm run preview      # preview the production build
```

The Vite dev proxy (`vite.config.js`) forwards `/api/*` to `http://localhost:8000`.
The backend must be running for chat to work.

---

## Project layout

```
frontend/
├── index.html              ← Vite entry point (loads Inter font)
├── vite.config.js          ← Dev proxy + build config
├── tailwind.config.js      ← Font + animation config
├── postcss.config.js
├── src/
│   ├── main.jsx            ← React root mount
│   ├── App.jsx             ← Root component: theme, routing, layout
│   ├── index.css           ← Tailwind directives + custom CSS
│   ├── components/
│   │   ├── Sidebar.jsx     ← Persona list, conversation history, health dot
│   │   ├── Header.jsx      ← Logo, theme toggle, mobile menu button
│   │   ├── WelcomeScreen.jsx ← Persona cards shown before first message
│   │   ├── ChatArea.jsx    ← Message list, typing indicator, citations
│   │   ├── InputArea.jsx   ← Persona selector, textarea, send button
│   │   ├── CitationModal.jsx ← Source detail modal
│   │   └── FlameIcon.jsx   ← SVG flame icon component
│   ├── hooks/
│   │   └── useChat.js      ← Chat state + SSE streaming hook
│   └── lib/
│       └── api.js          ← PERSONAS array, streamChat(), fetchHealth()
└── dist/                   ← Production build output (gitignored)
```

---

## Design system

The UI matches the `original_index.html` reference design:

| Token | Value |
|---|---|
| Font | Inter (300/400/500/600) |
| Background | `bg-white dark:bg-gray-900` |
| Sidebar | `bg-gray-50 dark:bg-gray-800` |
| Border | `border-gray-200 dark:border-gray-700` |
| Accent (flame, send) | `text-orange-400` / `bg-orange-500 hover:bg-orange-600` |
| User bubble | `bg-gray-100 dark:bg-gray-800` |
| Assistant bubble | `bg-white dark:bg-gray-900` |
| Input container | `bg-gray-100 dark:bg-gray-800` |
| Health dot | `bg-green-500` / `bg-yellow-400` / `bg-red-500` |

Dark mode is controlled by the `dark` class on `<html>` (Tailwind `darkMode: 'class'`).
Theme preference is persisted in `localStorage` under key `lumen-theme`.

---

## SSE streaming contract

`src/lib/api.js` → `streamChat()` connects to `POST /api/chat` and parses:

```
event: token      → onToken(token: string)
event: citations  → onCitations(citations: object[])
event: stats      → onStats(stats: object)
event: error      → throws Error(detail)
event: done       → stream ends, returns fullText
```

When the backend returns a non-2xx response, `err.detail` may be a Pydantic validation
array — stringify it: `err.detail.map(e => `${e.loc?.slice(-1)[0]}: ${e.msg}`).join('; ')`.

---

## Personas

Defined in `src/lib/api.js` as the `PERSONAS` array. Currently active persona IDs
(accepted by the backend): `kardec`.

Persona IDs `andreluiz`, `emmanuel`, `joana` are defined in the frontend but will return
404 from the backend until Phase 3.

---

## Code conventions

- **No default exports from `lib/`** — use named exports.
- **No inline styles** — use Tailwind utility classes.
- **No `lumen-*` custom Tailwind classes** — the design uses standard `gray-*` / `orange-*`.
- **Component files** are PascalCase (`ChatArea.jsx`); hooks are camelCase (`useChat.js`).
- Prettier enforces formatting — do not manually adjust indentation or quotes.

---

## After any change

1. `npm run build` must succeed with zero errors.
2. Visually verify the golden path: welcome screen → send message → streaming response → citation.
3. Check both light and dark mode.
4. Remove any component, hook, or import that is no longer referenced.

---

## Hygiene checklist (before every commit)

- [ ] `pre-commit run --all-files` — prettier passes on all `src/` files
- [ ] `npm run build` — zero errors, bundle under ~200 KB gzip
- [ ] No unused imports or components
- [ ] No `console.log` left in production code

---

> Also read: [`../AGENTS.md`](../AGENTS.md) · [`../backend/AGENTS.md`](../backend/AGENTS.md)
