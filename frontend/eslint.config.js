import eslint from '@eslint/js';
import { defineConfig } from 'eslint/config';
import svelte from 'eslint-plugin-svelte';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default defineConfig(
  {
    ignores: [
      '**/.svelte-kit/**',
      '**/build/**',
      '**/node_modules/**',
      '**/playwright-report/**',
      '**/test-results/**',
      '**/static/gource/vendor/**',
      '**/.venv/**',
      '**/target/**',
      '**/.runtime/**'
    ]
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  ...svelte.configs.recommended,
  ...svelte.configs.prettier,
  {
    languageOptions: {
      globals: { ...globals.browser, ...globals.node }
    }
  },
  {
    files: ['**/*.svelte', '**/*.svelte.ts', '**/*.svelte.js'],
    languageOptions: {
      parserOptions: { parser: tseslint.parser }
    }
  }
);
