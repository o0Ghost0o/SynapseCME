<script setup lang="ts">
import { EXAMPLE_CATEGORIES, type ExampleItem } from '~/utils/examples'

const open = defineModel<boolean>({ required: true })

const emit = defineEmits<{
  pick: [example: ExampleItem]
}>()

const activeCategory = ref<string>('all')

const categories = computed(() => [{ id: 'all', label: 'Todos', icon: '✨' }, ...EXAMPLE_CATEGORIES])

const visible = computed(() =>
  activeCategory.value === 'all'
    ? EXAMPLE_CATEGORIES.flatMap((c) => c.examples)
    : EXAMPLE_CATEGORIES.find((c) => c.id === activeCategory.value)?.examples ?? [],
)

function pick(example: ExampleItem) {
  open.value = false
  emit('pick', example)
}

// Cerrar con Escape
onMounted(() => {
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') open.value = false
  }
  window.addEventListener('keydown', onKey)
  onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
})
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="open" class="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
        <div class="absolute inset-0 bg-slate-950/70 backdrop-blur-sm" @click="open = false" />

        <!-- Móvil: bottom sheet casi completo · Desktop: dialog centrado -->
        <div
          class="glass-strong relative flex max-h-[92dvh] w-full flex-col rounded-b-none rounded-t-3xl p-5 sm:max-h-[80dvh] sm:max-w-2xl sm:rounded-3xl"
          role="dialog"
          aria-modal="true"
          aria-label="Ejemplos de captura"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <h2 class="text-lg font-bold text-white">Ejemplos de captura</h2>
              <p class="mt-0.5 text-xs text-slate-400">
                Toca un ejemplo para pegarlo en la captura; no se envía hasta que decidas.
              </p>
            </div>
            <button class="btn-ghost shrink-0 px-3 py-1.5 text-xs" @click="open = false">Cerrar ✕</button>
          </div>

          <div class="mt-4 flex gap-2 overflow-x-auto pb-1">
            <button
              v-for="cat in categories"
              :key="cat.id"
              class="glass-chip shrink-0 py-1.5 transition"
              :class="activeCategory === cat.id ? 'border-indigo-300/40 bg-indigo-400/20 text-indigo-100' : 'text-slate-300'"
              @click="activeCategory = cat.id"
            >
              <span>{{ cat.icon }}</span> {{ cat.label }}
            </button>
          </div>

          <div class="mt-3 flex-1 overflow-y-auto pr-1">
            <ul class="flex flex-col gap-2.5">
              <li v-for="example in visible" :key="example.id">
                <button
                  class="glass w-full px-4 py-3 text-left transition hover:border-indigo-300/30 hover:bg-white/15 active:scale-[0.99]"
                  @click="pick(example)"
                >
                  <p class="text-xs font-semibold uppercase tracking-wider text-indigo-300">{{ example.label }}</p>
                  <p class="mt-1 text-sm leading-relaxed text-slate-200">{{ example.text }}</p>
                </button>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
