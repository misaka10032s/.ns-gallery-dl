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

## Stack
- Backend: Python 3.11 + Flask (API + serves frontend build); SQLite at `data/app.db`
- Frontend: Vue 3 + Vite 8 + Pinia + vue-router; SCSS (sass)
- Download engines: gallery-dl, yt-dlp — both pip-managed via `venv`, invoked as subprocesses
  (yt-dlp resolves through PATH/venv `Scripts`, NOT a standalone `.exe`; the old sibling
  `.ns-yt-dlp` repo fallback is gone — that repo no longer exists)
- Bot: Discord (Python)
- Chrome extension: `chromeExtension/` (selection export, site-nav, omnibox, redirect cleanup) —
  before touching the selection engine (`chromeExtension/static/module/selector-*.js`), see
  `docs/blueprint/entries/BP-EXT-SELECTION-1.md` (approved design, binding decisions; spec linked
  via its `superpowers:` field at `docs/superpowers/specs/selection-mode-v2-spec.md`)
- External repos absorbed — do NOT modify: `javascript/ns-chrome-tool`
- **Windows:** use `python` (not `python3`)

### Downloader package updates (yt-dlp / gallery-dl)
- Central registry: `app/config/downloaders.py` `DOWNLOADER_PACKAGES` — add a future downloader
  in ONE line here; `app/services/updater_service.py`, the manual API endpoint, and the launcher
  `-u`/`-update` flag all derive from it.
- **Reactive only** — on a download failure classified as a "stale extractor" error (tight,
  centralized signature list in `updater_service.STALE_EXTRACTOR_SIGNATURES`), the failing
  provider's package is upgraded via pip and the job retries ONCE. A cooldown + "already
  installed version" guard (`app/config/downloaders.py` `UPDATE_COOLDOWN_SECONDS`,
  `app/storage/repositories/downloader_state_repo.py`) prevents mindless update→fail→update loops.
- **Manual** — `POST /api/downloaders/update` (same-origin guarded, refuses 409 while a job is
  running) + a "更新下載器" button in the Web UI header.
- **Launcher `-U`** — `dl.cmd -u` / `dl.sh -u` also force-updates every registered downloader
  package via the same registry.
- **NO scheduled / daily / every-startup auto-update** — by design, to keep startup fast and
  avoid pointless upstream churn.

## Run commands

### Launcher (`dl.cmd` / `dl.sh`)
| Flag | Action |
|---|---|
| `-s` | Start server + UI (auto-rebuilds frontend if source changed) |
| `-b` | Start Discord bot |
| `-s -b` | Start both |
| `-u` | Reinstall / update dependencies (also force-updates yt-dlp / gallery-dl) |
| `-h` | Show help |

Web UI: `http://127.0.0.1:7601/` — pages: `/`, `/history`, `/queue`, `/jobs`, `/cookies`

### Frontend
```bash
cd frontend && npm install
npm run build   # outputs to app/ui/ (served by Flask)
npm run dev     # dev server at 127.0.0.1:5173
```

## Dev commands

### Python — install dev/gate tooling
```bash
py -3.11 -m pip install -r requirements-dev.txt
```
Use `py -3.11` (the cluster-standard interpreter — NEVER bare `python`/`python3`, see global
CLAUDE.md). The repo's own `venv/` (Python 3.13) carries only runtime deps (Flask, gallery-dl,
yt-dlp, discord.py, …) — no pytest/ruff/mypy — and this repo's own CLAUDE.md states "Python
3.11", so `py -3.11` is both the intended-version match AND where the dev tooling actually
lives; it's used for every gate command below.

### Python — lint / typecheck / test
```bash
py -3.11 -m ruff check app module tests          # G1 (bare, unbaselined view)
py -3.11 -m mypy app --ignore-missing-imports     # G2 (bare, unbaselined view)
py -3.11 -m pytest -q                             # G3 — 12 test files, 197 tests, ~4-6s
```

### Frontend — lint / test
```bash
cd frontend
npm run lint    # eslint . (repo-wide, will show the pre-existing 541-warning backlog — G1 itself is diff-scoped, see below)
npm run test    # vitest run (JobsView.spec.js et al.; a zero-test-file result now FAILS the gate — see G3 below)
```

## Code quality gates

Two independent gate families — Vue/JS (`frontend/quality-gates/`, npm scripts) and Python
(`quality-gates/`, `run.py`) — because this repo is a genuine hybrid (Vue 3 + Vite frontend,
Flask + Discord-bot Python backend). Installed 2026-08-27; every gate below was proven to
actually fail before shipping (plant a known violation -> non-zero exit -> revert -> green
again) — a gate that could not be proven able to fail was dropped rather than faked (see
"Dropped for this repo" below).

**Every scan is explicitly scoped** — never a bare `.`/repo-root scan — so a gitignored scratch
file (this repo has several root-level working dirs: `venv/`, `download/`, `save/`, `data/`,
plus `frontend/tmp/` reserved for scratch scripts) can never become a gate input:
- Python: ruff/mypy scan `app module tests` by name (not `.`); pytest is pinned to
  `testpaths = ["tests"]` in `pyproject.toml` — a stray `test_*.py` dropped in `download/` is
  invisible to it. Proven both ways (planted a failing test in `download/scratch/` -> pytest
  exit 0; the same test moved into `tests/` -> exit 1).
- Frontend: madge (G4) scans `src/` only, never the package root; vitest's `test.include` is
  pinned to `src/**/*.{test,spec}.{js,mjs,cjs}` in `vite.config.js` (vitest's own default
  recursive glob is NOT relied on — a sibling repo's rollout shipped exactly that vacuous-scope
  bug, where a gitignored `frontend/tmp/` scratch test silently blocked every commit). Proven
  both ways (planted a failing test in `frontend/tmp/` -> `vitest run` exit 0; the same test
  moved into `src/` -> exit 1).
- The diff-scoped gates (frontend G1/G3b, Python G3b) inherit this for free: `git diff` can
  never see an untracked/gitignored file in the first place.

### Python — `py -3.11 quality-gates/run.py <g1|g2|g3|g4|g5|l0|l1> [--update-baseline]`

| Gate | What | Scope | Baseline (2026-08-27) |
|---|---|---|---|
| G1 | `ruff check app module tests` (select E,F,I,B,UP,RUF) | 49 pre-existing findings baselined (`ruff-baseline.json`), mostly `I001` unsorted-imports / `F401` unused-import — none fixed, only blocked from growing |
| G2 | `mypy app` (non-strict — see `pyproject.toml` `[tool.mypy]` for why not `strict=true`) | 12 pre-existing errors baselined (`mypy-baseline.json`) across 8 files |
| G3 | `pytest -q` (green) + AST assertion-presence on changed test functions (`check_test_assertions.py`) | 197 tests, all green |
| G4 | `import-linter` `layers` contract: `app.api > app.services > app.providers > app.domain > app.storage > app.config` | 4 pre-existing violations baselined (`import-cycle-baseline.json`) — `app.providers.*` genuinely calls `app.services.path_service`/`token_service` for filesystem/auth helpers; this is a real working dependency, not cleaned up, only blocked from growing |
| G5 | `pytest --cov=app --cov-report=xml` then `diff-cover --fail-under=60` | diff coverage of changed lines only |
| ~~G6~~ | mutation testing | **REMOVED cluster-wide for Python** — `mutmut` 3.x refuses to start on native Windows at all ("use WSL"), exit 1 unconditionally before mutating anything. Not attempted; recorded, not faked. |

`l0` = G1+G2+G3+G4 (~8s on the untouched tree). `l1` = l0+G5 (~15s).

**A baseline measured in a worktree goes stale if the merge target moves.** Regenerate it
against the merge target (`main`) immediately before merging, not at branch-cut time — a
baseline is a snapshot of a moving tree, not a fixed spec.

**G4 vacuous-gate finding (fixed):** before this install, `app/api`, `app/config`, `app/domain`,
`app/providers`, `app/services`, `app/storage` (and 5 `app/providers/*` subpackages) had NO
`__init__.py` — implicit PEP 420 namespace packages. import-linter's analysis engine (grimp
3.15) cannot see into a subpackage without one, so the contract silently reported "0
violations" on every run — not because the tree was clean, but because it couldn't find the
code at all (`Missing layer 'app.api': module app.api does not exist.`, an ERROR that the
original wrapper script didn't distinguish from a clean pass). Fixed by adding empty
`__init__.py` to all 11 affected directories (zero behavior change — verified via
`python -c "import app.main"`, the full pytest suite, and a grep for any namespace-package-only
API usage, all clean) — and `check_import_cycles.py` now fails loud instead of silently passing
if this regresses. **Do not remove those `__init__.py` files.**

**G1/G2 fail-open fix (2026-08-27 — closed a cluster-wide gap, see
`D:/backup/CSIA/@PM/state/runs/CROSS-REPO-mypy-failopen.md`):** neither `mypy` nor `ruff`
crashes on a broken/missing `[tool.mypy]` / `[tool.ruff]` config — both can silently fall back
to bare defaults (mypy) or hard-fail with empty stdout that used to be misread as "0 findings"
(ruff), and the old checker scripts only ever read stdout, never the return code or stderr.
**Reproduced here concretely** (measured, not assumed): planting a syntactically-valid but
unrecognized key under `[tool.mypy]` made mypy print a config-parse warning to stderr while
`check_mypy_baseline.py` silently reported `[G2] PASS` unchanged — the config problem was
invisible. The same corruption under `[tool.ruff]` made ruff exit 2 with **empty stdout**,
which the old script coerced to `"[]"` (via `proc.stdout or "[]"`), so all 49 baselined ruff
violations "vanished" at once and `check_ruff_baseline.py` reported `[G1] PASS — 0 total
violation(s)`. Both are now fixed, same two-part shape in both `check_mypy_baseline.py` and
`check_ruff_baseline.py`:
1. **Validate the config before trusting the run.** A static `tomllib` check confirms
   `pyproject.toml` exists, parses as TOML, and carries the relevant `[tool.mypy]` /
   `[tool.ruff]` table — BEFORE the tool even runs. Both checkers also now pass an explicit
   `--config-file` (mypy) / `--config` (ruff) instead of relying on silent auto-discovery.
   That alone is not sufficient (a syntactically valid but semantically bad option, e.g. a
   typo'd key, passes static TOML validation) — each script also checks the tool's own signal
   after running: mypy's config diagnostics are matched in stderr (mypy prefixes every
   config-loading problem with the config file's path, empty on a clean run); ruff's config/tool
   errors are caught via its own return-code contract (0 clean / 1 violations found / 2
   tool-or-config error — any other code is now a hard FAIL, never silently read as "0
   findings"). A config problem detected either way is `[G1]`/`[G2]` **FAIL, exit 2**, naming
   the exact diagnostic — never a silent PASS.
2. **A vanished baseline finding is now a FAILURE, not an ignorable note.** Previously, if a
   finding present in `mypy-baseline.json`/`ruff-baseline.json` stopped appearing, the gate
   printed `note: N baseline error(s) no longer exist — consider shrinking the baseline` and
   still returned PASS. That silence is exactly what a future silent-profile-disable mechanism
   (not just a broken TOML — any way the check could stop applying) would produce, so it is now
   `[G1]`/`[G2]` **FAIL, exit 1**, naming every vanished finding. **This is the durable half** —
   it catches the disappearance regardless of cause, not only the specific TOML-corruption
   mechanism part 1 targets.
   - **To legitimately shrink a baseline now** (a real fix landed, or a deliberate baseline
     realignment): confirm *why* the finding vanished first, then run
     `py -3.11 quality-gates/run.py g1 --update-baseline` (or `g2`) to re-snapshot. Do **not**
     run `--update-baseline` reflexively just to unblock a FAIL without checking the cause —
     that reintroduces exactly the blind spot this fix closes.
   - **Cost to routine development, stated plainly:** a normal commit that happens to
     incidentally fix one of the pre-existing baselined findings as a side effect (not the
     commit's main goal) will now FAIL until `--update-baseline` is run — this is an intended
     tradeoff, not a bug. The ruff baseline (49 entries) was realigned right before this fix
     landed (2026-08-27); that realignment is unaffected (it's the current committed baseline,
     not a vanished-vs-baseline diff), but any *future* incidental fix to one of those 49 needs
     the same explicit re-snapshot step.
   - **Measured non-reproduction, for the record:** a full TOML syntax error (duplicate
     `[tool.mypy]` key) or deleting `pyproject.toml` outright does NOT, on its own, cause a
     vanishing-findings PASS in this repo's *current* mypy config — losing
     `ignore_missing_imports = true` only ever ADDS spurious `import-untyped` findings here
     (this repo's only non-default mypy setting is a suppressor, not a strictness gate), so
     those two specific corruptions were already visible as an (unexplained) FAIL even before
     this fix. Relying on that coincidence was the actual risk — part 1's stderr/returncode
     checks make the FAIL explicit and correctly attributed instead of accidental.

**G1/G2/G4 guard-ordering fix (2026-08-27 — closed a SECOND fail-open introduced BY the fix
above):** point 2 above made a vanished baseline finding `FAIL, exit 1` on a plain run — but
the original `main()` had TWO separate defects, both confirmed by direct execution here (not
inferred from reading line numbers):
1. **Plain-run ordering.** `check_ruff_baseline.py`/`check_mypy_baseline.py` checked
   `if resolved: ... return 1` BEFORE it ever checked `if new:`. `check_import_cycles.py` (G4)
   had the mirror gap: it only ever printed `resolved` as an ignorable stdout note, never
   failing on it at all.
2. **The `--update-baseline` path itself, in ALL three gates** — the deeper defect: the
   `--update-baseline` branch ran BEFORE the baseline was even loaded/diffed against `current`,
   so it wrote `current` to disk unconditionally with NO check of `new` whatsoever, in ANY
   state — not only after a plain-run FAIL.

Net effect: a commit that simultaneously fixed one baselined finding AND introduced an
unrelated new one was told ONLY about the resolved finding on a plain run, and — separately —
running the gate's own suggested `--update-baseline` remedy in that same state silently baked
the unreviewed new finding into the baseline, hiding it permanently. **Reproduced concretely
for all three, both defects** (2026-08-27, in a throwaway worktree, fully reverted after, every
touched file hash-verified back to `HEAD`):
- G1: fixed the real baselined `app/main.py|F401` finding while planting a new
  `app/domain/enums.py|F401` — the plain run reported only the resolved finding, and running
  `--update-baseline` in that exact state absorbed the new one without a word.
- G2: fixed the real baselined `download_service.py|valid-type` finding (bare `callable` used
  as a type annotation instead of `Callable`) while planting a new `features.py|assignment`
  type error — same outcome.
- G4: removed the real baselined `app.providers.ytdlp.provider -> app.services.path_service`
  edge while planting a new illegal `app.config.features -> app.storage.db` cross-layer
  import — same outcome (the vanished entry printed only as a footer note; `--update-baseline`
  absorbed the new violation).

**Fix, one consistent shape across all three gates — a single shared function
(`quality-gates/lib/baseline.report_and_decide()`), not three near-copies, so they cannot drift
apart on this again:**
1. `new`/`resolved` are computed ONCE, up front, before EITHER the plain-run branch or the
   `--update-baseline` branch can act.
2. A plain run FAILs (exit 1) if EITHER set is non-empty, and reports **both** — never only one.
3. `--update-baseline` REFUSES to write (exit 1, zero file change) **only when BOTH `new` and
   `resolved` are non-empty** — that is the one state where a plain re-snapshot is genuinely
   ambiguous (it would silently accept the new finding as if it were the same kind of reviewed
   decision as the shrink). A **new-only** run (deliberately accepting a finding as debt) or a
   **resolved-only** run (shrinking for a genuine fix) still PROCEEDS — this is a real,
   documented, legitimate use of `--update-baseline` (each checker's own docstring: "a
   deliberate, reviewed cleanup (**or knowingly accepting a new one**)") — but now names every
   finding it is about to accept or remove, not just a count. Deliberately a hard refusal
   rather than "print a warning and write anyway" — a printed warning can go unread in a
   non-interactive/CI invocation (a scripted `--update-baseline && git commit`); a refusal
   cannot be missed.

All four run-states proven for G1, G2, and G4 (new-only / vanished-only / both-at-once /
neither), exit codes confirmed for each, PLUS `--update-baseline`'s behavior verified
separately in every state: new-only and resolved-only both succeed (exit 0) and name the
finding they act on; both-at-once refuses (exit 1, baseline file byte-for-byte unchanged). See
the "ORDERING FIX" docstring block at the top of each of the three checker scripts, and
`report_and_decide()`'s own docstring in `quality-gates/lib/baseline.py`, for the exact
reproduction evidence.

### Frontend — `cd frontend && npm run gate:<g1|g3|g4|l0|l1>`

| Gate | What | Scope | Baseline (2026-08-27) |
|---|---|---|---|
| G1 | ESLint, diff-LINE-scoped (only messages on lines the diff actually touched) | 541 pre-existing warnings repo-wide (all `eslint-plugin-vue` stylistic rules — `max-attributes-per-line`, `singleline-html-element-content-newline`, `html-self-closing`; 0 errors) made a bare `--max-warnings=0` unusable, so this gate uses the same line-diff scoping misaka_site2.0 uses for the same reason, at a smaller scale |
| G3 | `vitest run` (green, `passWithNoTests: false`) + `@vitest/eslint-plugin` `expect-expect` on changed test files | `src/views/JobsView.spec.js` (4 tests, real assertions on `jobs.error` rendering + the search filter) — a zero-matched-test-file result now hard-FAILs (fixed 2026-09-01, see below); grows as more tests are added |
| G4 | `madge` circular-import check on `src/` | 0 pre-existing cycles |
| `l1` | = `l0` (no G5/G6 — see below) | |

**G3 vacuous-gate finding (fixed 2026-09-01):** `frontend/vite.config.js`'s `test` block set
`passWithNoTests: true` with the justification "0 test files today, must still be a PASS". That
made `npm run gate:g3`/`vitest run` report PASS on a matched-zero-test-files result exactly the
same as a genuinely green suite — indistinguishable, and it stayed that way since the gate was
installed (2026-08-27) with nothing ever guarding a frontend regression. Fixed by (1) writing the
first real frontend test (`src/views/JobsView.spec.js`, not a placeholder — see file for what it
asserts) and (2) removing the `passWithNoTests: true` override (left at vitest's own default,
`false`), so a future "all tests deleted" state hard-fails instead of passing. Proven both ways:
deleting the test file made `gate:g3:test` exit non-zero with `No test files found`; restoring it
went back to green. **Do not re-add `passWithNoTests: true`** without also adding a gate that
separately checks "at least one test file exists" — otherwise this defect just moves one layer.

**Dropped for this repo, with evidence (not faked):**
- **G2 (typecheck)** — this frontend has **zero TypeScript**: 0 `.ts`/`.tsx` files, no
  `tsconfig.json` (verified via `find frontend -name "*.ts"`, 2026-08-27; all 26 source files
  are `.vue`/`.js`). Wiring `vue-tsc`/`jsconfig.json` `checkJs` against fully unannotated JS
  would inherit exactly the vacuous-checker failure this cluster already documented for
  `vue-tsc --noEmit` on misaka_site2.0 (proven exit-0-on-a-real-bug case) — near-zero type
  inference without any annotations gives false assurance, not real protection. Converting the
  frontend to TypeScript is a real option but is a 26-file rewrite outside this task's scope
  (minimal-diff rule) — revisit if/when the frontend adopts TS.
- **G5 (diff coverage) / G6 (mutation)** — this frontend has one test file today (vs the Python
  side's 12 files / 197 tests). A coverage or mutation-kill threshold against a single file is
  still theatre, not signal — skip until real coverage exists across more components, then
  reconsider both.

### Enabling the pre-commit hook
```bash
git config core.hooksPath .githooks
```
`.githooks/pre-commit` derives which stack(s) a commit touches from the staged file list and
runs only that stack's `l0` (frontend `frontend/*` staged -> `npm run gate:l0`; Python
`{app,module,scripts,tests}/*.py` staged -> `py -3.11 quality-gates/run.py l0`) — a
docs-only or config-only commit runs neither and exits immediately. `core.hooksPath` is
per-clone local config; it does not travel with the repo, so run the command above again on
any fresh clone or machine.

## Project structure
```
frontend/           Vue + Vite + Pinia source (styles/ = shared SCSS partials)
app/
  api/              Flask app + API entry (routes/: history/queue/jobs/auth/misc/pages/downloaders)
  config/           paths, env config, feature flags, downloader package registry
  domain/           job / provider / status types
  providers/        gallery-dl, yt-dlp, site-specific, cookies
  services/         queue, history, bot, token, bridge, downloader updater
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

## Gotchas
- **Web UI:** navigate ONLY via the left menu — direct URL navigation fails to render.
- **Data / schema:** verify data and schema by querying `data/app.db` directly — never infer schema from code.

## graphify
Before answering architecture/code questions: check `graphify-out/GRAPH_REPORT.md` for core
nodes; if `graphify-out/wiki/index.md` exists, browse the wiki before reading source files.
After code changes in this session, keep the graph in sync:
`python -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"`

## Skills (must use)
- **`superpowers:brainstorming`** — required before any new feature, improvement, or architecture change
- **`frontend-design`** — required for all frontend UI work (Vue components, pages, styles)
- **graphify** — use knowledge graph to assist design (see §graphify above)
