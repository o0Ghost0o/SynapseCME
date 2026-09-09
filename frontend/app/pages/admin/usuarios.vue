<script setup lang="ts">
import { useToast } from '~/composables/useToast'

interface AdminUser {
  username: string
  full_name: string
  role: string
}

const { request } = useApi()
const { show } = useToast()

const users = ref<AdminUser[]>([])
const loading = ref(false)
const failed = ref(false)
const creating = ref(false)
const error = ref('')

const form = reactive({ username: '', full_name: '', password: '', role: 'viewer' })

const ROLE_OPTIONS = [
  { value: 'viewer', label: 'Visor' },
  { value: 'capturer', label: 'Captor' },
  { value: 'admin', label: 'Administrador' },
]

function normalizeUsers(data: unknown): AdminUser[] {
  const arr = Array.isArray(data)
    ? data
    : Array.isArray((data as Record<string, unknown>)?.users)
      ? ((data as Record<string, unknown>).users as unknown[])
      : []
  return arr
    .filter((u) => u && typeof u === 'object')
    .map((u) => {
      const o = u as Record<string, unknown>
      return {
        username: String(o.username ?? ''),
        full_name: String(o.full_name ?? o.fullName ?? o.name ?? ''),
        role: String(o.role ?? 'viewer'),
      }
    })
    .filter((u) => u.username)
}

async function loadUsers() {
  loading.value = true
  failed.value = false
  try {
    users.value = normalizeUsers(await request('/api/auth/users'))
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

async function createUser() {
  error.value = ''
  creating.value = true
  try {
    await request('/api/auth/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: form.username.trim(),
        full_name: form.full_name.trim(),
        password: form.password,
        role: form.role,
      }),
    })
    show('Usuario creado')
    form.username = ''
    form.full_name = ''
    form.password = ''
    form.role = 'viewer'
    await loadUsers()
  } catch (e) {
    error.value = e instanceof Error && e.message.startsWith('HTTP 409')
      ? 'Ese nombre de usuario ya existe'
      : 'No se pudo crear el usuario'
  } finally {
    creating.value = false
  }
}

onMounted(loadUsers)
</script>

<template>
  <div class="flex flex-col gap-4">
    <div>
      <h1 class="text-2xl font-bold text-white">Usuarios</h1>
      <p class="mt-1 text-sm text-slate-400">
        Alta y revisión de usuarios de SynapseCME. Solo administradores.
      </p>
    </div>

    <div class="grid gap-4 lg:grid-cols-[1fr_340px]">
      <!-- Lista de usuarios -->
      <div class="glass p-4">
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-semibold text-white">Usuarios registrados</h2>
          <button class="btn-ghost px-3 py-1.5 text-xs" :disabled="loading" @click="loadUsers">
            {{ loading ? 'Actualizando…' : 'Actualizar' }}
          </button>
        </div>
        <ApiUnavailable v-if="failed" @retry="loadUsers" />
        <ul v-else class="mt-3 flex flex-col gap-2">
          <li
            v-for="u in users"
            :key="u.username"
            class="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/5 px-4 py-2.5"
          >
            <div class="min-w-0">
              <p class="truncate text-sm text-white">{{ u.full_name || u.username }}</p>
              <p class="text-[11px] text-slate-500">@{{ u.username }}</p>
            </div>
            <span class="glass-chip" :class="u.role === 'admin' ? 'border-fuchsia-300/30 bg-fuchsia-400/15 text-fuchsia-200' : ''">
              {{ roleLabel(u.role) }}
            </span>
          </li>
          <li v-if="!loading && !users.length" class="rounded-xl border border-dashed border-white/15 p-6 text-center text-xs text-slate-500">
            Sin usuarios registrados todavía.
          </li>
        </ul>
      </div>

      <!-- Alta de usuario -->
      <form class="glass h-fit p-4" @submit.prevent="createUser">
        <h2 class="text-sm font-semibold text-white">Crear usuario</h2>
        <div class="mt-3 flex flex-col gap-3">
          <div>
            <label for="new-username" class="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-400">Usuario</label>
            <input id="new-username" v-model="form.username" class="glass-input py-2 text-sm" type="text" required :disabled="creating" />
          </div>
          <div>
            <label for="new-fullname" class="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-400">Nombre completo</label>
            <input id="new-fullname" v-model="form.full_name" class="glass-input py-2 text-sm" type="text" required :disabled="creating" />
          </div>
          <div>
            <label for="new-password" class="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-400">Contraseña</label>
            <input id="new-password" v-model="form.password" class="glass-input py-2 text-sm" type="password" autocomplete="new-password" required :disabled="creating" />
          </div>
          <div>
            <label for="new-role" class="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-400">Rol</label>
            <select id="new-role" v-model="form.role" class="glass-input py-2 text-sm" :disabled="creating">
              <option v-for="opt in ROLE_OPTIONS" :key="opt.value" :value="opt.value" class="bg-slate-900">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <p v-if="error" class="rounded-xl border border-rose-300/30 bg-rose-400/15 px-3 py-2 text-center text-xs text-rose-200" role="alert">
            {{ error }}
          </p>
          <button class="btn-primary" type="submit" :disabled="creating || !form.username.trim() || !form.password">
            {{ creating ? 'Creando…' : 'Crear usuario' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
