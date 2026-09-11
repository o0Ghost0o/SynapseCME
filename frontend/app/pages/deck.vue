<script setup lang="ts">
definePageMeta({
  layout: false,
  auth: false,
})

useHead({
  title: 'SynapseCME — Pitch Deck (Sovereign Intelligence)',
  meta: [
    {
      name: 'description',
      content:
        'Presentación interactiva de SynapseCME: Inteligencia Soberana para la Base Instalada Hospitalaria.',
    },
  ],
})

const iframeRef = ref<HTMLIFrameElement | null>(null)

onMounted(() => {
  // Enfocar el iframe para que los atajos de teclado funcionen inmediatamente
  nextTick(() => {
    iframeRef.value?.focus()
  })

  // Reenviar eventos de teclado al iframe si el foco está en el contenedor padre
  const handleKeyDown = (e: KeyboardEvent) => {
    if (
      iframeRef.value?.contentWindow &&
      document.activeElement !== iframeRef.value
    ) {
      iframeRef.value.contentWindow.dispatchEvent(
        new KeyboardEvent(e.type, {
          key: e.key,
          code: e.code,
          bubbles: true,
          cancelable: true,
        }),
      )
    }
  }

  window.addEventListener('keydown', handleKeyDown)
  onUnmounted(() => window.removeEventListener('keydown', handleKeyDown))
})
</script>

<template>
  <div class="fixed inset-0 z-50 h-screen w-screen overflow-hidden bg-[#030712]">
    <iframe
      ref="iframeRef"
      src="/deck/slides.html"
      class="h-full w-full border-0"
      allow="fullscreen; autoplay"
      title="SynapseCME Presentation Deck"
    />
  </div>
</template>
