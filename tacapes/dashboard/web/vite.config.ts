import path from 'node:path';
/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// FastAPI is the source of truth for /api/* and /healthz in dev mode.
// Vite serves the React app at :5173 and proxies these through to uvicorn on :8732.
//
// In prod, `pnpm build` writes dist/, FastAPI mounts it as static and serves
// index.html for any unmatched route (SPA fallback in tacapes/dashboard/app.py).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api':     { target: 'http://127.0.0.1:8732', changeOrigin: false },
      '/healthz': { target: 'http://127.0.0.1:8732', changeOrigin: false },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    emptyOutDir: true,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
