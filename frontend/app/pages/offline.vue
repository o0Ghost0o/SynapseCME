<template>
  <div class="flex h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
    <div class="glass-strong max-w-sm p-8">
      <span class="mx-auto grid h-16 w-16 place-items-center rounded-full border border-[#f5a9a9] bg-[#fdf0f0] text-[#b42318]">
        <Icon name="wifi-off" :size="36" />
      </span>
      <h1 class="mt-4 font-display text-xl font-bold text-[#101828]">Sin conexión</h1>
      <p class="mt-2 text-sm text-[#5b6780]">
        No se puede contactar con el servidor local de SynapseCME. Comprueba que el equipo esté en marcha y
        vuelve a intentarlo.
      </p>
      <button class="btn-primary mt-6 w-full" @click="retry">Reintentar</button>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ layout: false })

function retry() {
  location.reload()
}
</script>
