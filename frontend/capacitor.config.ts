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
  plugins: {
    BackgroundRunner: {
      label: 'com.akord.elevators.location',
      src: 'background-runner.js',
      event: 'backgroundFetch',
      repeat: true,
      interval: 30,
      autoStart: true,
    },
  },
}

export default config
