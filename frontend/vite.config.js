import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/upload':   { target: 'http://localhost:8081', changeOrigin: true },
      '/projects': { target: 'http://localhost:8081', changeOrigin: true },
      '/auth':     { target: 'http://localhost:8081', changeOrigin: true },
      '/process':  { target: 'http://localhost:8081', changeOrigin: true },
      '/static':   { target: 'http://localhost:8081', changeOrigin: true },
    },
  },
})
