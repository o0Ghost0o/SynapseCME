export interface PresenceClient {
  client_type: string
  name: string
  connected_at?: string
  last_seen?: string
  status?: string
}

export interface TxEntry {
  at: string
  actor: string
  action: string
  target: string
  transition: string
  raw: Record<string, unknown>
}

export interface MutationEvent {
  summary: string
  nodeHint: string | null
  at: number
}

export type EventsStatus = 'offline' | 'connecting' | 'online'

const status = ref<EventsStatus>('offline')
const clients = ref<PresenceClient[]>([])
const txs = ref<TxEntry[]>([])
const lastMutation = ref<MutationEvent | null>(null)

let ws: WebSocket | null = null
let hello: { client_type: string; name: string } | null = null
let attempts = 0
let reconnectTimer: ReturnType<typeof setTimeout> | undefined
let pingTimer: ReturnType<typeof setInterval> | undefined

function normalizeTx(raw: Record<string, unknown>): TxEntry {
  const str = (v: unknown): string => (typeof v === 'string' && v ? v : '')
  return {
    at: str(raw.created_at) || str(raw.at) || str(raw.time) || new Date().toISOString(),
    actor: str(raw.actor) || str(raw.client) || str(raw.client_type) || str(raw.name) || 'sistema',
    action: (str(raw.action) || str(raw.accion) || 'consulta').toLowerCase(),
    target:
      str(raw.target) ||
      str(raw.objetivo) ||
      str(raw.objective) ||
      str(raw.facility) ||
      str(raw.installation) ||
      '',
    transition: str(raw.transition) || str(raw.transicion) || str(raw.state_change) || '',
    raw,
  }
}

function handleMessage(event: MessageEvent) {
  let msg: Record<string, unknown>
  try {
    msg = JSON.parse(String(event.data))
  } catch {
    return
  }
  switch (msg.type) {
    case 'presence': {
      const list = Array.isArray(msg.clients) ? msg.clients : []
      clients.value = list.filter((c) => c && typeof c === 'object') as PresenceClient[]
      break
    }
    case 'tx': {
      const entry = (msg.entry ?? msg.tx ?? {}) as Record<string, unknown>
      txs.value = [normalizeTx(entry), ...txs.value].slice(0, 200)
      break
    }
    case 'mutation': {
      const summary = typeof msg.summary === 'string' ? msg.summary : ''
      lastMutation.value = { summary, nodeHint: extractNodeHint(summary), at: Date.now() }
      break
    }
  }
}

function extractNodeHint(summary: string): string | null {
  // El resumen suele mencionar el id o etiqueta del nodo afectado.
  const match = summary.match(/[\w][\w .-]{2,60}/)
  return match ? match[0] : null
}

function scheduleReconnect(connectFn: () => void) {
  attempts += 1
  const delay = Math.min(1000 * 2 ** Math.min(attempts - 1, 4), 15000)
  clearTimeout(reconnectTimer)
  reconnectTimer = setTimeout(connectFn, delay)
}

export function useEvents() {
  const config = useRuntimeConfig()
  // wsBase vacío = derivar del origen actual (pasarela Caddy expone /ws/*).
  const wsBase = ((config.public.wsBase as string | undefined) || '').replace(/\/$/, '')

  function wsUrl(): string {
    if (wsBase) return `${wsBase}/ws/events`
    if (typeof window === 'undefined') return 'ws://localhost:3000/ws/events'
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}/ws/events`
  }

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    status.value = 'connecting'
    try {
      ws = new WebSocket(wsUrl())
    } catch {
      status.value = 'offline'
      scheduleReconnect(connect)
      return
    }
    ws.onopen = () => {
      attempts = 0
      status.value = 'online'
      if (hello) ws?.send(JSON.stringify({ type: 'hello', ...hello }))
      clearInterval(pingTimer)
      pingTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
      }, 20000)
    }
    ws.onmessage = handleMessage
    ws.onclose = () => {
      status.value = 'offline'
      clearInterval(pingTimer)
      scheduleReconnect(connect)
    }
    ws.onerror = () => {
      ws?.close()
    }
  }

  function ensure(opts?: { client_type?: string; name?: string }) {
    if (opts) {
      hello = {
        client_type: opts.client_type || 'dashboard',
        name: opts.name || 'Panel web SynapseCME',
      }
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'hello', ...hello }))
    }
    connect()
  }

  function disconnect() {
    clearTimeout(reconnectTimer)
    clearInterval(pingTimer)
    ws?.close()
    ws = null
    status.value = 'offline'
  }

  return { status, clients, txs, lastMutation, ensure, connect, disconnect }
}
