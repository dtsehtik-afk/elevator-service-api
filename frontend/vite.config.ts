import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Capacitor packages are native-mobile-only.
// In web builds we alias them to a stub so the browser never sees bare imports.
const CAPACITOR_STUB = path.resolve(__dirname, 'src/stubs/capacitor-stub.ts')

const CAPACITOR_PACKAGES = [
  '@capacitor/geolocation',
  '@capacitor/push-notifications',
  '@capacitor/background-runner',
  '@capacitor-community/background-geolocation',
  '@capacitor/synapse',
  '@capacitor/core',
  '@capacitor/android',
  '@capacitor/cli',
]

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: Object.fromEntries(CAPACITOR_PACKAGES.map(pkg => [pkg, CAPACITOR_STUB])),
  },
  optimizeDeps: {
    exclude: CAPACITOR_PACKAGES,
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


