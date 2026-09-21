// Flat ESLint config (ESLint v9+). Mirrors the standard Vue 3 + TypeScript
// setup (`npm create vue@latest`'s own generated config): Vue's recommended
// rules plus the official Vue/TypeScript bridge, scoped to source files only
// so generated output, tooling configs and node_modules are never linted.
import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import vueTsEslintConfig from '@vue/eslint-config-typescript'

export default [
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },
  {
    name: 'app/files-to-ignore',
    ignores: ['**/dist/**', '**/dist-ssr/**', '**/coverage/**', '**/node_modules/**'],
  },

  js.configs.recommended,
  ...vue.configs['flat/recommended'],
  ...vueTsEslintConfig(),

  {
    rules: {
      // Vue's <script setup> pattern regularly leaves props/emits destructured
      // for type inference without every one being read in the template.
      'vue/multi-word-component-names': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // Vuetify's `v-data-table` uses dynamic slot names shaped like
      // `item.<header-key>` (e.g. `#item.role`, `#item.is_active`) as a
      // documented, intentional convention — this rule's generic "v-slot
      // doesn't support modifiers" check can't distinguish that dotted slot
      // name from an actual (invalid) directive modifier and flags it as an
      // error either way.
      'vue/valid-v-slot': 'off',
    },
  },
  {
    // A near-verbatim copy of vue/jsx.d.ts (see the comment inside the file
    // for why it has to be inlined) — it is meant to match that upstream
    // declaration exactly, not this project's own lint rules. Placed after
    // the recommended configs above: flat config applies later array
    // entries on top of earlier ones for the same files, so an override
    // placed before them would just get re-enabled by the recommended sets.
    name: 'app/vendor-type-shims',
    files: ['src/jsx.d.ts'],
    rules: {
      'vue/prefer-import-from-vue': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },
]
