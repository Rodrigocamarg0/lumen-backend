# Design System — Frontend Reference

> Source of truth for the Lumen UI visual language.
> Read this before modifying any component styles.
> The reference HTML design is `frontend/original_index.html`.

---

## Typography

| Role | Value |
|---|---|
| Font family | `Inter` (Google Fonts, weights 300/400/500/600) |
| Load via | `index.html` `<link>` tag (preconnect + stylesheet) |
| Body declaration | `font-family: 'Inter', system-ui, sans-serif` in `index.css` |
| Tailwind config | `fontFamily.sans: ['Inter', 'system-ui', 'sans-serif']` |

---

## Color tokens (Tailwind classes)

### Layout backgrounds

| Surface | Light | Dark |
|---|---|---|
| Page background | `bg-white` | `dark:bg-gray-900` |
| Sidebar | `bg-gray-50` | `dark:bg-gray-800` |
| Header | `bg-white/80` | `dark:bg-gray-900/80` (+ `backdrop-blur-sm`) |
| Input container | `bg-gray-100` | `dark:bg-gray-800` |

### Borders

| Usage | Light | Dark |
|---|---|---|
| Primary border | `border-gray-200` | `dark:border-gray-700` |
| Select divider | `border-gray-300` | `dark:border-gray-600` |
| Bubble subtle | `border-gray-100` | `dark:border-gray-800` |

### Text

| Role | Light | Dark |
|---|---|---|
| Primary | `text-gray-900` | `dark:text-gray-100` |
| Secondary / muted | `text-gray-600` | `dark:text-gray-400` |
| Placeholder / dim | `text-gray-500` | (same) |

### Accent — orange

| Usage | Class |
|---|---|
| Flame icon | `text-orange-400` |
| Send button bg | `bg-orange-500 hover:bg-orange-600` |
| Send button text | `text-white` |
| Hover accent text | `group-hover:text-orange-500` |
| Selected persona border | `border-orange-300 dark:border-orange-700` |
| Selected persona bg | `bg-orange-50 dark:bg-orange-900/20` |
| Focus ring | `focus-within:ring-orange-400/50 focus-within:border-orange-400/50` |

### Chat bubbles

| Bubble | Light | Dark |
|---|---|---|
| User | `bg-gray-100` | `dark:bg-gray-800` |
| Assistant | `bg-white` | `dark:bg-gray-900` |
| User avatar | `bg-gray-300` | `dark:bg-gray-600` |
| Assistant avatar | `bg-orange-100` | `dark:bg-orange-900/30` |

### Health indicator dot

| Status | Class |
|---|---|
| OK | `bg-green-500` |
| Degraded | `bg-yellow-400` |
| Offline | `bg-red-500` |
| Checking | `bg-gray-400` |

### System note pill

```
text-xs text-gray-500 bg-gray-100 dark:bg-gray-800 px-3 py-1 rounded-full
```

---

## Dark mode

- Controlled by the `dark` class on `<html>` — Tailwind `darkMode: 'class'`
- Toggled in `App.jsx` via `document.documentElement.classList.toggle('dark', theme === 'dark')`
- Persisted in `localStorage` under key `lumen-theme`
- Default: follows `window.matchMedia('(prefers-color-scheme: dark)')`

---

## Animations

Defined in `tailwind.config.js` and `index.css`:

| Name | Usage | Definition |
|---|---|---|
| `.message-enter` | New chat bubbles slide in | `opacity:0 translateY(10px)` → `opacity:1 translateY(0)` over 0.3s |
| `.typing-dot` | Three-dot typing indicator | Scale 0→1→0 at 1.4s, staggered with `animation-delay` |
| `.flame` | Flame icon glow | CSS `filter: drop-shadow(0 0 6px rgba(255,255,255,0.6))` |

---

## Flame icon

Single SVG path, reused across the app via `<FlameIcon className="..." />`:
```
M12 2C10 6 8 8 8 11C8 13 9 15 10 16C9 16 8 15 7 14C6 18 8 21 12 22C16 21 18 18 17 14C16 15 15 16 14 16C15 15 16 13 16 11C16 8 14 6 12 2Z
```

Add the `.flame` CSS class to apply the glow filter.

---

## Scrollbar

Styled globally in `index.css`:
- Width: 8px
- Track: transparent
- Thumb (light): `#cbd5e1`
- Thumb (dark): `#475569`
- Thumb hover: `#94a3b8`

---

## Component sizing reference

| Component | Key dimensions |
|---|---|
| Header | `h-14`, `px-4` |
| Sidebar | `w-64` |
| Chat max-width | `max-w-3xl mx-auto` |
| Message bubble max-width | `max-w-[85%]` |
| Avatar size | `w-8 h-8 rounded-full` |
| Input padding | `py-3.5 px-2` |
| Send button | `p-2 m-1.5 rounded-xl` |
| Input container | `rounded-2xl` |

---

## See also

- Components: `frontend/src/components/`
- Global styles: `frontend/src/index.css`
- Tailwind config: `frontend/tailwind.config.js`
- Reference HTML: `frontend/original_index.html`
- Frontend developer guide: `frontend/AGENTS.md`
