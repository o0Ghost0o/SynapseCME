export interface AuthUser {
  username: string
  full_name: string
  role: string
}

interface TokenPair {
  access_token: string
  refresh_token: string
}

const ACCESS_KEY = 'synapse.access'
const REFRESH_KEY = 'synapse.refresh'
const USER_KEY = 'synapse.user'

export type AuthErrorKind = 'invalid' | 'network' | 'unknown'

export class AuthError extends Error {
  kind: AuthErrorKind
  constructor(kind: AuthErrorKind, message?: string) {
    super(message || kind)
    this.kind = kind
  }
}

const accessToken = ref('')
const refreshToken = ref('')
const user = ref<AuthUser | null>(null)

let restored = false
let refreshPromise: Promise<boolean> | null = null

function storage() {
  return typeof window === 'undefined' ? null : window.localStorage
}

function persist() {
  const store = storage()
  if (!store) return
  if (accessToken.value) store.setItem(ACCESS_KEY, accessToken.value)
  else store.removeItem(ACCESS_KEY)
  if (refreshToken.value) store.setItem(REFRESH_KEY, refreshToken.value)
  else store.removeItem(REFRESH_KEY)
  if (user.value) store.setItem(USER_KEY, JSON.stringify(user.value))
  else store.removeItem(USER_KEY)
}

function restore() {
  if (restored) return
  restored = true
  const store = storage()
  if (!store) return
  accessToken.value = store.getItem(ACCESS_KEY) || ''
  refreshToken.value = store.getItem(REFRESH_KEY) || ''
  const rawUser = store.getItem(USER_KEY)
  if (rawUser) {
    try {
      user.value = JSON.parse(rawUser) as AuthUser
    } catch {
      store.removeItem(USER_KEY)
    }
  }
}

function applyTokens(pair: TokenPair) {
  accessToken.value = pair.access_token
  refreshToken.value = pair.refresh_token
  persist()
}

function clearSession() {
  accessToken.value = ''
  refreshToken.value = ''
  user.value = null
  persist()
}

function apiBase(): string {
  return ((useRuntimeConfig().public.apiBase as string | undefined) || '').replace(/\/$/, '')
}

async function login(username: string, password: string): Promise<AuthUser> {
  let res: Response
  try {
    res = await fetch(`${apiBase()}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
  } catch {
    throw new AuthError('network', 'Servidor no disponible')
  }
  if (res.status === 401 || res.status === 403) {
    throw new AuthError('invalid', 'Credenciales inválidas')
  }
  if (!res.ok) throw new AuthError('unknown', `HTTP ${res.status}`)
  const data = await res.json()
  applyTokens(data as TokenPair)
  user.value = (data as { user?: AuthUser }).user ?? { username, full_name: username, role: 'viewer' }
  persist()
  return user.value
}

// Renovación serializada: llamadas concurrentes comparten una única petición.
function tryRefresh(): Promise<boolean> {
  if (!refreshToken.value) return Promise.resolve(false)
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const res = await fetch(`${apiBase()}/api/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken.value }),
        })
        if (!res.ok) return false
        const data = (await res.json()) as TokenPair & { user?: AuthUser }
        applyTokens(data)
        if (data.user) {
          user.value = data.user
          persist()
        }
        return true
      } catch {
        return false
      }
    })().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

async function logout(): Promise<void> {
  const token = refreshToken.value
  clearSession()
  if (token) {
    try {
      await fetch(`${apiBase()}/api/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: token }),
      })
    } catch {
      // cierre de sesión best-effort
    }
  }
  await navigateTo('/login')
}

// Sesión inválida en el servidor: limpiar y volver a /login conservando la ruta.
async function forceLogout(): Promise<void> {
  clearSession()
  const current = useRoute().fullPath
  await navigateTo({ path: '/login', query: { redirect: current } })
}

const isAuthenticated = computed(() => !!(accessToken.value || refreshToken.value))
const canCapture = computed(() => ['admin', 'capturer'].includes(user.value?.role ?? ''))
const isAdmin = computed(() => user.value?.role === 'admin')

export function useAuth() {
  restore()
  return {
    accessToken,
    refreshToken,
    user,
    isAuthenticated,
    canCapture,
    isAdmin,
    login,
    logout,
    tryRefresh,
    forceLogout,
  }
}
