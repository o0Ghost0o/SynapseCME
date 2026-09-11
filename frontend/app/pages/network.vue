<script setup lang="ts">
import type { GraphLink, GraphNode } from '~/components/ForceGraph.vue'
import { useEvents } from '~/composables/useEvents'
import { GRAPH_TYPE_COLORS, GRAPH_TYPE_LABELS } from '~/utils/graph'
import { STATE_RING_COLORS } from '~/utils/states'
import type { StateTone } from '~/utils/states'

const { request } = useApi()
const { clients, txs, lastMutation, status: wsStatus, ensure } = useEvents()

const nodes = ref<GraphNode[]>([])
const links = ref<GraphLink[]>([])
const loading = ref(false)
const failed = ref(false)
const paused = ref(false)
const actionFilter = ref('')
const visibleTxs = ref<TxEntry[]>([])

interface CoreInfo {
  name: string
  qvac_up: boolean
  qvac_url: string
  models: { id: string; state?: string | null }[]
  chat_model: string
  embed_model: string
  stt_model: string
  stt_up: boolean
  graph_counts: Record<string, number>
}

const core = ref<CoreInfo | null>(null)
const coreFailed = ref(false)

const ACTION_OPTIONS = [
  { value: '', label: 'Todas' },
  { value: 'crear', label: 'crear' },
  { value: 'fusionar', label: 'fusionar' },
  { value: 'promover', label: 'promover' },
  { value: 'consulta', label: 'consulta' },
]

const TYPE_ICONS: Record<string, string> = {
  field_app: 'phone',
  dashboard: 'grid',
  executive: 'briefcase',
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

async function loadCore() {
  try {
    const next = (await request('/api/network/core')) as CoreInfo
    if (JSON.stringify(next) !== JSON.stringify(core.value)) core.value = next
    coreFailed.value = false
  } catch {
    coreFailed.value = true
  }
}

let coreTimer: ReturnType<typeof setInterval> | undefined

// Nodos del grafo con el nodo principal inyectado al centro
const graphNodes = computed<GraphNode[]>(() => {
  if (!core.value) return nodes.value
  return [
    ...nodes.value,
    { id: '__core__', label: core.value.name, type: 'core', state: 'online' },
  ]
})

const graphLinks = computed<GraphLink[]>(() => {
  if (!core.value) return links.value
  const facilityIds = nodes.value.filter((n) => (n.type || '').toLowerCase() === 'facility').map((n) => n.id)
  return [
    ...links.value,
    ...facilityIds.map((id) => ({ source: '__core__', target: id, type: 'core' })),
  ]
})

const coreEquipmentTotal = computed(() => core.value?.graph_counts?.Equipment ?? 0)
const coreFacilityTotal = computed(() => core.value?.graph_counts?.Facility ?? 0)
const coreObservationTotal = computed(() => core.value?.graph_counts?.Observation ?? 0)

// ---------------------------------------------------------------------------
// Leyenda: niveles (colores por tipo de nodo) y estados (anillo)
// ---------------------------------------------------------------------------

const graphEl = ref<{ resetView: () => void } | null>(null)

/** Niveles presentes en el grafo, con su color (los alias comparten etiqueta). */
const typeLegend = computed(() => {
  const seen = new Map<string, string>()
  for (const n of graphNodes.value) {
    const key = (n.type || '').toLowerCase()
    const label = GRAPH_TYPE_LABELS[key]
    if (label && !seen.has(label)) seen.set(label, GRAPH_TYPE_COLORS[key] || '#94a3b8')
  }
  return [...seen.entries()].map(([label, color]) => ({ label, color }))
})

const stateLegend = computed(() => {
  const states = new Set(graphNodes.value.map((n) => stateTone(n.state)))
  const meta: Array<{ tone: StateTone; label: string }> = [
    { tone: 'emerald', label: 'confirmado / en línea' },
    { tone: 'sky', label: 'reportado' },
    { tone: 'amber', label: 'estimado' },
    { tone: 'rose', label: 'desconocido' },
  ]
  return meta.filter((m) => states.has(m.tone))
})

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

// Registro de transacciones: barra flotante expandible
const txOpen = ref(false)

onMounted(() => {
  ensure({ client_type: 'dashboard', name: 'Panel web SynapseCME' })
  void loadNetwork()
  void loadCore()
  coreTimer = setInterval(loadCore, 30_000)
})

onBeforeUnmount(() => {
  if (coreTimer) clearInterval(coreTimer)
})
</script>

<template>
  <div class="flex flex-col gap-4 xl:-mx-7 xl:-mt-6 xl:-mb-6">
    <ApiUnavailable v-if="failed" @retry="loadNetwork" />

    <template v-else>
      <!-- Lienzo full-bleed con paneles flotantes -->
      <div
        class="relative min-h-[70vh] overflow-hidden rounded-2xl border border-[#e3e8f2] xl:h-[calc(100dvh-61px)] xl:min-h-0 xl:rounded-none xl:border-0"
        style="background: radial-gradient(900px 600px at 50% 40%, rgba(29,99,216,.06), transparent), #eef2f9"
      >
        <div v-if="loading" class="absolute inset-0 z-10 flex items-center justify-center bg-[#eef2f9]/60 backdrop-blur-sm">
          <span class="animate-pulse text-sm text-[#5b6780]">Cargando grafo…</span>
        </div>
        <div v-if="!loading && !nodes.length" class="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center">
          <span class="grid h-14 w-14 place-items-center rounded-full border border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]">
            <Icon name="network" :size="32" />
          </span>
          <p class="max-w-xs text-sm text-[#5b6780]">
            El grafo está vacío. Captura registros desde la página de Captura para poblarlo.
          </p>
        </div>
        <ForceGraph ref="graphEl" :nodes="graphNodes" :links="graphLinks" :pulse-id="pulseTarget" class="absolute inset-0" />

        <!-- Título, estado del canal y acciones (flotante, arriba a la izquierda) -->
        <div class="absolute left-3 top-3 z-10 flex max-w-[calc(100%-1.5rem)] flex-col gap-2">
          <div class="rounded-xl border border-[#e3e8f2] bg-white/95 px-3 py-2 shadow-[0_4px_16px_rgba(16,24,40,0.08)] backdrop-blur-md">
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <div class="mr-1">
                <h1 class="font-display text-lg font-bold leading-tight text-[#101828]">Red en vivo</h1>
                <p class="text-[11px] leading-tight text-[#5b6780]">
                  Grafo de instalaciones en tiempo real, clientes conectados y registro de transacciones.
                </p>
              </div>
              <span
                class="glass-chip"
                :class="
                  wsStatus === 'online'
                    ? 'border-[#bfe8d2] bg-[#eefbf4] text-[#067647]'
                    : wsStatus === 'connecting'
                      ? 'border-[#f2e2a8] bg-[#fffaeb] text-[#8a6100]'
                      : 'border-[#f5a9a9] bg-[#fdf0f0] text-[#b42318]'
                "
              >
                <span
                  class="h-2 w-2 rounded-full"
                  :class="wsStatus === 'online' ? 'bg-[#17b26a]' : wsStatus === 'connecting' ? 'animate-pulse bg-[#d99a00]' : 'bg-[#d92d20]'"
                />
                {{ wsStatus === 'online' ? 'Canal WS activo' : wsStatus === 'connecting' ? 'Conectando…' : 'WS desconectado' }}
              </span>
              <button class="btn-ghost px-2.5 py-1.5 text-xs" @click="loadNetwork"><Icon name="refresh" :size="13" /> Actualizar</button>
            </div>
          </div>

          <!-- Leyenda de niveles (color del nodo) y estados (anillo) -->
          <div class="pointer-events-none w-fit rounded-xl border border-[#e3e8f2] bg-white/95 px-3 py-2 shadow-[0_4px_16px_rgba(16,24,40,0.08)] backdrop-blur-md">
            <p class="font-display text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7a8499]">Niveles</p>
            <ul class="mt-1 flex flex-col gap-1">
              <li v-for="t in typeLegend" :key="t.label" class="flex items-center gap-1.5 text-[11px] text-[#39445c]">
                <span class="h-2.5 w-2.5 shrink-0 rounded-full" :style="{ backgroundColor: t.color }" />
                {{ t.label }}
              </li>
            </ul>
            <template v-if="stateLegend.length">
              <p class="mt-2 font-display text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7a8499]">Estado</p>
              <ul class="mt-1 flex flex-col gap-1">
                <li v-for="s in stateLegend" :key="s.tone" class="flex items-center gap-1.5 text-[11px] text-[#39445c]">
                  <span
                    class="h-2.5 w-2.5 shrink-0 rounded-full border-2 border-transparent"
                    :style="{ borderColor: STATE_RING_COLORS[s.tone] }"
                  />
                  {{ s.label }}
                </li>
              </ul>
            </template>
          </div>
        </div>

        <!-- Paneles flotantes: nodo principal + clientes (desktop) -->
        <div class="absolute right-3 top-3 z-10 hidden w-[290px] flex-col gap-3 xl:flex">
          <div class="rounded-xl border border-[#e3e8f2] bg-white/95 p-4 shadow-[0_4px_16px_rgba(16,24,40,0.08)] backdrop-blur-md">
            <div class="flex items-center justify-between gap-2">
              <h2 class="font-display text-[13px] font-semibold text-[#101828]">Nodo principal</h2>
              <span
                class="glass-chip"
                :class="core && !coreFailed ? 'border-[#bfe8d2] bg-[#eefbf4] text-[#067647]' : 'border-[#f5a9a9] bg-[#fdf0f0] text-[#b42318]'"
              >
                <span
                  class="h-2 w-2 rounded-full"
                  :class="core && !coreFailed ? 'bg-[#17b26a]' : 'bg-[#d92d20]'"
                />
                {{ core && !coreFailed ? 'activo' : 'sin datos' }}
              </span>
            </div>
            <template v-if="core && !coreFailed">
              <p class="mt-1 truncate text-xs text-[#7a8499]" :title="core.qvac_url">
                {{ core.name }} · {{ core.qvac_url }}
              </p>
              <div class="mt-3 flex flex-col gap-2">
                <div>
                  <p class="text-[11px] font-medium uppercase tracking-wide text-[#7a8499]">Inferencia QVAC</p>
                  <ul class="mt-1 flex flex-col gap-1">
                    <li
                      v-for="m in core.models"
                      :key="m.id"
                      class="flex items-center justify-between gap-2 rounded-lg border border-[#e9edf5] bg-[#f7f9fd] px-2 py-1 text-xs"
                    >
                      <span class="truncate text-[#1a2233]">{{ m.id }}</span>
                      <span
                        class="flex items-center gap-1 text-[10px]"
                        :class="m.state === 'ready' ? 'text-[#067647]' : 'text-[#8a6100]'"
                      >
                        <span class="h-1.5 w-1.5 rounded-full" :class="m.state === 'ready' ? 'bg-[#17b26a]' : 'bg-[#d99a00]'" />
                        {{ m.state || 'cargado' }}
                      </span>
                    </li>
                    <li v-if="!core.models.length" class="text-xs text-[#b42318]">QVAC no responde</li>
                  </ul>
                  <p class="mt-1 text-[10px] text-[#7a8499]">
                    chat: {{ core.chat_model }} · embeddings: {{ core.embed_model }}
                  </p>
                </div>
                <div>
                  <p class="text-[11px] font-medium uppercase tracking-wide text-[#7a8499]">Dictado STT</p>
                  <p class="mt-1 flex items-center gap-1.5 text-xs text-[#5b6780]">
                    <span class="h-1.5 w-1.5 rounded-full" :class="core.stt_up ? 'bg-[#17b26a]' : 'bg-[#d92d20]'" />
                    {{ core.stt_model }}
                  </p>
                </div>
                <div>
                  <p class="text-[11px] font-medium uppercase tracking-wide text-[#7a8499]">Grafo Neo4j</p>
                  <div class="mt-1 flex flex-wrap gap-1.5">
                    <span class="glass-chip text-[11px]">{{ coreFacilityTotal }} instalaciones</span>
                    <span class="glass-chip text-[11px]">{{ coreEquipmentTotal }} equipos</span>
                    <span class="glass-chip text-[11px]">{{ coreObservationTotal }} observaciones</span>
                  </div>
                </div>
              </div>
            </template>
            <p v-else class="mt-2 text-xs text-[#7a8499]">
              No se pudo leer el estado del núcleo. Reintenta en unos segundos.
            </p>
          </div>

          <div class="flex max-h-[42vh] flex-col rounded-xl border border-[#e3e8f2] bg-white/95 p-4 shadow-[0_4px_16px_rgba(16,24,40,0.08)] backdrop-blur-md">
            <h2 class="font-display text-[13px] font-semibold text-[#101828]">Clientes conectados</h2>
            <span class="mt-0.5 text-xs text-[#7a8499]">{{ onlineClients.length }} en línea</span>
            <ul class="mt-3 flex flex-col gap-2 overflow-y-auto">
              <li
                v-for="(client, i) in clients"
                :key="`${client.name}-${i}`"
                class="flex items-center gap-3 rounded-xl border border-[#e9edf5] bg-[#f7f9fd] px-3 py-2"
              >
                <span class="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]">
                  <Icon :name="TYPE_ICONS[client.client_type] || 'activity'" :size="18" />
                </span>
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm text-[#101828]">{{ client.name || 'Cliente anónimo' }}</p>
                  <p class="text-[11px] text-[#7a8499]">{{ client.client_type }}</p>
                </div>
                <span class="flex items-center gap-1 text-[11px]" :class="(client.status || 'online') === 'online' ? 'text-[#067647]' : 'text-[#7a8499]'">
                  <span
                    class="h-1.5 w-1.5 rounded-full"
                    :class="(client.status || 'online') === 'online' ? 'bg-[#17b26a]' : 'bg-[#c4cddf]'"
                  />
                  {{ (client.status || 'online') === 'online' ? 'en línea' : 'inactivo' }}
                </span>
              </li>
              <li v-if="!clients.length" class="rounded-xl border border-dashed border-[#d4dbe8] p-4 text-center text-xs text-[#7a8499]">
                Aún no hay clientes en el canal WS.
              </li>
            </ul>
          </div>
        </div>

        <button
          class="absolute bottom-24 right-3 z-10 rounded-lg border border-[#d4dbe8] bg-white/95 px-2 py-1 text-[10px] text-[#39445c] shadow-[0_4px_16px_rgba(16,24,40,0.08)] backdrop-blur-md transition hover:border-[#c4ddfb] hover:text-[#1d63d8]"
          @click="graphEl?.resetView()"
        >
          Vista inicial
        </button>

        <p class="pointer-events-none absolute bottom-24 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-full border border-[#d4dbe8] bg-white/95 px-3 py-1 text-[10px] text-[#7a8499] shadow-[0_4px_16px_rgba(16,24,40,0.08)] backdrop-blur-md max-xl:hidden">
          Arrastra los nodos · arrastra el fondo para desplazarte · rueda para zoom
        </p>
        <div
          v-if="lastMutation"
          class="pointer-events-none absolute bottom-24 left-3 z-10 max-w-md rounded-xl border border-[#bfe8d2] bg-[#eefbf4] px-3 py-2 text-xs text-[#067647] shadow-[0_4px_16px_rgba(16,24,40,0.08)] backdrop-blur-md"
        >
          Última mutación: {{ lastMutation.summary }}
        </div>

        <!-- Registro de transacciones: barra flotante expandible -->
        <div class="absolute inset-x-3 bottom-3 z-20 rounded-xl border border-[#e3e8f2] bg-white/95 p-3 shadow-[0_4px_16px_rgba(16,24,40,0.08)] backdrop-blur-md">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="font-display text-[13px] font-semibold text-[#101828]">Registro de transacciones</h2>
            <span class="text-xs text-[#7a8499]">
              <template v-if="!filteredTxs.length">Sin transacciones registradas todavía.</template>
              <template v-else>{{ filteredTxs.length }} transacciones</template>
            </span>
            <div class="ml-auto flex flex-wrap items-center gap-2">
              <label class="text-xs text-[#5b6780]" for="tx-filter">Acción</label>
              <select id="tx-filter" v-model="actionFilter" class="glass-input w-auto rounded-lg px-2 py-1.5 text-xs">
                <option v-for="opt in ACTION_OPTIONS" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
              <button class="btn-ghost px-3 py-1.5 text-xs" @click="paused = !paused">
                <Icon v-if="paused" name="play" :size="12" />
                <Icon v-else name="pause" :size="12" />
                {{ paused ? 'Reanudar' : 'Pausar' }}
              </button>
              <button class="btn-ghost px-3 py-1.5 text-xs" @click="txOpen = !txOpen">
                <Icon :name="txOpen ? 'chevron-down' : 'chevron-up'" :size="12" />
                {{ txOpen ? 'Contraer' : 'Expandir' }}
              </button>
            </div>
          </div>
          <div v-if="txOpen" class="mt-3 max-h-56 overflow-y-auto rounded-xl border border-[#e3e8f2]">
            <table class="w-full border-collapse">
              <thead class="sticky top-0 bg-[#f7f9fd]">
                <tr>
                  <th class="th-cell">Hora</th>
                  <th class="th-cell">Actor</th>
                  <th class="th-cell">Acción</th>
                  <th class="th-cell">Objetivo</th>
                  <th class="th-cell">Transición de estado</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(tx, i) in filteredTxs" :key="i" class="border-t border-[#eef1f7] transition hover:bg-[#f7f9fd]">
                  <td class="td-cell whitespace-nowrap text-[#7a8499]">{{ fmtTime(tx.at) }}</td>
                  <td class="td-cell">{{ tx.actor }}</td>
                  <td class="td-cell">
                    <span class="glass-chip">{{ tx.action }}</span>
                  </td>
                  <td class="td-cell">{{ tx.target || '—' }}</td>
                  <td class="td-cell text-[#7a8499]">{{ tx.transition || '—' }}</td>
                </tr>
                <tr v-if="!filteredTxs.length">
                  <td colspan="5" class="px-4 py-6 text-center text-xs text-[#7a8499]">
                    Sin transacciones registradas todavía.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Paneles apilados bajo el grafo (móvil/tablet) -->
      <div class="grid gap-4 xl:hidden">
        <div class="glass p-4">
          <div class="flex items-center justify-between gap-2">
            <h2 class="font-display text-[13px] font-semibold text-[#101828]">Nodo principal</h2>
            <span
              class="glass-chip"
              :class="core && !coreFailed ? 'border-[#bfe8d2] bg-[#eefbf4] text-[#067647]' : 'border-[#f5a9a9] bg-[#fdf0f0] text-[#b42318]'"
            >
              <span
                class="h-2 w-2 rounded-full"
                :class="core && !coreFailed ? 'bg-[#17b26a]' : 'bg-[#d92d20]'"
              />
              {{ core && !coreFailed ? 'activo' : 'sin datos' }}
            </span>
          </div>
          <template v-if="core && !coreFailed">
            <p class="mt-1 truncate text-xs text-[#7a8499]" :title="core.qvac_url">
              {{ core.name }} · {{ core.qvac_url }}
            </p>
            <div class="mt-3 flex flex-col gap-2">
              <div>
                <p class="text-[11px] font-medium uppercase tracking-wide text-[#7a8499]">Inferencia QVAC</p>
                <ul class="mt-1 flex flex-col gap-1">
                  <li
                    v-for="m in core.models"
                    :key="m.id"
                    class="flex items-center justify-between gap-2 rounded-lg border border-[#e9edf5] bg-[#f7f9fd] px-2 py-1 text-xs"
                  >
                    <span class="truncate text-[#1a2233]">{{ m.id }}</span>
                    <span
                      class="flex items-center gap-1 text-[10px]"
                      :class="m.state === 'ready' ? 'text-[#067647]' : 'text-[#8a6100]'"
                    >
                      <span class="h-1.5 w-1.5 rounded-full" :class="m.state === 'ready' ? 'bg-[#17b26a]' : 'bg-[#d99a00]'" />
                      {{ m.state || 'cargado' }}
                    </span>
                  </li>
                  <li v-if="!core.models.length" class="text-xs text-[#b42318]">QVAC no responde</li>
                </ul>
                <p class="mt-1 text-[10px] text-[#7a8499]">
                  chat: {{ core.chat_model }} · embeddings: {{ core.embed_model }}
                </p>
              </div>
              <div>
                <p class="text-[11px] font-medium uppercase tracking-wide text-[#7a8499]">Dictado STT</p>
                <p class="mt-1 flex items-center gap-1.5 text-xs text-[#5b6780]">
                  <span class="h-1.5 w-1.5 rounded-full" :class="core.stt_up ? 'bg-[#17b26a]' : 'bg-[#d92d20]'" />
                  {{ core.stt_model }}
                </p>
              </div>
              <div>
                <p class="text-[11px] font-medium uppercase tracking-wide text-[#7a8499]">Grafo Neo4j</p>
                <div class="mt-1 flex flex-wrap gap-1.5">
                  <span class="glass-chip text-[11px]">{{ coreFacilityTotal }} instalaciones</span>
                  <span class="glass-chip text-[11px]">{{ coreEquipmentTotal }} equipos</span>
                  <span class="glass-chip text-[11px]">{{ coreObservationTotal }} observaciones</span>
                </div>
              </div>
            </div>
          </template>
          <p v-else class="mt-2 text-xs text-[#7a8499]">
            No se pudo leer el estado del núcleo. Reintenta en unos segundos.
          </p>
        </div>

        <div class="glass flex max-h-[46vh] flex-col p-4">
          <h2 class="font-display text-[13px] font-semibold text-[#101828]">Clientes conectados</h2>
          <span class="mt-0.5 text-xs text-[#7a8499]">{{ onlineClients.length }} en línea</span>
          <ul class="mt-3 flex flex-col gap-2 overflow-y-auto">
            <li
              v-for="(client, i) in clients"
              :key="`${client.name}-${i}`"
              class="flex items-center gap-3 rounded-xl border border-[#e9edf5] bg-[#f7f9fd] px-3 py-2"
            >
              <span class="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]">
                <Icon :name="TYPE_ICONS[client.client_type] || 'activity'" :size="18" />
              </span>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm text-[#101828]">{{ client.name || 'Cliente anónimo' }}</p>
                <p class="text-[11px] text-[#7a8499]">{{ client.client_type }}</p>
              </div>
              <span class="flex items-center gap-1 text-[11px]" :class="(client.status || 'online') === 'online' ? 'text-[#067647]' : 'text-[#7a8499]'">
                <span
                  class="h-1.5 w-1.5 rounded-full"
                  :class="(client.status || 'online') === 'online' ? 'bg-[#17b26a]' : 'bg-[#c4cddf]'"
                />
                {{ (client.status || 'online') === 'online' ? 'en línea' : 'inactivo' }}
              </span>
            </li>
            <li v-if="!clients.length" class="rounded-xl border border-dashed border-[#d4dbe8] p-4 text-center text-xs text-[#7a8499]">
              Aún no hay clientes en el canal WS.
            </li>
          </ul>
        </div>
      </div>
    </template>
  </div>
</template>
