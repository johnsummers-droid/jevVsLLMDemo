import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://localhost:8000',
    },
    // The app imports shared/schema/payloads.schema.json (the inspector's schema preview). Paths
    // are relative to web/; listing them replaces Vite's default, so web/ itself is included.
    fs: {
      allow: ['.', '../shared/schema'],
    },
  },
  test: {
    environment: 'jsdom',
  },
})
