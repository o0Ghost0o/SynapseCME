<script setup lang="ts">
import { useToast } from '~/composables/useToast'

const { request } = useApi()
const { show } = useToast()
const { lastMutation } = useEvents()

const loading = ref(false)
const failed = ref(false)
const regions = ref<HierarchyItem[]>([])
const countries = ref<HierarchyItem[]>([])
const facilities = ref<HierarchyItem[]>([])
const selectedRegion = ref('')
const selectedCountry = ref('')
const facility = ref<FacilityInfo | null>(null)
const facilityLoading = ref(false)

const crumbs = computed(() => {
  const list: Array<{ label: string; level: number }> = [{ label: 'Regiones', level: 0 }]
  if (selectedRegion.value) list.push({ label: selectedRegion.value, level: 1 })
  if (selectedCountry.value) list.push({ label: selectedCountry.value, level: 2 })
  return list
})

async function loadRegions() {
  loading.value = true
  failed.value = false
  try {
    regions.value = normalizeHierarchy(await request('/api/hierarchy'))
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

async function pickRegion(region: string) {
  selectedRegion.value = region
  selectedCountry.value = ''
  facilities.value = []
  facility.value = null
  try {
    countries.value = normalizeHierarchy(await request(`/api/hierarchy?region=${encodeURIComponent(region)}`))
  } catch {
    countries.value = []
  }
}

async function pickCountry(country: string) {
  selectedCountry.value = country
  facility.value = null
  try {
    facilities.value = normalizeHierarchy(
      await request(
        `/api/hierarchy?region=${encodeURIComponent(selectedRegion.value)}&country=${encodeURIComponent(country)}`,
      ),
    )
  } catch {
    facilities.value = []
  }
}

async function pickFacility(item: HierarchyItem) {
  facilityLoading.value = true
  try {
    facility.value = normalizeFacility(await request(`/api/facility/${encodeURIComponent(item.id)}`), item.id)
  } catch {
    facility.value = null
    show('No se pudo cargar la instalación')
  } finally {
    facilityLoading.value = false
  }
}

function goToLevel(level: number) {
  if (level === 0) {
    selectedRegion.value = ''
    selectedCountry.value = ''
    countries.value = []
    facilities.value = []
    facility.value = null
  } else if (level === 1) {
    pickRegion(selectedRegion.value)
  }
}

const modalityGroups = computed(() => {
  if (!facility.value) return []
  const map = new Map<string, EquipmentItem[]>()
  for (const eq of facility.value.equipment) {
    const list = map.get(eq.modality) || []
    list.push(eq)
    map.set(eq.modality, list)
  }
  return [...map.entries()].map(([modality, items]) => ({ modality, items }))
})

const RENEWAL_STATES = ['estimado', 'confirmado']

const renewalOpportunities = computed(() => {
  if (!facility.value) return []
  return facility.value.equipment.filter(
    (eq) => eq.age !== null && eq.age >= 8 && RENEWAL_STATES.includes(stateToneLabel(eq)),
  )
})

function stateToneLabel(eq: EquipmentItem): string {
  return eq.state.toLowerCase()
}

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

// Refresco en vivo cuando llega una mutación por WS (con debounce)
let refreshTimer: ReturnType<typeof setTimeout> | undefined
watch(lastMutation, () => {
  clearTimeout(refreshTimer)
  refreshTimer = setTimeout(() => {
    if (facility.value) void pickFacility({ id: facility.value.id, name: facility.value.name })
    else void loadRegions()
  }, 600)
})

onMounted(loadRegions)
</script>

<template>
  <div class="flex flex-col gap-4">
    <div>
      <h1 class="text-2xl font-bold text-white">Panel 360 — Cliente</h1>
      <p class="mt-1 text-sm text-slate-400">
        Explora región → país → instalación y revisa el estado de la base instalada.
      </p>
    </div>

    <ApiUnavailable v-if="failed" @retry="loadRegions" />
    <div v-else-if="loading" class="glass p-10 text-center text-sm text-slate-400">
      <span class="animate-pulse">Cargando jerarquía…</span>
    </div>

    <div v-else class="grid gap-4 lg:grid-cols-[320px_1fr]">
      <!-- Panel de jerarquía -->
      <div class="glass p-4">
        <h2 class="text-sm font-semibold text-white">Jerarquía</h2>
        <nav class="mt-2 flex flex-wrap items-center gap-1 text-xs text-slate-400">
          <template v-for="(crumb, i) in crumbs" :key="i">
            <span v-if="i" class="text-slate-600">/</span>
            <button
              class="rounded-lg px-1.5 py-0.5 transition hover:bg-white/10 hover:text-white"
              :class="i === crumbs.length - 1 ? 'font-semibold text-white' : ''"
              @click="goToLevel(crumb.level)"
            >
              {{ crumb.label }}
            </button>
          </template>
        </nav>

        <div class="mt-3 flex flex-col gap-1.5">
          <button
            v-if="!selectedRegion"
            v-for="item in regions"
            :key="item.id"
            class="btn-ghost justify-between text-left"
            @click="pickRegion(item.name)"
          >
            <span>🌍 {{ item.name }}</span>
            <span class="text-slate-500">→</span>
          </button>

          <button
            v-else-if="!selectedCountry"
            v-for="item in countries"
            :key="item.id"
            class="btn-ghost justify-between text-left"
            @click="pickCountry(item.name)"
          >
            <span>🏳️ {{ item.name }}</span>
            <span class="text-slate-500">→</span>
          </button>

          <button
            v-else
            v-for="item in facilities"
            :key="item.id"
            class="btn-ghost justify-between text-left"
            @click="pickFacility(item)"
          >
            <span>🏥 {{ item.name }}</span>
            <span class="text-slate-500">→</span>
          </button>

          <p
            v-if="
              (!selectedRegion && !regions.length) ||
              (selectedRegion && !selectedCountry && !countries.length) ||
              (selectedCountry && !facilities.length)
            "
            class="rounded-xl border border-dashed border-white/15 p-4 text-center text-xs text-slate-500"
          >
            Sin datos en este nivel
          </p>
        </div>
      </div>

      <!-- Panel de detalle -->
      <div class="flex min-h-64 flex-col gap-4">
        <div v-if="facilityLoading" class="glass p-10 text-center text-sm text-slate-400">
          <span class="animate-pulse">Cargando instalación…</span>
        </div>

        <template v-else-if="facility">
          <div class="glass-strong flex flex-wrap items-start justify-between gap-3 p-5">
            <div>
              <h2 class="text-xl font-bold text-white">{{ facility.name }}</h2>
              <p class="mt-0.5 text-sm text-slate-400">
                {{ [facility.city, facility.country].filter(Boolean).join(' · ') || 'Sin ubicación' }}
              </p>
            </div>
            <span class="glass-chip">{{ facility.equipment.length }} equipos</span>
          </div>

          <div v-if="modalityGroups.length" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <div v-for="group in modalityGroups" :key="group.modality" class="glass p-4">
              <div class="flex items-center justify-between gap-2">
                <h3 class="text-sm font-semibold text-white">{{ group.modality }}</h3>
                <span class="glass-chip">×{{ group.items.length }}</span>
              </div>
              <ul class="mt-3 flex flex-col gap-2">
                <li
                  v-for="eq in group.items"
                  :key="eq.id"
                  class="flex items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2"
                >
                  <div class="min-w-0">
                    <p class="truncate text-xs text-slate-200">
                      {{ [eq.manufacturer, eq.model].filter(Boolean).join(' ') || 'Equipo sin modelo' }}
                    </p>
                    <p class="mt-0.5 text-[11px] text-slate-500">
                      {{ eq.age !== null ? `${eq.age} años` : 'Antigüedad desconocida' }} ·
                      {{ freshness(eq.updatedAt) }}
                    </p>
                  </div>
                  <StateChip :estado="eq.state" />
                </li>
              </ul>
            </div>
          </div>
          <p v-else class="glass border-dashed p-6 text-center text-sm text-slate-500">
            Esta instalación no tiene equipos registrados todavía.
          </p>

          <div class="glass p-5">
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
            Selecciona una región, un país y una instalación para ver el detalle de su equipamiento.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
