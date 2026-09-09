<script setup lang="ts">
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="glass mx-auto mt-16 max-w-md p-8 text-center">
    <div class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-rose-300/30 bg-rose-400/15 text-2xl">
      ⚠️
    </div>
    <h2 class="text-xl font-bold text-white">Servidor local no disponible</h2>
    <p class="mt-2 text-sm leading-relaxed text-slate-300">
      No se pudo contactar con la API de SynapseCME. Comprueba que el backend esté
      en marcha (<code class="rounded bg-white/10 px-1.5 py-0.5 text-xs">http://localhost:8000</code>)
      y vuelve a intentarlo.
    </p>
    <button class="btn-primary mt-5" @click="$emit('retry')">Reintentar conexión</button>
  </div>
</template>
