<script setup lang="ts">
import { AuthError } from '~/composables/useAuth'

const { login, isAuthenticated } = useAuth()
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
  <div class="flex min-h-[70vh] items-center justify-center">
    <div class="glass-strong w-full max-w-sm p-8">
      <div class="flex flex-col items-center">
        <img src="/logo.svg" alt="SynapseCME" class="h-12 w-auto" width="400" height="120" />
        <p class="mt-3 text-center text-xs text-slate-400">
          Inteligencia de base instalada hospitalaria
        </p>
      </div>

      <form class="mt-6 flex flex-col gap-4" @submit.prevent="submit">
        <div>
          <label for="username" class="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-400">
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
          <label for="password" class="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-400">
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
          class="rounded-xl border border-rose-300/30 bg-rose-400/15 px-3 py-2 text-center text-sm text-rose-200"
          role="alert"
        >
          {{ error }}
        </p>

        <button class="btn-primary w-full" type="submit" :disabled="loading || !username.trim() || !password">
          {{ loading ? 'Iniciando sesión…' : 'Iniciar sesión' }}
        </button>
      </form>
    </div>
  </div>
</template>
