<script setup lang="ts">
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="glass-strong mx-auto mt-16 max-w-md p-8 text-center">
    <div class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl border border-[#f5a9a9] bg-[#fdf0f0] text-[#b42318]">
      <Icon name="wifi-off" :size="24" />
    </div>
    <h2 class="text-xl font-bold text-[#101828]">Servidor local no disponible</h2>
    <p class="mt-2 text-sm leading-relaxed text-[#5b6780]">
      No se pudo contactar con la API de SynapseCME. Comprueba que la pasarela y el
      backend estén en marcha en este mismo origen y vuelve a intentarlo.
    </p>
    <button class="btn-primary mt-5" @click="$emit('retry')">Reintentar conexión</button>
  </div>
</template>
