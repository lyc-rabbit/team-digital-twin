import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const LOCAL_PROXY_PORT = '7897'
for (const key of Object.keys(process.env)) {
  if (!/^(https?|all|ftp|ws|wss)_proxy$/i.test(key)) continue
  const value = String(process.env[key] || '')
  if (value.includes(LOCAL_PROXY_PORT)) delete process.env[key]
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
})
