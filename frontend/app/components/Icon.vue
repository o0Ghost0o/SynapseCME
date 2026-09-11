<script setup lang="ts">
import { ICONS } from '~/utils/icons'

const props = withDefaults(
  defineProps<{ name: string; size?: number | string }>(),
  { size: 16 },
)
const markup = computed(() => ICONS[props.name] ?? ICONS.alert)
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    v-html="markup"
  />
</template>
