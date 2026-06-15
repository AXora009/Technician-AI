# Technician AI — Frontend

React SPA built with Bun + Vite + Tailwind CSS v4 + shadcn/ui.

## Prerequisites

- [Bun](https://bun.sh/) v1.1+

## Development

```bash
# Install dependencies
bun install

# Start dev server (proxies /api/* to localhost:8000)
bun dev
```

The Vite dev server runs on `http://localhost:5173` and proxies all `/api/*` requests to the FastAPI backend at `:8000`. Make sure the backend is running:

```bash
# From the repo root
source .venv/bin/activate
python app.py
```

## Build for Production

```bash
bun run build
```

This outputs optimized assets to `../static/` (the repo root's `static/` directory). The FastAPI backend serves these automatically — no separate frontend server needed.

## Deployment

1. `cd frontend && bun install && bun run build`
2. `cd .. && python app.py`
3. Open `http://localhost:8000`

The backend serves:
- `/api/*` — JSON API endpoints
- `/assets/*` — JS/CSS bundles (from Vite build)
- `/*` — SPA fallback (`static/index.html`)

## Project Structure

```
src/
├── main.tsx                  # Entry point
├── App.tsx                   # Layout shell
├── index.css                 # Tailwind + theme variables
├── types/api.ts              # API response types
├── hooks/
│   ├── use-api.ts            # Fetch wrapper for all endpoints
│   └── use-theme.ts          # Dark/light mode toggle
├── context/
│   └── theme-provider.tsx    # Theme context provider
├── components/
│   ├── ui/                   # shadcn/ui base components
│   ├── layout/               # Header, Sidebar
│   ├── ask/                  # AskForm, AnswerCard, SourceList, FeedbackWidget
│   ├── knowledge/            # TopicTree, KnowledgeEntry, EntryList
│   ├── ingest/               # UploadForm (drag-and-drop)
│   └── shared/               # ThemeToggle, TagBadge, Spinner
└── lib/utils.ts              # cn() helper
```

## Theming

The app supports **light** and **dark** modes. Toggle with the button in the header (cycles: light → dark → system).

Theme colors are defined as CSS variables in `src/index.css`, mapped to the letterhead design palette:
- Light: warm paper tones (`#f7f4ec` background, `#9a2b1f` crimson accent)
- Dark: warm dark grays (`#1a1816` background, `#c4493b` lighter crimson)

### Adding shadcn components

```bash
bunx --bun shadcn@latest add <component-name>
```
