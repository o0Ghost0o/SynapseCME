<script setup lang="ts">
const { request } = useApi()

const entries = ref<MetricEntry[]>([])
const loading = ref(false)
const failed = ref(false)

async function loadMetrics() {
  loading.value = true
  failed.value = false
  try {
    entries.value = normalizeMetrics(await request('/api/metrics'))
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

const stats = computed(() => {
  const totalGenerados = entries.value.reduce((acc, e) => acc + (e.generationTokens ?? 0), 0)
  return [
    { label: 'Ejecuciones', value: fmtNum(entries.value.length) },
    { label: 'TTFT medio', value: `${fmtNum(Math.round(avg(entries.value.map((e) => e.ttftMs)) ?? 0))} ms` },
    { label: 'Rendimiento medio', value: `${fmtNum(avg(entries.value.map((e) => e.tps)), 1)} tok/s` },
    { label: 'Tokens generados', value: fmtNum(totalGenerados) },
  ]
})

onMounted(loadMetrics)
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-bold text-[#101828]">Métricas del modelo</h1>
        <p class="mt-1 text-sm text-[#5b6780]">
          Rendimiento de inferencia local por ejecución: carga del modelo, tokens y latencia.
        </p>
      </div>
      <button class="btn-ghost" :disabled="loading" @click="loadMetrics">
        {{ loading ? 'Actualizando…' : 'Actualizar' }}
      </button>
    </div>

    <!-- Franja de estadísticas -->
    <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <div v-for="stat in stats" :key="stat.label" class="glass p-4">
        <p class="text-[11px] font-semibold uppercase tracking-wider text-[#7a8499]">{{ stat.label }}</p>
        <p class="mt-1 font-display text-2xl font-bold text-[#101828]">{{ stat.value }}</p>
      </div>
    </div>

    <ApiUnavailable v-if="failed" @retry="loadMetrics" />
    <div v-else-if="loading" class="glass p-10 text-center text-sm text-[#7a8499]">
      <span class="animate-pulse">Cargando métricas…</span>
    </div>

    <div v-else class="glass overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full border-collapse">
          <thead>
            <tr class="border-b border-[#e3e8f2]">
              <th class="th-cell">Modelo</th>
              <th class="th-cell">Carga (ms)</th>
              <th class="th-cell">Tokens prompt</th>
              <th class="th-cell">Tokens generados</th>
              <th class="th-cell">TTFT (ms)</th>
              <th class="th-cell">Total (ms)</th>
              <th class="th-cell">Tokens/seg</th>
              <th class="th-cell">Fecha</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(entry, i) in entries"
              :key="i"
              class="border-b border-[#eef1f7] transition hover:bg-[#f7f9fd]"
            >
              <td class="td-cell font-medium text-[#101828]">{{ entry.model }}</td>
              <td class="td-cell">{{ fmtNum(entry.modelLoadMs) }}</td>
              <td class="td-cell">{{ fmtNum(entry.promptTokens) }}</td>
              <td class="td-cell">{{ fmtNum(entry.generationTokens) }}</td>
              <td class="td-cell">{{ fmtNum(Math.round(entry.ttftMs ?? NaN) || null) }}</td>
              <td class="td-cell">{{ fmtNum(Math.round(entry.totalMs ?? NaN) || null) }}</td>
              <td class="td-cell">
                <span class="glass-chip border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]">
                  {{ fmtNum(entry.tps, 1) }}
                </span>
              </td>
              <td class="td-cell whitespace-nowrap text-[#7a8499]">{{ fmtDate(entry.createdAt) }}</td>
            </tr>
            <tr v-if="!entries.length">
              <td colspan="8" class="px-4 py-10 text-center text-sm text-[#7a8499]">
                Aún no hay ejecuciones registradas. Las métricas aparecerán tras las primeras consultas al agente.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
