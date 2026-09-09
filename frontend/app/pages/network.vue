<script setup lang="ts">
import type { GraphLink, GraphNode } from '~/components/ForceGraph.vue'
import { useEvents } from '~/composables/useEvents'

const { request } = useApi()
const { clients, txs, lastMutation, status: wsStatus, ensure } = useEvents()

const nodes = ref<GraphNode[]>([])
const links = ref<GraphLink[]>([])
const loading = ref(false)
const failed = ref(false)
const paused = ref(false)
const actionFilter = ref('')
const visibleTxs = ref<TxEntry[]>([])

const ACTION_OPTIONS = [
  { value: '', label: 'Todas' },
  { value: 'crear', label: 'crear' },
  { value: 'fusionar', label: 'fusionar' },
  { value: 'promover', label: 'promover' },
  { value: 'consulta', label: 'consulta' },
]

const TYPE_ICONS: Record<string, string> = {
  field_app: '📱',
  dashboard: '📊',
  executive: '🏢',
}

async function loadNetwork() {
  loading.value = true
  failed.value = false
  try {
    const data = (await request('/api/network')) as { nodes?: unknown; links?: unknown }
    const rawNodes = Array.isArray(data?.nodes) ? data.nodes : []
    nodes.value = rawNodes
      .filter((n) => n && typeof n === 'object')
      .map((n) => {
        const o = n as Record<string, unknown>
        return {
          id: String(o.id ?? ''),
          label: String(o.label ?? o.name ?? o.id ?? ''),
          type: typeof o.type === 'string' ? o.type : undefined,
          state: typeof o.state === 'string' ? o.state : undefined,
        }
      })
      .filter((n) => n.id)
    const ids = new Set(nodes.value.map((n) => n.id))
    const rawLinks = Array.isArray(data?.links) ? data.links : []
    links.value = rawLinks
      .filter((l) => l && typeof l === 'object')
      .map((l) => {
        const o = l as Record<string, unknown>
        return {
          source: String(o.source ?? ''),
          target: String(o.target ?? ''),
          type: typeof o.type === 'string' ? o.type : undefined,
        }
      })
      .filter((l) => ids.has(l.source) && ids.has(l.target))
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

// Pulso del nodo afectado por la última mutación
const pulseTarget = computed<string | null>(() => {
  if (!lastMutation.value) return null
  const hint = lastMutation.value.nodeHint?.toLowerCase()
  if (!hint) return null
  const hit = nodes.value.find(
    (n) => n.id.toLowerCase() === hint || (n.label && n.label.toLowerCase().includes(hint)),
  )
  return hit ? hit.id : null
})

// Cola de transacciones pausable y filtrable
watch(
  txs,
  (list) => {
    if (paused.value) return
    visibleTxs.value = list
  },
  { immediate: true },
)

watch(paused, (isPaused) => {
  if (!isPaused) visibleTxs.value = txs.value
})

const filteredTxs = computed(() => {
  if (!actionFilter.value) return visibleTxs.value.slice(0, 30)
  return visibleTxs.value.filter((t) => t.action.includes(actionFilter.value)).slice(0, 30)
})

const onlineClients = computed(() => clients.value.filter((c) => (c.status || 'online') === 'online'))

onMounted(() => {
  ensure({ client_type: 'dashboard', name: 'Panel web SynapseCME' })
  void loadNetwork()
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold text-white">Red en vivo</h1>
        <p class="mt-1 text-sm text-slate-400">
          Grafo de instalaciones en tiempo real, clientes conectados y registro de transacciones.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <span class="glass-chip" :class="wsStatus === 'online' ? '' : 'border-rose-300/30 bg-rose-400/15 text-rose-200'">
          <span
            class="h-2 w-2 rounded-full"
            :class="wsStatus === 'online' ? 'bg-emerald-400' : wsStatus === 'connecting' ? 'animate-pulse bg-amber-400' : 'bg-rose-500'"
          />
          {{ wsStatus === 'online' ? 'Canal WS activo' : wsStatus === 'connecting' ? 'Conectando…' : 'WS desconectado' }}
        </span>
        <button class="btn-ghost" @click="loadNetwork">Actualizar</button>
      </div>
    </div>

    <ApiUnavailable v-if="failed" @retry="loadNetwork" />

    <div v-else class="grid gap-4 xl:grid-cols-[1fr_300px]">
      <!-- Lienzo del grafo -->
      <div class="glass relative min-h-[62vh] overflow-hidden p-2">
        <div v-if="loading" class="absolute inset-0 z-10 flex items-center justify-center bg-slate-950/40 backdrop-blur-sm">
          <span class="animate-pulse text-sm text-slate-300">Cargando grafo…</span>
        </div>
        <div v-if="!loading && !nodes.length" class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center">
          <p class="text-4xl">🕸️</p>
          <p class="max-w-xs text-sm text-slate-400">
            El grafo está vacío. Captura registros desde la página de Captura para poblarlo.
          </p>
        </div>
        <ForceGraph :nodes="nodes" :links="links" :pulse-id="pulseTarget" class="min-h-[60vh]" />
        <div
          v-if="lastMutation"
          class="pointer-events-none absolute bottom-3 left-3 max-w-md rounded-xl border border-emerald-300/25 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-100 backdrop-blur-xl"
        >
          Última mutación: {{ lastMutation.summary }}
        </div>
      </div>

      <!-- Panel de clientes conectados -->
      <div class="glass flex max-h-[62vh] flex-col p-4">
        <h2 class="text-sm font-semibold text-white">Clientes conectados</h2>
        <span class="mt-0.5 text-xs text-slate-400">{{ onlineClients.length }} en línea</span>
        <ul class="mt-3 flex flex-col gap-2 overflow-y-auto">
          <li
            v-for="(client, i) in clients"
            :key="`${client.name}-${i}`"
            class="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-2"
          >
            <span class="text-lg">{{ TYPE_ICONS[client.client_type] || '💻' }}</span>
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm text-slate-100">{{ client.name || 'Cliente anónimo' }}</p>
              <p class="text-[11px] text-slate-500">{{ client.client_type }}</p>
            </div>
            <span class="flex items-center gap-1 text-[11px]" :class="(client.status || 'online') === 'online' ? 'text-emerald-300' : 'text-slate-500'">
              <span
                class="h-1.5 w-1.5 rounded-full"
                :class="(client.status || 'online') === 'online' ? 'bg-emerald-400' : 'bg-slate-500'"
              />
              {{ (client.status || 'online') === 'online' ? 'en línea' : 'inactivo' }}
            </span>
          </li>
          <li v-if="!clients.length" class="rounded-xl border border-dashed border-white/15 p-4 text-center text-xs text-slate-500">
            Aún no hay clientes en el canal WS.
          </li>
        </ul>
      </div>
    </div>

    <!-- Registro de transacciones -->
    <div class="glass p-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h2 class="text-sm font-semibold text-white">Registro de transacciones</h2>
        <div class="flex items-center gap-2">
          <label class="text-xs text-slate-400" for="tx-filter">Acción</label>
          <select id="tx-filter" v-model="actionFilter" class="glass-input w-auto px-2 py-1.5 text-xs">
            <option v-for="opt in ACTION_OPTIONS" :key="opt.value" :value="opt.value" class="bg-slate-900">
              {{ opt.label }}
            </option>
          </select>
          <button class="btn-ghost px-3 py-1.5 text-xs" @click="paused = !paused">
            {{ paused ? '▶ Reanudar' : '⏸ Pausar' }}
          </button>
        </div>
      </div>
      <div class="mt-3 max-h-56 overflow-y-auto rounded-xl border border-white/10">
        <table class="w-full border-collapse">
          <thead class="sticky top-0 bg-slate-900/70 backdrop-blur-xl">
            <tr>
              <th class="th-cell">Hora</th>
              <th class="th-cell">Actor</th>
              <th class="th-cell">Acción</th>
              <th class="th-cell">Objetivo</th>
              <th class="th-cell">Transición de estado</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(tx, i) in filteredTxs" :key="i" class="border-t border-white/5">
              <td class="td-cell whitespace-nowrap text-slate-400">{{ fmtTime(tx.at) }}</td>
              <td class="td-cell">{{ tx.actor }}</td>
              <td class="td-cell">
                <span class="glass-chip">{{ tx.action }}</span>
              </td>
              <td class="td-cell">{{ tx.target || '—' }}</td>
              <td class="td-cell text-slate-400">{{ tx.transition || '—' }}</td>
            </tr>
            <tr v-if="!filteredTxs.length">
              <td colspan="5" class="px-4 py-6 text-center text-xs text-slate-500">
                Sin transacciones registradas todavía.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
