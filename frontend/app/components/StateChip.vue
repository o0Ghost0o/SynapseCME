<script setup lang="ts">
const props = defineProps<{ estado?: string | null }>()

const tone = computed(() => stateTone(props.estado))
const label = computed(() => props.estado || 'Desconocido')
</script>

<template>
  <span class="glass-chip" :class="STATE_CHIP_CLASSES[tone]">
    <span class="h-1.5 w-1.5 rounded-full bg-current" />
    {{ label }}
  </span>
</template>
