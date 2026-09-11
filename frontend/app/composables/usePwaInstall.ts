import { ref, computed, onMounted } from 'vue'

const deferredPrompt = ref<any>(null)
const isInstallable = ref(false)
const isStandalone = ref(false)
const showIosInstructions = ref(false)

let listenersRegistered = false

function initPwaListeners() {
  if (!import.meta.client || listenersRegistered) return
  listenersRegistered = true

  // Detect standalone mode (already installed / launched from home screen)
  const standaloneMedia = window.matchMedia('(display-mode: standalone)')
  isStandalone.value = standaloneMedia.matches || Boolean((window.navigator as any).standalone)

  standaloneMedia.addEventListener('change', (e) => {
    isStandalone.value = e.matches
  })

  // Capture beforeinstallprompt for Chromium, Edge, Samsung Internet, Android
  window.addEventListener('beforeinstallprompt', (e: Event) => {
    e.preventDefault()
    deferredPrompt.value = e
    isInstallable.value = true
  })

  window.addEventListener('appinstalled', () => {
    deferredPrompt.value = null
    isInstallable.value = false
    isStandalone.value = true
  })
}

export function usePwaInstall() {
  const nuxtApp = useNuxtApp()
  const pwa = (nuxtApp as any).$pwa

  if (import.meta.client) {
    initPwaListeners()
  }

  const isIos = computed(() => {
    if (!import.meta.client) return false
    const ua = window.navigator.userAgent.toLowerCase()
    return /iphone|ipad|ipod/.test(ua) && !(window as any).MSStream
  })

  const canInstall = computed(() => {
    if (isStandalone.value) return false
    if (isIos.value) return true
    return isInstallable.value || !!deferredPrompt.value || Boolean(pwa?.showInstallPrompt)
  })

  async function installApp(): Promise<boolean> {
    if (deferredPrompt.value) {
      deferredPrompt.value.prompt()
      const choice = await deferredPrompt.value.userChoice
      if (choice?.outcome === 'accepted') {
        deferredPrompt.value = null
        isInstallable.value = false
        return true
      }
      return false
    }

    if (pwa?.showInstallPrompt && typeof pwa.install === 'function') {
      const choice = await pwa.install()
      return choice?.outcome === 'accepted'
    }

    if (isIos.value) {
      showIosInstructions.value = true
      return false
    }

    return false
  }

  return {
    canInstall,
    isStandalone,
    isIos,
    showIosInstructions,
    installApp,
  }
}
