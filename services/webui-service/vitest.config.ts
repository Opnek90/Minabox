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
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
