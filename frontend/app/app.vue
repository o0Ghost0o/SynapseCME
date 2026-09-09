<script setup lang="ts">
const { apiOnline, start } = useConnection()
const { status: wsStatus, ensure } = useEvents()
const { toast } = useToast()

const navLinks = [
  { to: '/chat', label: 'Captura' },
  { to: '/dashboard', label: 'Panel 360' },
  { to: '/network', label: 'Red en vivo' },
  { to: '/metricas', label: 'Métricas' },
]

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

onMounted(() => {
  start()
  ensure({ client_type: 'dashboard', name: 'Panel web SynapseCME' })
})
</script>

<template>
  <div class="min-h-screen">
    <header class="sticky top-0 z-40 px-4 pt-4">
      <nav class="glass mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
        <NuxtLink to="/chat" class="flex items-center gap-2.5">
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
