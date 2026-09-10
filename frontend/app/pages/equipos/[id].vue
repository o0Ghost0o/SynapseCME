<script setup lang="ts">
const route = useRoute()
const { fetchWithAuth } = useApi()

const loading = ref(true)
const failed = ref(false)
const notFound = ref(false)
const detail = ref<EquipmentDetailData | null>(null)

const equipmentId = computed(() => String(route.params.id || ''))

async function load() {
  loading.value = true
  failed.value = false
  notFound.value = false
  try {
    const res = await fetchWithAuth(`/api/equipment/${encodeURIComponent(equipmentId.value)}`)
    if (res.status === 404) {
      notFound.value = true
      detail.value = null
      return
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    detail.value = normalizeEquipmentDetail(await res.json())
  } catch {
    failed.value = true
    detail.value = null
  } finally {
    loading.value = false
  }
}

const equipment = computed(() => detail.value?.equipment ?? null)

const title = computed(() =>
  [equipment.value?.manufacturer, equipment.value?.model].filter(Boolean).join(' ') || 'Equipo sin modelo',
)

const hasIssues = computed(() =>
  (detail.value?.parameters ?? []).some((p) => p.status === 'warning' || p.status === 'critical'),
)

const parameters = computed(() => detail.value?.parameters ?? [])
const observations = computed(() => detail.value?.observations ?? [])
const parameterHistory = computed(() => detail.value?.parameterHistory ?? [])

function observationParams(obs: ObservationEntry): ParameterEntry[] {
  return parameterHistory.value.filter((p) => p.sourceObservationId === obs.id)
}

function paramValue(p: ParameterEntry): string {
  if (p.value === null || p.value === '') return '—'
  return `${p.value}${p.unit ? ` ${p.unit}` : ''}`
}

watch(equipmentId, load)
onMounted(load)
</script>

<template>
  <div class="flex flex-col gap-4">
    <button class="btn-ghost self-start" @click="navigateTo('/dashboard')">← Volver al panel</button>

    <div v-if="loading" class="glass p-10 text-center text-sm text-slate-400">
      <span class="animate-pulse">Cargando equipo…</span>
    </div>

    <ApiUnavailable v-else-if="failed" @retry="load" />

    <div v-else-if="notFound" class="glass mx-auto max-w-md p-8 text-center">
      <p class="text-4xl">🔍</p>
      <h1 class="mt-3 text-xl font-bold text-white">Equipo no encontrado</h1>
      <p class="mt-2 text-sm text-slate-400">
        No existe un equipo con el identificador «{{ equipmentId }}» en el grafo.
      </p>
      <button class="btn-primary mt-5" @click="navigateTo('/dashboard')">Volver al panel</button>
    </div>

    <template v-else-if="equipment">
      <div class="glass-strong p-5">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <h1 class="text-xl font-bold text-white">{{ title }}</h1>
            <p class="mt-1 text-sm text-slate-400">
              🏥 {{ equipment.facilityName
              }}<span v-if="equipment.city || equipment.country">
                · {{ [equipment.city, equipment.country].filter(Boolean).join(', ') }}
              </span>
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <span class="glass-chip">{{ equipment.modality }}</span>
            <span v-if="equipment.ageYears !== null" class="glass-chip">{{ equipment.ageYears }} años</span>
            <StateChip :estado="equipment.state" />
          </div>
        </div>
      </div>

      <div
        v-if="hasIssues"
        class="glass flex items-center gap-3 border-amber-300/30 bg-amber-400/10 px-4 py-3"
      >
        <span class="text-xl">⚠️</span>
        <p class="text-sm text-amber-200">Posible mantenimiento/reparación: hay parámetros fuera de rango.</p>
      </div>

      <section class="glass p-5">
        <h2 class="text-sm font-semibold text-white">Parámetros</h2>
        <p class="mt-0.5 text-xs text-slate-500">Último valor registrado por magnitud técnica.</p>
        <ul v-if="parameters.length" class="mt-3 flex flex-col gap-2">
          <li
            v-for="p in parameters"
            :key="p.id"
            class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2"
          >
            <div class="min-w-0">
              <p class="text-sm capitalize text-slate-200">{{ p.name }}</p>
              <p class="text-[11px] text-slate-500">{{ relativeDate(p.createdAt) }}</p>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-sm font-semibold text-white">{{ paramValue(p) }}</span>
              <span v-if="p.status" class="glass-chip" :class="PARAMETER_STATUS_CLASSES[p.status]">
                {{ PARAMETER_STATUS_LABELS[p.status] }}
              </span>
              <span v-else class="glass-chip">sin clasificar</span>
            </div>
          </li>
        </ul>
        <p v-else class="mt-3 rounded-xl border border-dashed border-white/15 p-4 text-center text-xs text-slate-500">
          Todavía no hay parámetros registrados para este equipo.
        </p>
      </section>

      <section class="glass p-5">
        <h2 class="text-sm font-semibold text-white">Historial de observaciones</h2>
        <p class="mt-0.5 text-xs text-slate-500">{{ observations.length }} observaciones en el grafo.</p>
        <ol v-if="observations.length" class="mt-4 flex flex-col gap-4 border-l border-white/10 pl-4">
          <li v-for="obs in observations" :key="obs.id" class="relative">
            <span class="absolute -left-[21.5px] top-1.5 h-2.5 w-2.5 rounded-full border border-indigo-300/40 bg-indigo-400/60" />
            <p class="text-sm leading-relaxed text-slate-200">{{ obs.text }}</p>
            <div class="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
              <span class="glass-chip">👤 {{ obs.contributor }}</span>
              <span class="glass-chip">🕒 {{ relativeDate(obs.createdAt) }}</span>
              <span v-if="obs.confidence !== null" class="glass-chip">
                Confianza {{ Math.round(obs.confidence * 100) }}%
              </span>
            </div>
            <div v-if="observationParams(obs).length" class="mt-2 flex flex-wrap gap-1.5">
              <span
                v-for="p in observationParams(obs)"
                :key="p.id"
                class="glass-chip"
                :class="p.status ? PARAMETER_STATUS_CLASSES[p.status] : ''"
              >
                {{ p.name }}: {{ paramValue(p) }}
              </span>
            </div>
          </li>
        </ol>
        <p v-else class="mt-3 rounded-xl border border-dashed border-white/15 p-4 text-center text-xs text-slate-500">
          Sin observaciones registradas todavía.
        </p>
      </section>
    </template>
  </div>
</template>
