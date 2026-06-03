import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Capacitor packages are native-mobile-only.
// In web builds we alias them to a stub so the browser never sees bare imports.
const CAPACITOR_STUB = path.resolve(__dirname, 'src/stubs/capacitor-stub.ts')

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@capacitor/push-notifications': CAPACITOR_STUB,
      '@capacitor/geolocation': CAPACITOR_STUB,
      '@capacitor/background-runner': CAPACITOR_STUB,
      '@capacitor-community/background-geolocation': CAPACITOR_STUB,
      '@capacitor/synapse': CAPACITOR_STUB,
    },
  },
  server: {
    port: parseInt(process.env.PORT || '5173'),
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})


