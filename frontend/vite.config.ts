import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend FastAPI di :8000; /api, /audio, /avatar-assets, dan /ws diteruskan supaya frontend tidak perlu CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/audio': 'http://127.0.0.1:8000',
      '/avatar-assets': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})
