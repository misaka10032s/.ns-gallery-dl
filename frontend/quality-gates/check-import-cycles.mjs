#!/usr/bin/env node
// G4 — "no NEW import cycle relative to a version-controlled baseline."
//
// Tool: madge. Explicitly scanned root is 'src' ONLY (never '.' / the frontend/ package root)
// — this is the scope guard: node_modules, dist, coverage, and any gitignored scratch dir such
// as frontend/tmp/ live OUTSIDE src/, so they are structurally invisible to this gate no matter
// what a tool's own default excludes are. Plain JS + Vue project (no TypeScript), so no
// tsConfig / path-alias resolution is needed — madge's default resolver handles the single
// `@` -> `src` alias already declared in vite.config.js because @ resolves the same way
// relative imports do once files live inside src/.
//
// This does NOT clean up pre-existing cycles — it only blocks NEW ones.
import madge from 'madge'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const cwd = process.cwd()
const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASELINE_PATH = path.join(__dirname, 'import-cycle-baseline.json')

function cycleKey(cycle) {
  return [...cycle].sort().join('|')
}

async function findCycles() {
  const res = await madge(path.join(cwd, 'src'), {
    fileExtensions: ['js', 'vue'],
  })
  return res.circular()
}

function loadBaseline() {
  if (!fs.existsSync(BASELINE_PATH)) return []
  return JSON.parse(fs.readFileSync(BASELINE_PATH, 'utf-8'))
}

async function main() {
  const updateMode = process.argv.includes('--update-baseline')
  const current = await findCycles()

  if (updateMode) {
    fs.writeFileSync(BASELINE_PATH, JSON.stringify(current, null, 2) + '\n')
    console.log(`[G4] baseline updated — ${current.length} cycle(s) recorded at ${path.relative(cwd, BASELINE_PATH)}.`)
    return 0
  }

  const baseline = loadBaseline()
  const baselineKeys = new Set(baseline.map(cycleKey))
  const currentKeys = new Set(current.map(cycleKey))

  const newCycles = current.filter((c) => !baselineKeys.has(cycleKey(c)))
  const resolvedCycles = baseline.filter((c) => !currentKeys.has(cycleKey(c)))

  if (resolvedCycles.length > 0) {
    console.log(`[G4] note: ${resolvedCycles.length} baseline cycle(s) no longer exist — consider re-running with --update-baseline to shrink the baseline:`)
    for (const c of resolvedCycles) console.log(`  - ${c.join(' -> ')}`)
  }

  if (newCycles.length > 0) {
    console.error(`[G4] FAIL — ${newCycles.length} NEW import cycle(s) not present in the baseline:`)
    for (const c of newCycles) console.error(`  - ${c.join(' -> ')} -> ${c[0]}`)
    console.error(`\nBaseline: ${path.relative(cwd, BASELINE_PATH)} (${baseline.length} pre-existing cycle(s), unaffected).`)
    return 1
  }

  console.log(`[G4] PASS — ${current.length} total cycle(s), 0 new vs baseline (${baseline.length} pre-existing).`)
  return 0
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error('[G4] gate crashed:', err)
    process.exit(1)
  })
