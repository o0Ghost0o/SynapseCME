<script setup lang="ts">
interface FollowUp {
  icon: string
  title: string
  summary: string
  details: string[]
  tags: string[]
}

const howItWorks = [
  {
    title: 'Captura en campo',
    text: 'El ingeniero dicta o escribe en español libre: "Visité el Hospital Aurora en Panamá, vi 3 resonancias y 2 tomógrafos, una RM tiene como 8 años". También por voz, con dictado STT on-edge.',
  },
  {
    title: 'Extracción con LLM local',
    text: 'MedPsy (Q4_K_M, vía QVAC) extrae entidades con salida estructurada. Si el nodo de inferencia no responde, un extractor determinista en español mantiene la app operativa.',
  },
  {
    title: 'GraphRAG: el grafo muta',
    text: 'La extracción se traduce en mutaciones del grafo (MERGE de la jerarquía región → país → ciudad → instalación → equipo), con detección de duplicados.',
  },
  {
    title: 'Consenso ponderado',
    text: 'Las observaciones de distintos observadores se ponderan para promover estados: Desconocido → Estimado → Reportado → Confirmado. Cada mutación queda en el registro de transacciones.',
  },
  {
    title: 'Lectura en tiempo real',
    text: 'Panel 360 (agregado ejecutivo), Red en vivo (grafo interactivo con clientes conectados) y Métricas de rendimiento del modelo, todo por WebSocket y REST.',
  },
]

const stack = [
  { icon: 'phone', title: 'Cliente — Nuxt 4 (PWA / Capacitor)', text: 'Captura, Panel 360, Red viva y Métricas; instalable como app y con modo offline.' },
  { icon: 'settings', title: 'Backend — FastAPI', text: 'Agente GraphRAG con tool calling, autenticación JWT + refresh rotativo (RBAC) y canal WS de eventos.' },
  { icon: 'sparkles', title: 'Inferencia — QVAC (Tether)', text: 'MedPsy Q4_K_M (~4.5 GB) + EmbeddingGemma multilingüe sobre RTX; servidor OpenAI-compatible, cero nube.' },
  { icon: 'database', title: 'Datos — Neo4j + PostgreSQL', text: 'Grafo de la red instalada y estado operativo con log inmutable de transacciones.' },
  { icon: 'mic', title: 'Voz — speaches / faster-whisper', text: 'Transcripción en CPU a propósito: la GPU se reserva para el modelo de chat.' },
  { icon: 'shield', title: 'Gateway — Caddy único punto público', text: 'Un solo origen para app, /api/* y /ws/*; Neo4j, Postgres y QVAC son internos.' },
]

const value = [
  { icon: 'clipboard', title: 'Inventario vivo sin formularios', text: 'El parque instalado se actualiza hablando, no rellenando campos: la fricción de la captura desaparece.' },
  { icon: 'check', title: 'Confianza por consenso', text: 'Cada dato gana fiabilidad a medida que distintos observadores lo confirman; nada se presenta como hecho sin respaldo.' },
  { icon: 'refresh', title: 'Oportunidades de renovación', text: 'Antigüedad, modalidades y estado por instalación hacen visible dónde hay ciclo de renovación tecnológica.' },
  { icon: 'lock', title: 'Soberanía de los datos', text: 'Hospital e instalaciones conservan sus datos en su propio hardware; nada sale a APIs de terceros.' },
  { icon: 'trending-up', title: 'Coste de despliegue mínimo', text: 'Una RTX 3060 Ti (8 GB) aloja todo el stack; corre igual en CPU para desarrollo.' },
  { icon: 'globe', title: 'Red de pares', text: 'Los nodos pueden sincronizar observaciones entre sí (SYNC_PEERS): cada sede ve la red completa sin centralizarla.' },
]

const followUps: FollowUp[] = [
  {
    icon: 'camera',
    title: 'Captura de evidencia fotográfica',
    summary: 'Adjuntar fotos a las observaciones de campo como respaldo verificable del estado del equipo.',
    details: [
      'Fotos adjuntas a cada observación, con compresión y límite de tamaño',
      'Miniaturas en el detalle de equipo y en el expediente de la instalación',
      'Sincronización diferida para captura sin conexión (PWA)',
    ],
    tags: ['captura', 'offline', 'evidencia'],
  },
  {
    icon: 'users',
    title: 'Jerarquía de roles y revisiones',
    summary: 'Cadena de supervisión: el capturador registra, el supervisor revisa y aprueba antes de publicar.',
    details: [
      'Nuevos roles: supervisor y revisor sobre el flujo actual (admin / capturador / visor)',
      'Cola de pendientes de revisión con aprobar, corregir o rechazar',
      'Historial de quién aprobó cada observación (trazabilidad completa)',
    ],
    tags: ['roles', 'aprobación', 'trazabilidad'],
  },
  {
    icon: 'edit',
    title: 'Firma de clientes en actas',
    summary: 'Firma digital del responsable de la instalación al tomar o entregar un equipo (take-off / handover).',
    details: [
      'Lienzo de firma en pantalla desde la propia PWA, sin papel',
      'Acta generada con fecha, equipo, observaciones y firma incrustada',
      'Registro inmutable del acta vinculado al nodo del grafo',
    ],
    tags: ['firma', 'actas', 'take-off'],
  },
  {
    icon: 'file',
    title: 'Generación de informes',
    summary: 'Informes exportables del parque instalado por instalación, red o período, listos para compartir.',
    details: [
      'Plantillas: estado general, incidencias, vida útil de tubos y sondas',
      'Exportación a PDF y CSV con el logo y datos de la organización',
      'Informes programados (semanal/mensual) enviados por correo o descarga',
    ],
    tags: ['pdf', 'csv', 'exportación'],
  },
  {
    icon: 'activity',
    title: 'Analítica profunda y clustering',
    summary: 'Descubrir patrones ocultos en el grafo: agrupar instalaciones similares y detectar anomalías.',
    details: [
      'Clustering de instalaciones por perfil de equipamiento y patrones de incidencia',
      'Detección de anomalías: comportamientos atípicos frente a instalaciones comparables',
      'Embeddings de observaciones ya disponibles: base para búsqueda semántica y recomendaciones',
    ],
    tags: ['clustering', 'anomalías', 'embeddings'],
  },
]
</script>

<template>
  <div class="flex flex-col gap-4">
    <div>
      <h1 class="font-display text-2xl font-bold text-[#101828]">Documentación</h1>
      <p class="mt-1 text-sm text-[#5b6780]">
        Qué es SynapseCME, cómo funciona, en qué se sostiene y hacia dónde evoluciona.
      </p>
    </div>

    <!-- Qué es este proyecto -->
    <div class="glass p-4 sm:p-5">
      <h2 class="font-display text-sm font-semibold text-[#101828]">¿Qué es este proyecto?</h2>
      <p class="mt-2 text-xs leading-relaxed text-[#5b6780]">
        SynapseCME es una plataforma descentralizada, <em>agent-first</em>, que convierte observaciones de
        campo no estructuradas sobre equipamiento hospitalario —dictadas o escritas en español por ingenieros
        e instalaciones— en una base de datos <strong class="text-[#101828]">GraphRAG</strong> viva, estructurada y
        confiable. Toda la inferencia corre <strong class="text-[#101828]">on-edge</strong> con QVAC sobre hardware
        local NVIDIA RTX: cero APIs de nube y privacidad absoluta de los datos.
      </p>
      <div class="mt-3 flex flex-wrap gap-1.5">
        <span v-for="p in ['Descentralizada', 'Agent-first', 'GraphRAG', 'On-edge', 'Privacidad total']" :key="p" class="glass-chip text-[10px]">
          {{ p }}
        </span>
      </div>
    </div>

    <!-- Cómo funciona -->
    <div class="glass p-4 sm:p-5">
      <h2 class="font-display text-sm font-semibold text-[#101828]">¿Cómo funciona?</h2>
      <ol class="mt-3 flex flex-col gap-3">
        <li v-for="(step, i) in howItWorks" :key="step.title" class="flex items-start gap-3">
          <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#eaf3fe] text-xs font-bold text-[#1d63d8]">
            {{ i + 1 }}
          </span>
          <div class="min-w-0">
            <p class="text-xs font-semibold text-[#101828]">{{ step.title }}</p>
            <p class="mt-0.5 text-xs leading-relaxed text-[#5b6780]">{{ step.text }}</p>
          </div>
        </li>
      </ol>
    </div>

    <!-- En qué se sostiene -->
    <div class="glass p-4 sm:p-5">
      <h2 class="font-display text-sm font-semibold text-[#101828]">En qué se sostiene</h2>
      <p class="mt-1 text-xs text-[#7a8499]">
        Stack 100 % local: un único gateway público y todos los servicios internos en la misma red.
      </p>
      <div class="mt-3 grid gap-2 sm:grid-cols-2">
        <div v-for="s in stack" :key="s.title" class="flex items-start gap-2.5 rounded-xl border border-[#e9edf5] bg-[#f7f9fd] px-3 py-2.5">
          <Icon :name="s.icon" :size="18" class="mt-0.5 shrink-0 text-[#1d63d8]" />
          <div class="min-w-0">
            <p class="text-xs font-semibold text-[#101828]">{{ s.title }}</p>
            <p class="mt-0.5 text-[11px] leading-relaxed text-[#5b6780]">{{ s.text }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Valor del producto -->
    <div class="glass p-4 sm:p-5">
      <h2 class="font-display text-sm font-semibold text-[#101828]">Valor del producto</h2>
      <ul class="mt-3 grid gap-2 md:grid-cols-2">
        <li v-for="v in value" :key="v.title" class="rounded-xl border border-[#e9edf5] bg-[#f7f9fd] px-3 py-2.5">
          <p class="flex items-center gap-1.5 text-xs font-semibold text-[#101828]">
            <Icon :name="v.icon" :size="15" class="shrink-0 text-[#1d63d8]" />
            {{ v.title }}
          </p>
          <p class="mt-0.5 text-[11px] leading-relaxed text-[#5b6780]">{{ v.text }}</p>
        </li>
      </ul>
    </div>

    <!-- Follow-ups: mejoras propuestas -->
    <div class="glass p-4 sm:p-5">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="font-display text-sm font-semibold text-[#101828]">Follow-ups · Seguimientos propuestos</h2>
        <span class="glass-chip text-[11px]">{{ followUps.length }} propuestas</span>
      </div>
      <p class="mt-1 text-xs text-[#7a8499]">
        Ideas evaluadas para futuras iteraciones. Aún no están implementadas; el orden no implica prioridad.
      </p>

      <ul class="mt-4 grid gap-3 md:grid-cols-2">
        <li v-for="fu in followUps" :key="fu.title" class="rounded-2xl border border-[#e9edf5] bg-[#f7f9fd] p-4">
          <div class="flex items-start gap-3">
            <span class="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]">
              <Icon :name="fu.icon" :size="18" />
            </span>
            <div class="min-w-0">
              <p class="text-sm font-semibold text-[#101828]">{{ fu.title }}</p>
              <p class="mt-1 text-xs leading-relaxed text-[#5b6780]">{{ fu.summary }}</p>
            </div>
          </div>
          <ul class="mt-3 flex flex-col gap-1.5">
            <li v-for="d in fu.details" :key="d" class="flex items-start gap-1.5 text-xs text-[#5b6780]">
              <span class="mt-1 h-1 w-1 shrink-0 rounded-full bg-[#1d63d8]" />
              {{ d }}
            </li>
          </ul>
          <div class="mt-3 flex flex-wrap gap-1.5">
            <span v-for="t in fu.tags" :key="t" class="glass-chip text-[10px]">{{ t }}</span>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>
