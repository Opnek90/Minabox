import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

// Eigene Config statt eines test-Blocks in vite.config.ts: Der Produktionsbuild
// zieht PWA- und Kompressions-Plugins mit, die im Testlauf nur Zeit kosten.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  define: {
    // In vite.config.ts aus dem Build-Zeitpunkt erzeugt; im Test konstant.
    __BUILD_ID__: JSON.stringify('test'),
  },
  test: {
    // 5 s (Vitest-Standard) reicht auf einem Raspberry Pi nicht: die
    // Interaktionstests von MediaImportDialog brauchen dort allein schon
    // knapp 5 s, unter Last kippen sie darueber. Eine Suite, die zufaellig
    // rot wird, taugt nicht als Waechter in der CI.
    testTimeout: 20_000,
    // A handful of interaction tests drive real MUI transitions (tooltip
    // fade-out, dialog open) and poll with React Testing Library's 1 s async
    // default. On the shared CI runner those routinely lose the race even
    // though they are correct - the assertion is just late. One retry turns
    // that noise into a pass; a genuinely broken test still fails twice.
    retry: process.env.CI ? 2 : 0,
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
