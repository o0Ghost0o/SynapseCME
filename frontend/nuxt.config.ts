import tailwindcss from '@tailwindcss/vite'

export default defineNuxtConfig({
  compatibilityDate: '2025-09-01',
  ssr: false,
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  vite: {
    plugins: [tailwindcss()],
  },
  nitro: {
    // Genera .output/public/index.html para que Capacitor tenga un punto de entrada estático.
    prerender: {
      routes: ['/'],
    },
  },
  runtimeConfig: {
    public: {
      // Vacío = mismo origen (la pasarela Caddy expone /api/* y /ws/* en el puerto 3000).
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '',
      wsBase: process.env.NUXT_PUBLIC_WS_BASE || '',
    },
  },
  app: {
    head: {
      htmlAttrs: { lang: 'es' },
      title: 'SynapseCME',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
        { name: 'description', content: 'Inteligencia de base instalada de equipamiento hospitalario' },
        { name: 'theme-color', content: '#0b1023' },
      ],
      link: [{ rel: 'icon', type: 'image/svg+xml', href: '/logo.svg' }],
    },
  },
})
