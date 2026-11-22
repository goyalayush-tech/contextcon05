import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The production build goes straight into the FastAPI static folder, so `uvicorn` alone serves the UI.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  build: { outDir: '../flightback/static/dist', emptyOutDir: true },
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
