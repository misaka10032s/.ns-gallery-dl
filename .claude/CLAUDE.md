# ns-media-hub — AI dev guide

Unified media-download hub (refactored from `ns-gallery-dl`): gallery-dl image-site downloads,
yt-dlp video, Discord bot auto-download, local API + queue/history/jobs/cookies Web UI,
Chrome extension, and centralised cookie management. Backend is Python/Flask; frontend is Vue 3/Vite.

> Cluster conventions (git authority, language, i18n, ports, layout) are BINDING and live at
> D:/backup/CSIA/@PM/.claude/context/cluster-conventions.md — Read it before any work here.

## Delegation & verification
- Orchestration, model tiering, and dispatch rules: D:/backup/CSIA/@PM/.claude/context/model-dispatch-doctrine.md
- Decision rubrics (escalate / done / ask / change course): D:/backup/CSIA/@PM/.claude/context/judgment-rubrics.md
- Whoever produced work never certifies it — verification runs in a fresh-context agent.
- Every done/correct/dead/broken claim carries evidence: file:line, test output, or read-back.
- Target missing or contradicting the task → STOP and ask; never scaffold around it.

## Context index
_(none yet — add files here per @PM taxonomy)_

## Stack
- Backend: Python 3.11 + Flask (API + serves frontend build); SQLite at `data/app.db`
- Frontend: Vue 3 + Vite 8 + Pinia + vue-router; SCSS (sass)
- Download engines: gallery-dl, yt-dlp
- Bot: Discord (Python)
- Chrome extension: `chromeExtension/` (selection export, site-nav, omnibox, redirect cleanup)
- External repos absorbed — do NOT modify: `.ns-yt-dlp`, `javascript/ns-chrome-tool`
- **Windows:** use `python` (not `python3`)

## Run commands

### Launcher (`dl.cmd` / `dl.sh`)
| Flag | Action |
|---|---|
| `-s` | Start server + UI (auto-rebuilds frontend if source changed) |
| `-b` | Start Discord bot |
| `-s -b` | Start both |
| `-u` | Reinstall / update dependencies |
| `-h` | Show help |

Web UI: `http://127.0.0.1:7601/` — pages: `/`, `/history`, `/queue`, `/jobs`, `/cookies`

### Frontend
```bash
cd frontend && npm install
npm run build   # outputs to app/ui/ (served by Flask)
npm run dev     # dev server at 127.0.0.1:5173
```

## Project structure
```
frontend/           Vue + Vite + Pinia source (styles/ = shared SCSS partials)
app/
  api/              Flask app + API entry (routes/: history/queue/jobs/auth/misc/pages)
  config/           paths, env config, feature flags
  domain/           job / provider / status types
  providers/        gallery-dl, yt-dlp, site-specific, cookies
  services/         queue, history, bot, token, bridge
  storage/          SQLite schema + repositories
  ui/               Vite build output (served by Flask; gitignored)
chromeExtension/    Chrome extension (one canonical copy)
module/             legacy entry compat layer
data/               app.db, tokens, cookies
download/           download output (gitignored)
dl.py               Python entry point → app.main
```

## Domain conventions

### Download paths (provider-directed — no hardcoding outside domain registry)
- Discord: guild-only — `download/discord/<guild>/attachments|embeds/`
- Pixiv: author-level — `download/gallery-dl/pixiv.net/<author>/`
- YouTube / X / Facebook: domain-only — `download/ytdlp/<domain>/`

### Cookies
- Canonical path: `cookies/` (old paths auto-migrate on scan)
- `cookies/*` is gitignored — local-private, never commit
- Scan results written to SQLite registry; providers resolve applicable cookie automatically

### Data storage
- All state (jobs, history, cookies registry) in SQLite (`data/app.db`)
- Legacy `data/history.json` auto-migrates to SQLite on init

### `.env` (copy from `.env.example`)
Key fields: `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_IDS`, `BOT_DOMAIN_ALLOWLIST`,
`BOT_DOMAIN_DENYLIST`, `DISCORD_EMOJI_*`

### Site-specific logic
- Preserve nhentai + wnacg specialized download logic — do not generalise away

## graphify
Before answering architecture/code questions: check `graphify-out/GRAPH_REPORT.md` for core
nodes; if `graphify-out/wiki/index.md` exists, browse the wiki before reading source files.
After code changes in this session, keep the graph in sync:
`python -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"`

## Skills (must use)
- **`superpowers:brainstorming`** — required before any new feature, improvement, or architecture change
- **`frontend-design`** — required for all frontend UI work (Vue components, pages, styles)
- **graphify** — use knowledge graph to assist design (see §graphify above)
