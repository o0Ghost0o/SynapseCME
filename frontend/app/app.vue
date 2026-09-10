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
  )
  if (isAdmin.value) links.push({ to: '/admin/usuarios', label: 'Usuarios' })
  return links
})

const route = useRoute()
const menuOpen = ref(false)
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
      ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]'
      : 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.8)]',
  label:
    apiOnline.value === true && wsStatus.value === 'online'
      ? 'Conectado al servidor local'
      : 'Servidor local no disponible',
}))

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
    <header class="sticky top-0 z-40 px-4 pt-4">
      <nav class="glass relative mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
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

        <!-- Hamburger (móvil/tablet) -->
        <div class="relative ml-auto lg:hidden">
          <button
            class="btn-ghost px-3 py-1.5 text-sm"
            :aria-expanded="menuOpen"
            aria-label="Menú de navegación"
            data-testid="nav-menu-button"
            @click="menuOpen = !menuOpen"
          >
            {{ menuOpen ? '✕' : '☰' }} Menú
          </button>
          <Transition name="toast">
            <div
              v-if="menuOpen"
              class="glass-strong absolute right-0 top-full z-50 mt-2 w-56 rounded-2xl p-2"
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
              <div class="mt-1 flex items-center gap-2 border-t border-white/10 px-3 pt-2.5">
                <span class="h-2 w-2 rounded-full transition" :class="connectionDot.cls" />
                <span class="text-xs text-slate-300">{{ connectionDot.online ? 'En línea' : 'Sin conexión' }}</span>
              </div>
            </div>
          </Transition>
        </div>

        <div class="hidden items-center gap-2 pl-2 sm:flex" :title="connectionDot.label">
          <span class="glass-chip">
            <span class="h-2 w-2 rounded-full transition" :class="connectionDot.cls" />
            {{ connectionDot.online ? 'En línea' : 'Sin conexión' }}
          </span>
        </div>

        <div v-if="isAuthenticated && user" class="flex items-center gap-2 border-l border-white/10 pl-3">
          <div class="hidden text-right md:block">
            <p class="text-xs font-semibold leading-tight text-white">{{ user.full_name || user.username }}</p>
            <p class="text-[10px] leading-tight text-slate-400">{{ roleLabel(user.role) }}</p>
          </div>
          <span class="glass-chip border-indigo-300/30 bg-indigo-400/15 text-indigo-200 md:hidden">
            {{ user.full_name || user.username }}
          </span>
          <button class="btn-ghost px-3 py-1.5 text-xs" title="Cerrar sesión" @click="logout()">
            ⏻ Cerrar sesión
          </button>
        </div>
      </nav>
    </header>

    <main class="mx-auto w-full max-w-7xl px-4 pb-16 pt-6">
      <NuxtPage />
    </main>

    <Transition name="toast">
      <div
        v-if="toast.visible"
        class="glass-strong toast-in fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3.5 text-sm font-medium text-white"
        role="status"
      >
        <span class="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-400/20 text-emerald-300">✓</span>
        {{ toast.text }}
      </div>
    </Transition>
  </div>
</template>
