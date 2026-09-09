export function useApi() {
  const config = useRuntimeConfig()
  // apiBase vacío = rutas relativas al mismo origen (pasarela Caddy).
  const apiBase = ((config.public.apiBase as string | undefined) || '').replace(/\/$/, '')
  const { accessToken, tryRefresh, forceLogout } = useAuth()

  async function fetchWithAuth(path: string, init?: RequestInit): Promise<Response> {
    const headers = new Headers(init?.headers)
    if (accessToken.value) headers.set('Authorization', `Bearer ${accessToken.value}`)

    let res = await fetch(`${apiBase}${path}`, { ...init, headers })

    if (res.status === 401 && accessToken.value) {
      const refreshed = await tryRefresh()
      if (refreshed) {
        headers.set('Authorization', `Bearer ${accessToken.value}`)
        res = await fetch(`${apiBase}${path}`, { ...init, headers })
      } else {
        await forceLogout()
        throw new Error('Sesión expirada')
      }
    }
    return res
  }

  async function request<T = unknown>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetchWithAuth(path, init)
    if (!res.ok) throw new Error(`HTTP ${res.status} en ${path}`)
    return (await res.json()) as T
  }

  return { apiBase, request, fetchWithAuth }
}
