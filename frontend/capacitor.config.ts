import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.akord.elevators',
  appName: 'אקורד מעליות',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    url: 'https://34-173-13-122.sslip.io',
    cleartext: false,
  },
}

export default config
