<script setup lang="ts">
import { useToast } from '~/composables/useToast'

const { request } = useApi()
const { show } = useToast()
const { lastMutation } = useEvents()

const loading = ref(false)
const failed = ref(false)
const tree = ref<RegionNode[]>([])
const facility = ref<FacilityInfo | null>(null)
const facilityLoading = ref(false)
// En <lg el árbol va colapsado tras un toggle (la rejilla pasa a una columna).
const showTree = ref(false)

// Expansión del árbol
const expandedRegions = ref<Set<string>>(new Set())
const expandedCountries = ref<Set<string>>(new Set())

function toggle(set: Set<string>, key: string) {
  const next = new Set(set)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  return next
}

const totalFacilities = computed(() =>
  tree.value.reduce(
    (acc, r) => acc + r.countries.reduce((a, c) => a + c.facilities.length, 0),
    0,
  ),
)

async function loadTree() {
  loading.value = true
  failed.value = false
  try {
    tree.value = normalizeHierarchyTree(await request('/api/hierarchy'))
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

async function pickFacility(f: FacilityRef) {
  facilityLoading.value = true
  // En móvil, elegir instalación cierra el árbol para dejar sitio al detalle.
  showTree.value = false
  try {
    facility.value = normalizeFacility(await request(`/api/facility/${encodeURIComponent(f.id)}`), f.id)
  } catch {
    facility.value = null
    show('No se pudo cargar la instalación')
  } finally {
    facilityLoading.value = false
  }
}

const modalityGroups = computed(() => {
  if (showAll.value) {
    const map = new Map<string, EquipmentListItem[]>()
    for (const eq of globalItems.value) {
      const list = map.get(eq.modality) || []
      list.push(eq)
      map.set(eq.modality, list)
    }
    return [...map.entries()].map(([modality, items]) => ({ modality, items }))
  }
  const map = new Map<string, EquipmentItem[]>()
  for (const eq of filteredEquipment.value) {
    const list = map.get(eq.modality) || []
    list.push(eq)
    map.set(eq.modality, list)
  }
  return [...map.entries()].map(([modality, items]) => ({ modality, items }))
})

// ---------------------------------------------------------------------------
// Filtros (3b): client-side sobre la facility seleccionada; el toggle "Ver
// todos" dispara GET /api/equipments con los filtros server-side.
// ---------------------------------------------------------------------------
const showAll = ref(false)
const filterModality = ref('')
const filterManufacturer = ref('')
const filterState = ref('')
const filterCountry = ref('')
const searchQuery = ref('')

const hasActiveFilters = computed(() =>
  Boolean(filterModality.value || filterManufacturer.value || filterState.value || filterCountry.value || searchQuery.value.trim()),
)

function clearFilters() {
  filterModality.value = ''
  filterManufacturer.value = ''
  filterState.value = ''
  filterCountry.value = ''
  searchQuery.value = ''
}

const countryOptions = computed(() => {
  const set = new Set<string>()
  for (const region of tree.value) for (const country of region.countries) set.add(country.name)
  return [...set].sort((a, b) => a.localeCompare(b, 'es'))
})

function equipmentName(eq: { manufacturer: string, model: string }): string {
  return [eq.manufacturer, eq.model].filter(Boolean).join(' ')
}

/* Los ítems globales usan ageYears/facilityName; los de facility, age/updatedAt. */
function itemAge(eq: EquipmentItem | EquipmentListItem): number | null {
  return 'age' in eq ? eq.age : eq.ageYears
}
function itemUpdatedAt(eq: EquipmentItem | EquipmentListItem): string {
  return 'updatedAt' in eq ? eq.updatedAt : ''
}
function itemFacilityName(eq: EquipmentItem | EquipmentListItem): string {
  return 'facilityName' in eq ? eq.facilityName : ''
}

// Opciones pobladas desde la facility cargada + el listado global traído para opciones.
const optionPool = computed(() => {
  const fromFacility = (facility.value?.equipment ?? []).map((eq) => ({
    modality: eq.modality,
    manufacturer: eq.manufacturer,
    state: eq.state,
  }))
  const fromGlobal = globalOptionItems.value.map((eq) => ({
    modality: eq.modality,
    manufacturer: eq.manufacturer,
    state: eq.state,
  }))
  return [...fromFacility, ...fromGlobal]
})

const modalityOptions = computed(() => [...new Set(optionPool.value.map((e) => e.modality).filter(Boolean))].sort((a, b) => a.localeCompare(b)))
const manufacturerOptions = computed(() => [...new Set(optionPool.value.map((e) => e.manufacturer).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es')))
const stateOptions = computed(() => [...new Set(optionPool.value.map((e) => e.state).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es')))

const filteredEquipment = computed(() => {
  const list = facility.value?.equipment ?? []
  const q = searchQuery.value.trim().toLowerCase()
  return list.filter(
    (eq) =>
      (!filterModality.value || eq.modality === filterModality.value) &&
      (!filterManufacturer.value || eq.manufacturer === filterManufacturer.value) &&
      (!filterState.value || eq.state === filterState.value) &&
      (!q || equipmentName(eq).toLowerCase().includes(q)),
  )
})

const RENEWAL_STATES = ['estimado', 'confirmado']

// Vista global: resultados filtrados (server-side) + ítems sin filtrar para opciones.
const globalItems = ref<EquipmentListItem[]>([])
const globalOptionItems = ref<EquipmentListItem[]>([])
const globalTotal = ref(0)
const globalLoading = ref(false)

function globalParams(): string {
  const params = new URLSearchParams()
  if (filterModality.value) params.set('modality', filterModality.value)
  if (filterManufacturer.value) params.set('manufacturer', filterManufacturer.value)
  if (filterState.value) params.set('state', filterState.value)
  if (filterCountry.value) params.set('country', filterCountry.value)
  const q = searchQuery.value.trim()
  if (q) params.set('q', q)
  params.set('limit', '500')
  return params.toString()
}

async function loadGlobal() {
  globalLoading.value = true
  try {
    const data = normalizeEquipmentList(await request(`/api/equipments?${globalParams()}`))
    globalItems.value = data.items
    globalTotal.value = data.total
  } catch {
    show('No se pudo cargar el listado global de equipos')
  } finally {
    globalLoading.value = false
  }
}

async function loadGlobalOptions() {
  if (globalOptionItems.value.length) return
  try {
    globalOptionItems.value = normalizeEquipmentList(await request('/api/equipments?limit=500')).items
  } catch {
    // Las opciones se quedan solo con las de la facility; no es bloqueante.
  }
}

let globalTimer: ReturnType<typeof setTimeout> | undefined
watch([showAll, filterModality, filterManufacturer, filterState, filterCountry, searchQuery], () => {
  if (!showAll.value) return
  void loadGlobalOptions()
  clearTimeout(globalTimer)
  globalTimer = setTimeout(loadGlobal, 300)
})

const renewalOpportunities = computed(() => {
  if (!facility.value) return []
  return facility.value.equipment.filter(
    (eq) => eq.age !== null && eq.age >= 8 && RENEWAL_STATES.includes(eq.state.toLowerCase()),
  )
})

function freshness(updatedAt: string): string {
  if (!updatedAt) return 'Sin fecha'
  const d = new Date(updatedAt)
  if (Number.isNaN(d.getTime())) return 'Sin fecha'
  const days = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (days <= 1) return 'Actualizado hoy'
  if (days < 30) return `Hace ${days} días`
  if (days < 365) return `Hace ${Math.floor(days / 30)} meses`
  return `Hace ${Math.floor(days / 365)} años`
}

// Refresco en vivo: debounce de 2 s para no refetchear el árbol en ráfagas.
let refreshTimer: ReturnType<typeof setTimeout> | undefined
watch(lastMutation, () => {
  clearTimeout(refreshTimer)
  refreshTimer = setTimeout(() => {
    if (facility.value) void pickFacility({ id: facility.value.id, name: facility.value.name })
    void loadTree()
  }, 2000)
})

onMounted(loadTree)
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold text-white">Panel 360 — Cliente</h1>
        <p class="mt-1 text-sm text-slate-400">
          Explora la jerarquía región → país → instalación y revisa el estado de la base instalada.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="tree.length" class="glass-chip">{{ tree.length }} regiones · {{ totalFacilities }} instalaciones</span>
        <button class="btn-ghost" :disabled="loading" @click="loadTree">
          {{ loading ? 'Actualizando…' : 'Actualizar' }}
        </button>
      </div>
    </div>

    <ApiUnavailable v-if="failed" @retry="loadTree" />
    <div v-else-if="loading && !tree.length" class="glass p-10 text-center text-sm text-slate-400">
      <span class="animate-pulse">Cargando jerarquía…</span>
    </div>

    <div v-else class="grid gap-4 lg:grid-cols-[360px_1fr]">
      <button class="btn-ghost lg:hidden" @click="showTree = !showTree">
        {{ showTree ? '▲ Ocultar jerarquía' : '▼ Mostrar jerarquía' }}
        <span v-if="tree.length" class="glass-chip">{{ totalFacilities }} instalaciones</span>
      </button>

      <!-- Árbol de jerarquía -->
      <div class="glass max-h-[75vh] overflow-y-auto p-4" :class="showTree ? '' : 'hidden lg:block'">
        <h2 class="text-sm font-semibold text-white">Jerarquía</h2>
        <p class="mt-0.5 text-xs text-slate-500">Regiones · Países · Instalaciones</p>

        <div class="mt-3 flex flex-col gap-1.5">
          <div v-for="region in tree" :key="`r-${region.name}`">
            <button
              class="btn-ghost w-full justify-between text-left"
              @click="expandedRegions = toggle(expandedRegions, region.name)"
            >
              <span class="flex items-center gap-2">
                <span class="text-slate-400 transition" :class="expandedRegions.has(region.name) ? 'rotate-90' : ''">▸</span>
                🌍 {{ region.name }}
              </span>
              <span class="glass-chip">{{ region.countries.length }} países</span>
            </button>

            <div v-if="expandedRegions.has(region.name)" class="ml-4 mt-1.5 flex flex-col gap-1.5 border-l border-white/10 pl-3">
              <div v-for="country in region.countries" :key="`c-${region.name}-${country.name}`">
                <button
                  class="btn-ghost w-full justify-between text-left"
                  @click="expandedCountries = toggle(expandedCountries, `${region.name}/${country.name}`)"
                >
                  <span class="flex items-center gap-2">
                    <span class="text-slate-400 transition" :class="expandedCountries.has(`${region.name}/${country.name}`) ? 'rotate-90' : ''">▸</span>
                    🏳️ {{ country.name }}
                  </span>
                  <span class="glass-chip">{{ country.facilities.length }}</span>
                </button>

                <div
                  v-if="expandedCountries.has(`${region.name}/${country.name}`)"
                  class="ml-4 mt-1.5 flex flex-col gap-1 border-l border-white/10 pl-3"
                >
                  <button
                    v-for="f in country.facilities"
                    :key="`f-${f.id}`"
                    class="btn-ghost justify-between text-left"
                    :class="facility?.id === f.id ? 'border-indigo-300/40 bg-indigo-400/20' : ''"
                    @click="pickFacility(f)"
                  >
                    <span>🏥 {{ f.name }}</span>
                    <span class="text-slate-500">→</span>
                  </button>
                  <p v-if="!country.facilities.length" class="rounded-lg border border-dashed border-white/10 px-3 py-1.5 text-[11px] text-slate-500">
                    Sin instalaciones registradas
                  </p>
                </div>
              </div>
            </div>
          </div>

          <p v-if="!tree.length" class="rounded-xl border border-dashed border-white/15 p-6 text-center text-xs text-slate-500">
            Sin datos de jerarquía todavía.
          </p>
        </div>
      </div>

      <!-- Panel de detalle -->
      <div class="flex min-h-64 flex-col gap-4">
        <div v-if="facilityLoading" class="glass p-10 text-center text-sm text-slate-400">
          <span class="animate-pulse">Cargando instalación…</span>
        </div>

        <template v-else-if="facility || showAll">
          <div v-if="facility" class="glass-strong flex flex-wrap items-start justify-between gap-3 p-5">
            <div>
              <h2 class="text-xl font-bold text-white">{{ facility.name }}</h2>
              <p class="mt-0.5 text-sm text-slate-400">
                {{ [facility.city, facility.country].filter(Boolean).join(' · ') || 'Sin ubicación' }}
              </p>
            </div>
            <span class="glass-chip">
              {{ showAll ? `${globalTotal} equipos (global)` : `${facility.equipment.length} equipos` }}
            </span>
          </div>

          <!-- Barra de filtros -->
          <div class="glass flex flex-col gap-3 p-4">
            <div class="flex flex-wrap items-center gap-2">
              <button
                class="btn-ghost"
                :class="showAll ? 'border-indigo-300/40 bg-indigo-400/20' : ''"
                @click="showAll = !showAll"
              >
                {{ showAll ? '◉ Viendo todos los equipos' : '○ Ver todos los equipos' }}
              </button>
              <button v-if="hasActiveFilters" class="btn-ghost" @click="clearFilters">Limpiar filtros</button>
              <span v-if="globalLoading" class="text-xs text-slate-500">Actualizando…</span>
            </div>
            <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
              <label class="flex flex-col gap-1 text-[11px] text-slate-400">
                Modalidad
                <select v-model="filterModality" class="glass-input py-2 text-sm">
                  <option value="">Todas</option>
                  <option v-for="m in modalityOptions" :key="m" :value="m">{{ m }}</option>
                </select>
              </label>
              <label class="flex flex-col gap-1 text-[11px] text-slate-400">
                Fabricante
                <select v-model="filterManufacturer" class="glass-input py-2 text-sm">
                  <option value="">Todos</option>
                  <option v-for="m in manufacturerOptions" :key="m" :value="m">{{ m }}</option>
                </select>
              </label>
              <label class="flex flex-col gap-1 text-[11px] text-slate-400">
                Estado
                <select v-model="filterState" class="glass-input py-2 text-sm">
                  <option value="">Todos</option>
                  <option v-for="s in stateOptions" :key="s" :value="s">{{ s }}</option>
                </select>
              </label>
              <label class="flex flex-col gap-1 text-[11px] text-slate-400" :class="showAll ? '' : 'opacity-50'">
                País
                <select v-model="filterCountry" class="glass-input py-2 text-sm" :disabled="!showAll">
                  <option value="">Todos</option>
                  <option v-for="c in countryOptions" :key="c" :value="c">{{ c }}</option>
                </select>
              </label>
              <label class="flex flex-col gap-1 text-[11px] text-slate-400">
                Buscar
                <input
                  v-model="searchQuery"
                  type="search"
                  placeholder="Fabricante o modelo…"
                  class="glass-input py-2 text-sm"
                />
              </label>
            </div>
          </div>

          <div v-if="modalityGroups.length" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <div v-for="group in modalityGroups" :key="group.modality" data-testid="modality-card" class="glass p-4">
              <div class="flex items-center justify-between gap-2">
                <h3 class="text-sm font-semibold text-white">{{ group.modality }}</h3>
                <span class="glass-chip">×{{ group.items.length }}</span>
              </div>
              <ul class="mt-3 flex flex-col gap-2">
                <li
                  v-for="eq in group.items"
                  :key="eq.id"
                  data-testid="equipment-item"
                  class="flex cursor-pointer items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 transition hover:border-indigo-300/30 hover:bg-white/10"
                  @click="navigateTo(`/equipos/${eq.id}`)"
                >
                  <div class="min-w-0">
                    <p class="truncate text-xs text-slate-200">
                      {{ equipmentName(eq) || 'Equipo sin modelo' }}
                    </p>
                    <p class="mt-0.5 text-[11px] text-slate-500">
                      <template v-if="showAll">🏥 {{ itemFacilityName(eq) }} · </template>
                      {{ itemAge(eq) !== null ? `${itemAge(eq)} años` : 'Antigüedad desconocida' }}
                      <template v-if="!showAll">· {{ freshness(itemUpdatedAt(eq)) }}</template>
                    </p>
                  </div>
                  <StateChip :estado="eq.state" />
                </li>
              </ul>
            </div>
          </div>
          <p v-else class="glass border-dashed p-6 text-center text-sm text-slate-500">
            <template v-if="showAll">Ningún equipo coincide con los filtros.</template>
            <template v-else-if="hasActiveFilters">Ningún equipo de esta instalación coincide con los filtros.</template>
            <template v-else>Esta instalación no tiene equipos registrados todavía.</template>
          </p>

          <div v-if="facility && !showAll" class="glass p-5">
            <h3 class="text-sm font-semibold text-amber-200">Oportunidades de renovación</h3>
            <p class="mt-0.5 text-xs text-slate-400">Equipos estimados o confirmados con más de 8 años.</p>
            <ul v-if="renewalOpportunities.length" class="mt-3 flex flex-col gap-2">
              <li
                v-for="eq in renewalOpportunities"
                :key="eq.id"
                class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-300/20 bg-amber-400/10 px-3 py-2"
              >
                <div>
                  <p class="text-sm text-amber-100">
                    {{ eq.modality }} — {{ [eq.manufacturer, eq.model].filter(Boolean).join(' ') || 'sin modelo' }}
                  </p>
                  <p class="text-[11px] text-amber-200/70">{{ eq.age }} años de antigüedad</p>
                </div>
                <StateChip :estado="eq.state" />
              </li>
            </ul>
            <p v-else class="mt-3 rounded-xl border border-dashed border-white/15 p-4 text-center text-xs text-slate-500">
              Sin oportunidades: ningún equipo supera los 8 años.
            </p>
          </div>
        </template>

        <div v-else class="glass flex flex-1 flex-col items-center justify-center p-10 text-center">
          <p class="text-4xl">🏥</p>
          <p class="mt-3 max-w-xs text-sm text-slate-400">
            Expande una región y un país en el árbol y selecciona una instalación para ver su ficha 360.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
