<script setup lang="ts">
const { apiOnline, start } = useConnection()
const { status: wsStatus, ensure, reconnect } = useEvents()
const { toast } = useToast()
const { user, isAuthenticated, canCapture, isAdmin, accessToken, tryRefresh, forceLogout, logout } = useAuth()

const navLinks = computed(() => {
  const links: Array<{ to: string; label: string }> = []
  if (canCapture.value) links.push({ to: '/chat', label: 'Captura' })
  links.push(
    { to: '/dashboard', label: 'Panel 360' },
    { to: '/network', label: 'Red en vivo' },
    { to: '/metricas', label: 'Métricas' },
    { to: '/documentacion', label: 'Documentación' },
  )
  if (isAdmin.value) links.push({ to: '/admin/usuarios', label: 'Usuarios' })
  return links
})

const route = useRoute()
const menuOpen = ref(false)

// Instalación PWA: el módulo captura beforeinstallprompt y expone el prompt.
const { $pwa } = useNuxtApp()
const canInstall = computed(
  () => !!$pwa && !$pwa.isInstalled && $pwa.isInstallable === true,
)
async function installApp() {
  await $pwa?.showInstallPrompt()
}
watch(
  () => route.fullPath,
  () => {
    menuOpen.value = false
  },
)

const connectionDot = computed(() => ({
  online: apiOnline.value === true && wsStatus.value === 'online',
  cls:
    apiOnline.value === true && wsStatus.value === 'online'
      ? 'bg-[#17b26a]'
      : 'bg-[#d92d20]',
  chipCls:
    apiOnline.value === true && wsStatus.value === 'online'
      ? 'border-[#bfe8d2] bg-[#eefbf4] text-[#067647]'
      : 'border-[#f5cdcd] bg-[#fdf0f0] text-[#b42318]',
  label:
    apiOnline.value === true && wsStatus.value === 'online'
      ? 'Conectado al servidor local'
      : 'Servidor local no disponible',
}))

const userInitials = computed(() => {
  const name = user.value?.full_name || user.value?.username || ''
  const parts = name.trim().split(/\s+/)
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || 'S'
})

async function handleWsAuthError() {
  const refreshed = await tryRefresh()
  if (refreshed) reconnect()
  else await forceLogout()
}

onMounted(() => {
  start()
  ensure({
    client_type: 'dashboard',
    name: 'Panel web SynapseCME',
    getToken: () => accessToken.value || null,
    onAuthError: handleWsAuthError,
  })
})
</script>

<template>
  <div class="min-h-screen">
    <header v-if="route.path !== '/login'" class="sticky top-0 z-40 border-b border-[#e3e8f2] bg-white/95 backdrop-blur-md">
      <nav class="relative mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
        <NuxtLink to="/dashboard" class="flex items-center gap-2.5">
          <img
            src="/logo.svg"
            alt="SynapseCME"
            class="h-8 w-auto sm:h-9"
            width="400"
            height="120"
          />
        </NuxtLink>

        <!-- Navegación inline (desktop) -->
        <div class="ml-auto hidden items-center gap-1 lg:flex">
          <NuxtLink
            v-for="link in navLinks"
            :key="link.to"
            :to="link.to"
            class="nav-link"
            active-class="nav-link-active"
          >
            {{ link.label }}
          </NuxtLink>
        </div>

        <!-- Hamburger (móvil/tablet): único control visible en pantallas pequeñas -->
        <div class="relative ml-auto lg:hidden">
          <button
            class="btn-ghost px-3 py-1.5 text-sm"
            :aria-expanded="menuOpen"
            aria-label="Menú de navegación"
            data-testid="nav-menu-button"
            @click="menuOpen = !menuOpen"
          >
            <Icon :name="menuOpen ? 'close' : 'menu'" :size="15" /><span class="hidden sm:inline"> Menú</span>
          </button>
          <Transition name="toast">
            <div
              v-if="menuOpen"
              class="glass-strong absolute right-0 top-full z-50 mt-2 w-60 rounded-2xl p-2"
              data-testid="nav-menu"
            >
              <NuxtLink
                v-for="link in navLinks"
                :key="link.to"
                :to="link.to"
                class="nav-link block px-3 py-2.5"
                active-class="nav-link-active"
              >
                {{ link.label }}
              </NuxtLink>
              <div class="mt-1 border-t border-[#e3e8f2] px-3 pt-2.5">
                <p v-if="user" class="text-xs font-semibold leading-tight text-[#101828]">{{ user.full_name || user.username }}</p>
                <p v-if="user" class="mb-2 text-[10px] leading-tight text-[#7a8499]">{{ roleLabel(user.role) }}</p>
                <div class="flex items-center gap-2" :title="connectionDot.label">
                  <span class="h-2 w-2 rounded-full transition" :class="connectionDot.cls" />
                  <span class="text-xs text-[#5b6780]">{{ connectionDot.online ? 'En línea' : 'Sin conexión' }}</span>
                </div>
                <button
                  v-if="canInstall"
                  class="btn-ghost mt-2 block w-full px-3 py-2 text-left text-xs"
                  @click="installApp"
                >
                  <Icon name="download" :size="13" /> Instalar app
                </button>
                <button
                  class="btn-ghost mt-2 block w-full px-3 py-2 text-left text-xs"
                  title="Cerrar sesión"
                  data-testid="nav-logout"
                  @click="logout()"
                >
                  <Icon name="power" :size="13" /> Cerrar sesión
                </button>
              </div>
            </div>
          </Transition>
        </div>

        <div class="hidden items-center gap-2 pl-2 lg:flex" :title="connectionDot.label">
          <button
            v-if="canInstall"
            class="btn-ghost px-3 py-1.5 text-xs"
            title="Instalar SynapseCME como aplicación"
            @click="installApp"
          >
            <Icon name="download" :size="13" /> Instalar app
          </button>
          <span class="glass-chip" :class="connectionDot.chipCls">
            <span class="h-2 w-2 rounded-full transition" :class="connectionDot.cls" />
            {{ connectionDot.online ? 'En línea' : 'Sin conexión' }}
          </span>
        </div>

        <div v-if="isAuthenticated && user" class="hidden items-center gap-3 border-l border-[#e3e8f2] pl-3 lg:flex">
          <div class="text-right">
            <p class="text-xs font-semibold leading-tight text-[#101828]">{{ user.full_name || user.username }}</p>
            <p class="text-[10px] leading-tight text-[#7a8499]">{{ roleLabel(user.role) }}</p>
          </div>
          <span class="grid h-9 w-9 place-items-center rounded-full bg-[#e8eefc] font-display text-xs font-semibold text-[#1d63d8]">
            {{ userInitials }}
          </span>
          <button class="btn-ghost px-3 py-1.5 text-xs" title="Cerrar sesión" @click="logout()">
            <Icon name="power" :size="13" /> Cerrar sesión
          </button>
        </div>
      </nav>
    </header>

    <main class="w-full px-7 pb-6 pt-6">
      <NuxtPage />
    </main>

    <Transition name="toast">
      <div
        v-if="toast.visible"
        class="glass-strong toast-in fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3.5 text-sm font-medium text-[#101828]"
        role="status"
      >
        <span class="grid h-6 w-6 place-items-center rounded-full bg-[#eefbf4] text-[#067647]">
          <Icon name="check" :size="14" />
        </span>
        {{ toast.text }}
      </div>
    </Transition>
  </div>
</template>
