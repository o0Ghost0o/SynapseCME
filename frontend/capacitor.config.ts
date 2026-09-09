import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.synapsecme.app',
  appName: 'SynapseCME',
  webDir: '.output/public',
  android: {
    // Permite llamadas en claro a la API local (http://localhost:8000) en desarrollo.
    allowMixedContent: true,
  },
}

export default config
