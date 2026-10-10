import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // MapLibre loads its worker as a separate ES module resolved at runtime from
  // import.meta.url, which bundlers cannot see. Dev: serve the package as-is so
  // that URL resolves. Build: MapView imports the worker explicitly as an ES
  // module worker and hands its URL to MapLibre (see components/MapView.tsx).
  optimizeDeps: { exclude: ['maplibre-gl'] },
  worker: { format: 'es' },
  server: {
    // In development the Django API runs on :8000; proxying keeps the frontend
    // same-origin so the browser code is identical to the nginx-served build.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  preview: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
