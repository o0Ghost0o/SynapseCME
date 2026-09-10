<template>
  <div class="flex h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
    <div class="glass-strong max-w-sm p-8">
      <p class="text-5xl">📡</p>
      <h1 class="mt-4 text-xl font-bold text-white">Sin conexión</h1>
      <p class="mt-2 text-sm text-slate-400">
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
