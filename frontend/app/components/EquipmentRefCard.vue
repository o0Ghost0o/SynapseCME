<script setup lang="ts">
export interface EquipmentRef {
  id: string
  modality?: string | null
  manufacturer?: string | null
  model?: string | null
  state?: string | null
  facility_name?: string | null
  country?: string | null
  age_years?: number | null
  has_issue?: boolean
  issues?: string[]
}

const props = defineProps<{ eq: EquipmentRef }>()

const title = computed(
  () => [props.eq.manufacturer, props.eq.model].filter(Boolean).join(' ') || 'Equipo sin modelo',
)

const location = computed(() => [props.eq.facility_name, props.eq.country].filter(Boolean).join(' · '))
</script>

<template>
  <NuxtLink
    :to="`/equipos/${encodeURIComponent(eq.id)}`"
    data-testid="assistant-equipment-card"
    class="glass block rounded-xl px-3 py-2.5 transition hover:border-[#c4ddfb] hover:bg-[#f4f8fe]"
  >
    <div class="flex items-center justify-between gap-2">
      <p class="min-w-0 truncate text-sm font-semibold text-[#101828]">{{ title }}</p>
      <span v-if="eq.modality" class="glass-chip shrink-0 text-[11px]">{{ eq.modality }}</span>
    </div>
    <p v-if="location" class="mt-0.5 flex items-center gap-1 truncate text-[11px] text-[#7a8499]">
      <Icon name="hospital" :size="11" />{{ location }}
    </p>
    <div class="mt-1.5 flex flex-wrap items-center gap-1.5">
      <StateChip v-if="eq.state" :estado="eq.state" />
      <span v-if="eq.age_years !== null && eq.age_years !== undefined" class="glass-chip text-[11px]">
        {{ eq.age_years }} años
      </span>
      <span
        v-if="eq.has_issue"
        class="glass-chip border-[#f5a9a9] bg-[#fdf0f0] text-[11px] text-[#b42318]"
      >
        <Icon name="alert" :size="11" />requiere atención
      </span>
    </div>
    <ul v-if="eq.issues?.length" class="mt-1.5 flex flex-col gap-0.5">
      <li v-for="(issue, i) in eq.issues" :key="i" class="truncate text-[11px] text-[#d99a00]">
        · {{ issue }}
      </li>
    </ul>
  </NuxtLink>
</template>
