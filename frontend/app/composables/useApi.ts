export function useApi() {
  const config = useRuntimeConfig()
  // apiBase vacío = rutas relativas al mismo origen (pasarela Caddy).
  const apiBase = ((config.public.apiBase as string | undefined) || '').replace(/\/$/, '')

  async function request<T = unknown>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${apiBase}${path}`, init)
    if (!res.ok) throw new Error(`HTTP ${res.status} en ${path}`)
    return (await res.json()) as T
  }

  return { apiBase, request }
}
