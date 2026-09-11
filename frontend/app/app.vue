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
    { to: '/deck', label: 'Deck' },
  )
  if (isAdmin.value) links.push({ to: '/admin/usuarios', label: 'Usuarios' })
  return links
})

const route = useRoute()
const menuOpen = ref(false)

// Instalación PWA: detecta instalación nativa y maneja el prompt en todos los navegadores
const { canInstall, installApp, showIosInstructions } = usePwaInstall()
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
  const path = route.path.toLowerCase().replace(/\/+$/, '') || '/'
  if (
    route.meta.auth === false ||
    path === '/deck' ||
    path.startsWith('/deck/') ||
    path === '/offline' ||
    path.startsWith('/offline/')
  ) {
    return
  }
  const refreshed = await tryRefresh()
  if (refreshed) reconnect()
  else await forceLogout()
}

onMounted(() => {
  start()
  const path = route.path.toLowerCase().replace(/\/+$/, '') || '/'
  // Conectar WebSocket únicamente si el usuario está autenticado y no está en /deck
  if (isAuthenticated.value && !path.startsWith('/deck')) {
    ensure({
      client_type: 'dashboard',
      name: 'Panel web SynapseCME',
      getToken: () => accessToken.value || null,
      onAuthError: handleWsAuthError,
    })
  }
})

// Reconectar si el usuario se autentica o navega a una ruta protegida
watch([isAuthenticated, () => route.path], ([authed, path]) => {
  const norm = String(path).toLowerCase().replace(/\/+$/, '') || '/'
  if (authed && !norm.startsWith('/deck') && !norm.startsWith('/login')) {
    ensure({
      client_type: 'dashboard',
      name: 'Panel web SynapseCME',
      getToken: () => accessToken.value || null,
      onAuthError: handleWsAuthError,
    })
  }
})
</script>

<template>
  <VitePwaManifest />
  <div class="min-h-screen">
    <header v-if="route.path !== '/login' && !route.path.toLowerCase().startsWith('/deck')" class="sticky top-0 z-40 border-b border-[#e3e8f2] bg-white/95 backdrop-blur-md">
      <nav class="relative mx-auto flex w-full max-w-[1800px] items-center gap-3 px-4 sm:px-6 lg:px-8 py-3">
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
          <span class="glass-chip" :class="connectionDot.chipCls">
            <span class="h-2 w-2 rounded-full transition" :class="connectionDot.cls" />
            {{ connectionDot.online ? 'En línea' : 'Sin conexión' }}
          </span>
        </div>

        <div v-if="isAuthenticated && user" class="hidden items-center gap-2.5 border-l border-[#e3e8f2] pl-3 lg:flex">
          <div class="text-right">
            <p class="text-xs font-semibold leading-tight text-[#101828]">{{ user.full_name || user.username }}</p>
            <p class="text-[10px] leading-tight text-[#7a8499]">{{ roleLabel(user.role) }}</p>
          </div>
          <span class="grid h-9 w-9 place-items-center rounded-full bg-[#e8eefc] font-display text-xs font-semibold text-[#1d63d8]">
            {{ userInitials }}
          </span>
          <button
            v-if="canInstall"
            class="btn-ghost px-3 py-1.5 text-xs"
            title="Instalar SynapseCME como aplicación"
            @click="installApp"
          >
            <Icon name="download" :size="13" /> Instalar app
          </button>
          <button class="btn-ghost px-3 py-1.5 text-xs" title="Cerrar sesión" @click="logout()">
            <Icon name="power" :size="13" /> Cerrar sesión
          </button>
        </div>

        <div v-else-if="canInstall" class="hidden items-center border-l border-[#e3e8f2] pl-3 lg:flex">
          <button
            class="btn-ghost px-3 py-1.5 text-xs"
            title="Instalar SynapseCME como aplicación"
            @click="installApp"
          >
            <Icon name="download" :size="13" /> Instalar app
          </button>
        </div>
      </nav>
    </header>

    <main :class="route.path.toLowerCase().startsWith('/deck') ? 'p-0 m-0' : 'mx-auto w-full max-w-[1800px] px-4 sm:px-6 lg:px-8 pb-6 pt-6'">
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

    <!-- Modal de ayuda para instalación en iOS / Safari -->
    <Transition name="fade">
      <div
        v-if="showIosInstructions"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4"
        @click.self="showIosInstructions = false"
      >
        <div class="glass-strong relative max-w-sm w-full rounded-2xl p-6 shadow-2xl text-center bg-white">
          <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[#e8eefc] text-[#1d63d8]">
            <Icon name="download" :size="22" />
          </div>
          <h3 class="text-base font-semibold text-[#101828]">Instalar en iPhone / iPad</h3>
          <p class="mt-2 text-xs leading-relaxed text-[#5b6780]">
            Para instalar SynapseCME en tu pantalla de inicio desde Safari:
          </p>
          <ol class="mt-4 text-left text-xs leading-relaxed text-[#344054] space-y-2.5 list-decimal list-inside rounded-xl bg-[#f8fafc] p-3.5 border border-[#e3e8f2]">
            <li>Toca el botón <strong>Compartir</strong> en la barra inferior (icono de un recuadro con flecha hacia arriba).</li>
            <li>Desliza hacia abajo y pulsa <strong>«Agregar al inicio»</strong>.</li>
            <li>Confirma tocando <strong>«Agregar»</strong> en la esquina superior derecha.</li>
          </ol>
          <button
            class="btn-primary mt-5 w-full py-2.5 text-xs font-semibold"
            @click="showIosInstructions = false"
          >
            Entendido
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>
