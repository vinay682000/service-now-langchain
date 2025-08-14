import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Proxy all /chat requests to your backend
      '/chat': {
        target: 'https://studious-bassoon-xx7vwvqxq7jcvv4g-8000.app.github.dev',
        changeOrigin: true,
        secure: false, // skip SSL verification in Codespaces
      },
    },
  },
})
