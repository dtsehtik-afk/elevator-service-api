import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.akord.elevators',
  appName: 'אקורד מעליות',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    url: 'https://lift-agent.com',
    cleartext: false,
  },
}

export default config
