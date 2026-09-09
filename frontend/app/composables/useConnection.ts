const apiOnline = ref<boolean | null>(null)
const healthModels = ref<string[]>([])
const healthCheckedAt = ref<Date | null>(null)

let started = false
let timer: ReturnType<typeof setInterval> | undefined

async function checkHealth(apiBase: string) {
  try {
    const res = await fetch(`${apiBase}/api/health`, { signal: AbortSignal.timeout(4000) })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    apiOnline.value = true
    healthModels.value = Array.isArray(data?.models) ? data.models : []
  } catch {
    apiOnline.value = false
    healthModels.value = []
  } finally {
    healthCheckedAt.value = new Date()
  }
}

export function useConnection() {
  const { apiBase } = useApi()

  function start() {
    if (started) return
    started = true
    void checkHealth(apiBase)
    timer = setInterval(() => void checkHealth(apiBase), 10000)
  }

  function refresh() {
    return checkHealth(apiBase)
  }

  return { apiOnline, healthModels, healthCheckedAt, start, refresh }
}
