import tailwindcss from '@tailwindcss/vite'

export default defineNuxtConfig({
  compatibilityDate: '2025-09-01',
  ssr: false,
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  modules: ['@vite-pwa/nuxt'],
  vite: {
    plugins: [tailwindcss()],
  },
  postcss: {
    plugins: {
      // cssnano 8 requiere Node 22+ (Set methods ES2025); la minificación la
      // hace Vite con esbuild, cssnano solo duplica el paso.
      cssnano: false,
    },
  },
  pwa: {
    strategies: 'generateSW',
    registerType: 'autoUpdate',
    manifest: {
      name: 'SynapseCME',
      short_name: 'SynapseCME',
      lang: 'es',
      description: 'Inteligencia de base instalada de equipamiento hospitalario',
      display: 'standalone',
      orientation: 'portrait',
      theme_color: '#f4f6fb',
      background_color: '#f4f6fb',
      start_url: '/',
      scope: '/',
      id: '/',
      icons: [
        {
          src: '/icons/icon-192.png',
          sizes: '192x192',
          type: 'image/png',
          purpose: 'any',
        },
        {
          src: '/icons/icon-512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'any',
        },
        {
          src: '/icons/icon-maskable-512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'maskable',
        },
      ],
    },
    workbox: {
      navigateFallback: '/offline',
      globPatterns: ['**/*.{js,css,html,svg,png,webmanifest}'],
      runtimeCaching: [
        {
          // Nunca cachear el backend: /api/* y /ws/* siempre van a red.
          urlPattern: /^.*\/(api|ws)\/.*/,
          handler: 'NetworkOnly',
        },
      ],
    },
    client: {
      installPrompt: true,
    },
    devOptions: {
      // Registra el service worker también en `nuxi dev` (sin esto la PWA
      // solo existe en build de producción).
      enabled: true,
      navigateFallback: '/offline',
      suppressWarnings: true,
    },
  },
  nitro: {
    // Genera .output/public/index.html para que Capacitor tenga un punto de entrada estático.
    prerender: {
      routes: ['/', '/offline', '/deck'],
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
        { name: 'theme-color', content: '#f4f6fb' },
        { name: 'mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-status-bar-style', content: 'black-translucent' },
        { name: 'apple-mobile-web-app-title', content: 'SynapseCME' },
      ],
      link: [
        { rel: 'manifest', href: '/manifest.webmanifest' },
        { rel: 'icon', type: 'image/svg+xml', href: '/logo.svg' },
        { rel: 'apple-touch-icon', href: '/icons/icon-192.png' },
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        {
          rel: 'stylesheet',
          href: 'https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap',
        },
      ],
    },
  },
})
