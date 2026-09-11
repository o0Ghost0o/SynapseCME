<script setup lang="ts">
import { AuthError } from '~/composables/useAuth'

const { login, isAuthenticated } = useAuth()
const { apiOnline } = useConnection()
const route = useRoute()

if (isAuthenticated.value) {
  await navigateTo('/dashboard')
}

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await login(username.value.trim(), password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    await navigateTo(redirect)
  } catch (e) {
    if (e instanceof AuthError) {
      error.value =
        e.kind === 'invalid'
          ? 'Credenciales inválidas'
          : e.kind === 'network'
            ? 'Servidor no disponible'
            : 'Error inesperado. Inténtalo de nuevo.'
    } else {
      error.value = 'Error inesperado. Inténtalo de nuevo.'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="-mx-7 -my-6 grid min-h-[100dvh] overflow-hidden bg-white lg:grid-cols-[1.1fr_1fr]">
    <!-- Panel de marca -->
    <div class="relative hidden flex-col overflow-hidden bg-[#0e1630] p-11 text-[#eef2f9] lg:flex">
      <div class="pointer-events-none absolute inset-0" aria-hidden="true">
        <div class="absolute inset-0 bg-[radial-gradient(700px_500px_at_30%_70%,rgba(37,99,235,0.28),transparent)]" />
        <svg class="absolute inset-0 h-full w-full opacity-40" viewBox="0 0 100 100" preserveAspectRatio="none">
          <g stroke="rgba(148,178,255,0.25)" stroke-width="0.25">
            <line x1="12" y1="18" x2="38" y2="30" />
            <line x1="38" y1="30" x2="30" y2="58" />
            <line x1="30" y1="58" x2="62" y2="66" />
            <line x1="62" y1="66" x2="78" y2="38" />
            <line x1="38" y1="30" x2="78" y2="38" />
            <line x1="12" y1="18" x2="30" y2="58" />
            <line x1="62" y1="66" x2="86" y2="80" />
            <line x1="78" y1="38" x2="86" y2="80" />
          </g>
          <g fill="#67d4ff">
            <circle cx="12" cy="18" r="1.4" />
            <circle cx="38" cy="30" r="1.8" />
            <circle cx="30" cy="58" r="1.4" />
            <circle cx="62" cy="66" r="1.8" />
            <circle cx="78" cy="38" r="1.4" />
            <circle cx="86" cy="80" r="1.2" />
          </g>
        </svg>
      </div>

      <div class="relative flex items-center gap-2">
        <span class="h-6 w-6 rounded-md bg-gradient-to-br from-sky-500 to-blue-600" />
        <span class="font-display text-lg font-bold">Synapse<span class="text-sky-400">CME</span></span>
      </div>

      <div class="relative mt-auto max-w-md">
        <h1 class="font-display text-[33px] font-bold leading-[1.2] tracking-tight">
          Inteligencia de base instalada hospitalaria
        </h1>
        <p class="mt-3.5 text-[14.5px] leading-relaxed text-[#b9c5e0]">
          Observaciones de campo en español libre → grafo GraphRAG vivo, con inferencia 100 % local.
        </p>
        <ul class="mt-6 flex flex-col gap-3 text-[13px] text-[#cbd5ea]">
          <li class="flex items-center gap-2.5">
            <span class="h-1.5 w-1.5 rounded-full bg-emerald-400" />Cero APIs de nube — todo on-edge sobre NVIDIA RTX
          </li>
          <li class="flex items-center gap-2.5">
            <span class="h-1.5 w-1.5 rounded-full bg-sky-400" />Consenso ponderado: Estimado → Reportado → Confirmado
          </li>
          <li class="flex items-center gap-2.5">
            <span class="h-1.5 w-1.5 rounded-full bg-violet-400" />Panel 360, Red en vivo y Métricas por WebSocket
          </li>
        </ul>
      </div>
    </div>

    <!-- Formulario -->
    <div class="flex flex-col bg-white p-7 text-[#1a2233] sm:p-12">
      <div class="flex items-center justify-between lg:justify-end">
        <div class="flex items-center gap-2 lg:hidden">
          <span class="h-6 w-6 rounded-md bg-gradient-to-br from-sky-500 to-blue-600" />
          <span class="font-display text-lg font-bold text-[#101828]">Synapse<span class="text-[#0284c7]">CME</span></span>
        </div>
        <span
          v-if="apiOnline === false"
          class="inline-flex items-center gap-1.5 rounded-full border border-[#f5cdcd] bg-[#fdf0f0] px-2.5 py-1 text-[11.5px] font-medium text-[#b42318]"
        >
          <span class="h-1.5 w-1.5 rounded-full bg-[#d92d20]" />Sin conexión
        </span>
      </div>

      <div class="mx-auto my-auto w-full max-w-sm">
        <img src="/logo.svg" alt="SynapseCME" class="mb-6 h-11 w-auto lg:hidden" width="400" height="120" />
        <h2 class="font-display text-2xl font-bold text-[#101828]">Iniciar sesión</h2>
        <p class="mt-1.5 text-[13.5px] text-[#5b6780]">Accede con tu cuenta del nodo local.</p>

        <form class="mt-6 flex flex-col gap-4" @submit.prevent="submit">
          <div>
            <label for="username" class="mb-1.5 block font-display text-[11px] font-semibold uppercase tracking-[0.1em] text-[#5b6780]">
              Usuario
            </label>
            <input
              id="username"
              v-model="username"
              class="glass-input"
              type="text"
              autocomplete="username"
              placeholder="Nombre de usuario"
              required
              :disabled="loading"
            />
          </div>
          <div>
            <label for="password" class="mb-1.5 block font-display text-[11px] font-semibold uppercase tracking-[0.1em] text-[#5b6780]">
              Contraseña
            </label>
            <input
              id="password"
              v-model="password"
              class="glass-input"
              type="password"
              autocomplete="current-password"
              placeholder="••••••••"
              required
              :disabled="loading"
            />
          </div>

          <p
            v-if="error"
            class="flex items-center gap-2 rounded-xl border border-[#f0d3d3] bg-[#fdf5f5] px-3 py-2 text-center text-sm text-[#8a2018]"
            role="alert"
          >
            <Icon name="alert" :size="15" class="shrink-0" />{{ error }}
          </p>

          <button class="btn-primary w-full" type="submit" :disabled="loading || !username.trim() || !password">
            {{ loading ? 'Iniciando sesión…' : 'Iniciar sesión' }}
          </button>
          <p class="text-center text-[11.5px] text-[#7a8499]">El acceso requiere que el nodo local esté en línea</p>
        </form>
      </div>
    </div>
  </div>
</template>
