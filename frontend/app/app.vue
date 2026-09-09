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
      <nav class="glass mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
        <NuxtLink to="/dashboard" class="flex items-center gap-2.5">
          <img
            src="/logo.svg"
            alt="SynapseCME"
            class="h-8 w-auto sm:h-9"
            width="400"
            height="120"
          />
        </NuxtLink>

        <div class="ml-auto flex items-center gap-1 overflow-x-auto">
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
