// ESLint flat config — Vue 3 + plain JS (this project carries ZERO TypeScript: 0 .ts files,
// no tsconfig.json — verified by `find . -name "*.ts"` at gate-install time, 2026-08-27).
// Do not add @typescript-eslint/typescript-eslint here unless the project actually adopts TS —
// see `.claude/CLAUDE.md` -> `## Code quality gates` for why G2 (typecheck) was dropped instead
// of wired against untyped JS.
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'

export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**', '.vite/**'],
  },

  js.configs.recommended,

  ...pluginVue.configs['flat/recommended'],

  {
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      // Plain-JS project — no type system to catch unused args, so keep this lenient enough
      // for the common `catch (err) {}` / handler-signature patterns already in this codebase.
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'vue/multi-word-component-names': 'off', // views/*.vue are routed pages, single-word by convention here
    },
  },
]
