import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  base: '/ui/',
  build: {
    outDir: '../app/ui',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    // EXPLICIT scope — do NOT fall back to vitest's default recursive glob. That default would
    // also pick up any gitignored scratch test dropped under frontend/tmp/ (see .gitignore) and
    // fail the gate on a file nobody meant to ship — the exact defect this line exists to close
    // (found in a sibling repo's quality-gate rollout, 2026-08-27). Only files inside src/ are
    // ever gate inputs.
    include: ['src/**/*.{test,spec}.{js,mjs,cjs}'],
    exclude: ['node_modules/**', 'dist/**', 'coverage/**', 'tmp/**'],
    passWithNoTests: true, // this project has 0 test files today — 0 tests must be a PASS, not a broken gate
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/**'],
      exclude: ['src/**/*.{test,spec}.{js,mjs,cjs}'],
    },
  },
})
