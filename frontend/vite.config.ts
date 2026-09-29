import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { readFileSync } from 'fs'

// La versione arriva da package.json, che `scripts/release.py` aggiorna a
// ogni rilascio: così il numero a piè di pagina è quello del build, non uno
// scritto a mano in un componente e dimenticato lì.
const { version } = JSON.parse(readFileSync(path.resolve(__dirname, 'package.json'), 'utf-8'))

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: process.env.PORT ? parseInt(process.env.PORT) : 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  // `vite preview` serves the production build, which is the only way to check
  // behaviour without HMR in the way. It needs the same proxy as dev, or every
  // API call 404s against the static server.
  preview: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
