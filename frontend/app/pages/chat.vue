<script setup lang="ts">
import { useToast } from '~/composables/useToast'
import type { ExampleItem } from '~/utils/examples'

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  extraction: Record<string, unknown> | null
  followup: string | null
  done: boolean
  error?: boolean
}

const { fetchWithAuth } = useApi()
const { show } = useToast()
const { apiOnline, refresh } = useConnection()
const { ensure } = useEvents()
const { user } = useAuth()

onMounted(() => {
  ensure({ client_type: 'field_app', name: 'App de campo SynapseCME' })
})

const input = ref('')
const sending = ref(false)
const messages = ref<ChatMessage[]>([])
const listEl = ref<HTMLElement | null>(null)

// —— Dictado (STT) ——
const captureEl = ref<HTMLTextAreaElement | null>(null)
const dictating = ref(false)
const transcribing = ref(false)
const recordSecs = ref(0)
const micModal = ref<'priming' | 'denied' | null>(null)
const examplesOpen = ref(false)
let mediaRecorder: MediaRecorder | null = null
let recorderMime = ''
let recordChunks: Blob[] = []
let recordTimer: ReturnType<typeof setTimeout> | undefined
let recordInterval: ReturnType<typeof setInterval> | undefined
let recordCancelled = false
let activeStream: MediaStream | null = null
const MAX_RECORDING_MS = 60000
const MIC_PRIMED_KEY = 'synapse-mic-primed'

// Orden de preferencia: opus en Chrome/Android, mp4 en iOS/Safari, aac residual.
const RECORDER_MIMES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/aac']

function pickRecorderMime(): string | null {
  if (typeof MediaRecorder === 'undefined') return null
  for (const mime of RECORDER_MIMES) {
    try {
      if (MediaRecorder.isTypeSupported(mime)) return mime
    } catch {
      // isTypeSupported no disponible en este navegador
    }
  }
  return null
}

function recorderExtension(): string {
  if (recorderMime.includes('mp4')) return 'm4a'
  if (recorderMime.includes('aac')) return 'aac'
  return 'webm'
}

async function micPermissionState(): Promise<PermissionState | 'unsupported'> {
  try {
    const status = await navigator.permissions.query({ name: 'microphone' as PermissionName })
    return status.state
  } catch {
    return 'unsupported'
  }
}

async function toggleDictation() {
  if (dictating.value) {
    mediaRecorder?.stop()
    return
  }
  if (transcribing.value) return
  const state = await micPermissionState()
  if (state === 'denied') {
    micModal.value = 'denied'
    return
  }
  const primed = localStorage.getItem(MIC_PRIMED_KEY) === '1'
  if (!primed && state !== 'granted') {
    micModal.value = 'priming'
    return
  }
  await startRecording()
}

function allowMicrophone() {
  localStorage.setItem(MIC_PRIMED_KEY, '1')
  micModal.value = null
  void startRecording()
}

async function startRecording() {
  const mime = pickRecorderMime()
  if (mime === null) {
    show('Tu navegador no soporta grabación de audio; escribe la observación a mano.')
    return
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    activeStream = stream
    recordChunks = []
    recordCancelled = false
    mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
    recorderMime = mediaRecorder.mimeType || mime || 'audio/webm'
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size) recordChunks.push(e.data)
    }
    mediaRecorder.onstop = () => {
      clearTimeout(recordTimer)
      clearInterval(recordInterval)
      activeStream?.getTracks().forEach((t) => t.stop())
      activeStream = null
      dictating.value = false
      if (!recordCancelled) void uploadRecording()
    }
    recordSecs.value = 0
    mediaRecorder.start()
    dictating.value = true
    recordInterval = setInterval(() => recordSecs.value++, 1000)
    recordTimer = setTimeout(() => mediaRecorder?.stop(), MAX_RECORDING_MS)
  } catch (err) {
    dictating.value = false
    handleMicError(err)
  }
}

function cancelRecording() {
  recordCancelled = true
  mediaRecorder?.stop()
  show('Dictado cancelado')
}

function handleMicError(err: unknown) {
  const name = (err as DOMException | null)?.name ?? ''
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') {
    micModal.value = 'denied'
  } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    show('No se encontró micrófono en este dispositivo')
  } else if (name === 'NotReadableError' || name === 'TrackStartError') {
    show('El micrófono está en uso por otra aplicación')
  } else {
    show('No se pudo iniciar el micrófono. Inténtalo de nuevo.')
  }
}

const recordTimeLabel = computed(() => {
  const m = Math.floor(recordSecs.value / 60)
  const s = (recordSecs.value % 60).toFixed(0).padStart(2, '0')
  return `${m}:${s}`
})

async function uploadRecording() {
  if (!recordChunks.length) return
  const blob = new Blob(recordChunks, { type: recorderMime })
  transcribing.value = true
  try {
    const form = new FormData()
    form.append('file', blob, `dictation.${recorderExtension()}`)
    const res = await fetchWithAuth('/api/stt', { method: 'POST', body: form })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = (await res.json()) as { text?: string }
    const text = typeof data.text === 'string' ? data.text.trim() : ''
    if (!text) {
      show('No se entendió el audio, intenta de nuevo')
    } else {
      input.value = input.value.trim() ? `${input.value.trim()} ${text}` : text
      nextTick(() => captureEl.value?.focus())
    }
  } catch {
    show('El servicio de dictado (STT) no está disponible')
  } finally {
    transcribing.value = false
  }
}

function applyExample(example: ExampleItem) {
  input.value = example.text
  nextTick(() => captureEl.value?.focus())
  show('Ejemplo pegado en la captura')
}

const FIELD_DEFS: Array<{ key: string; label: string; aliases: string[] }> = [
  { key: 'instalacion', label: 'Instalación', aliases: ['instalacion', 'installation', 'facility', 'hospital', 'site'] },
  { key: 'ciudad', label: 'Ciudad', aliases: ['ciudad', 'city', 'town'] },
  { key: 'pais', label: 'País', aliases: ['pais', 'country', 'nacion'] },
  { key: 'modalidad', label: 'Modalidad', aliases: ['modalidad', 'modality', 'type'] },
  { key: 'cantidad', label: 'Cantidad', aliases: ['cantidad', 'quantity', 'count', 'units'] },
  { key: 'fabricante', label: 'Fabricante', aliases: ['fabricante', 'manufacturer', 'vendor', 'make'] },
  { key: 'modelo', label: 'Modelo', aliases: ['modelo', 'model'] },
  { key: 'antiguedad', label: 'Antigüedad', aliases: ['antiguedad', 'age', 'age_years', 'years'] },
  { key: 'confianza', label: 'Confianza', aliases: ['confianza', 'confidence', 'score'] },
  { key: 'estado', label: 'Estado', aliases: ['estado', 'state', 'status'] },
]

function normKey(k: string): string {
  return k.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}

// El backend envía el ExtractionResult anidado de Pydantic
// ({facility, city, country, items: [{modality, quantity, ...}]}), mientras
// que el LLM puede devolver un dict plano con claves en español. Se normaliza
// a un dict plano con las claves primarias de FIELD_DEFS.
function normalizeExtraction(raw: Record<string, unknown>): Record<string, unknown> {
  const flat: Record<string, unknown> = { ...raw }
  if (raw.facility !== undefined && flat.instalacion === undefined) flat.instalacion = raw.facility
  if (raw.city !== undefined && flat.ciudad === undefined) flat.ciudad = raw.city
  if (raw.country !== undefined && flat.pais === undefined) flat.pais = raw.country
  if (raw.confidence !== undefined && flat.confianza === undefined) flat.confianza = raw.confidence
  const items = (Array.isArray(raw.items) ? raw.items : []).filter(
    (i): i is Record<string, unknown> => !!i && typeof i === 'object',
  )
  if (items.length) {
    const first = items[0]
    if (flat.modalidad === undefined) {
      const mods = [...new Set(items.map((i) => i.modality).filter(Boolean))]
      flat.modalidad = mods.join(', ')
    }
    if (flat.cantidad === undefined) {
      const total = items.reduce((n, i) => n + (typeof i.quantity === 'number' ? i.quantity : 0), 0)
      if (total > 0) flat.cantidad = total
    }
    if (flat.fabricante === undefined) flat.fabricante = first.manufacturer
    if (flat.modelo === undefined) flat.modelo = first.model
    if (flat.antiguedad === undefined) flat.antiguedad = first.age_years
  }
  return flat
}

function fieldValue(extraction: Record<string, unknown>, def: (typeof FIELD_DEFS)[number]): unknown {
  const entries = Object.entries(extraction)
  for (const alias of def.aliases) {
    const hit = entries.find(([k]) => normKey(k) === alias)
    if (hit) return hit[1]
  }
  for (const alias of def.aliases) {
    const hit = entries.find(([k]) => normKey(k).includes(alias))
    if (hit) return hit[1]
  }
  return undefined
}

function displayValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (key === 'confianza' && typeof value === 'number') {
    const pct = value <= 1 ? value * 100 : value
    return `${pct.toFixed(0)} %`
  }
  if (key === 'antiguedad' && typeof value === 'number') {
    return `${value % 1 === 0 ? value.toFixed(0) : value.toFixed(1)} años`
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function confidencePct(extraction: Record<string, unknown>): number | null {
  const v = fieldValue(extraction, FIELD_DEFS[8])
  if (typeof v !== 'number') return null
  return Math.min(v <= 1 ? v * 100 : v, 100)
}

function estadoValue(extraction: Record<string, unknown>): string {
  return displayValue('estado', fieldValue(extraction, FIELD_DEFS[9]))
}

function handleEvent(msg: ChatMessage, event: Record<string, unknown>) {
  switch (event.type) {
    case 'token': {
      const t = typeof event.text === 'string' ? event.text : ''
      // Defensa en profundidad: el JSON crudo de extracción nunca debe
      // renderizarse como burbuja de texto del agente.
      if (!msg.text.trim() && t.trimStart().startsWith('{')) break
      msg.text += t
      scrollDown()
      break
    }
    case 'extraction':
      msg.extraction = normalizeExtraction((event.data ?? event.extraction ?? {}) as Record<string, unknown>)
      break
    case 'followup':
      msg.followup = typeof event.question === 'string' ? event.question : String(event.question ?? '')
      break
    case 'done':
      msg.done = true
      show('Registro guardado en el grafo')
      break
  }
}

function scrollDown() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  input.value = ''
  messages.value.push({ role: 'user', text, extraction: null, followup: null, done: true })
  const msg = reactive<ChatMessage>({ role: 'assistant', text: '', extraction: null, followup: null, done: false })
  messages.value.push(msg)
  sending.value = true
  scrollDown()
  try {
    const res = await fetchWithAuth('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        client_type: 'field_app',
      }),
    })
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx: number
      while ((idx = buffer.indexOf('\n\n')) >= 0) {
        const rawEvent = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        for (const line of rawEvent.split('\n')) {
          if (!line.startsWith('data:')) continue
          const payload = line.slice(5).trim()
          if (!payload) continue
          try {
            handleEvent(msg, JSON.parse(payload))
          } catch {
            // línea de mantenimiento del stream: se ignora
          }
        }
      }
    }
    msg.done = true
  } catch {
    msg.error = true
    msg.text = msg.text || 'No se pudo contactar con el agente. Comprueba que el servidor local esté en marcha.'
  } finally {
    sending.value = false
    scrollDown()
  }
}

function applyFollowup(question: string) {
  input.value = question
}

const confirmed = reactive<Record<number, boolean>>({})
</script>

<template>
  <div class="flex h-[calc(100dvh-11rem)] flex-col gap-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold text-white">Captura agent-first</h1>
        <p class="mt-1 text-sm text-slate-400">
          Describe en lenguaje natural el equipamiento instalado; el agente extrae la estructura al grafo.
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <span v-if="user" class="glass-chip border-emerald-300/30 bg-emerald-400/15 text-emerald-200">
          ✍️ Capturando como {{ user.full_name || user.username }}
        </span>
        <span class="glass-chip border-indigo-300/30 bg-indigo-400/15 text-indigo-200">
          <span>💬</span> Preguntá o dictá una observación
        </span>
      </div>
    </div>

    <div
      v-if="apiOnline === false"
      class="glass flex flex-wrap items-center justify-between gap-3 border-rose-300/25 bg-rose-400/10 px-4 py-3"
    >
      <p class="text-sm text-rose-200">
        ⚠️ Servidor local no disponible. Los mensajes no podrán procesarse hasta que el backend responda.
      </p>
      <button class="btn-ghost" @click="refresh()">Reintentar</button>
    </div>

    <div ref="listEl" class="glass flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
      <div v-if="!messages.length" class="m-auto max-w-sm text-center text-sm text-slate-400">
        <p class="text-4xl">🎙️</p>
        <p class="mt-3">
          Ejemplo: «En el Hospital General de Valencia hay 2 resonancias Siemens MAGNETOM Vida de 9 años, modalidad
          confirmada».
        </p>
      </div>

      <template v-for="(msg, i) in messages" :key="i">
        <div v-if="msg.role === 'user'" class="ml-auto max-w-[80%] rounded-2xl rounded-br-md border border-indigo-300/25 bg-indigo-500/25 px-4 py-2.5 text-sm text-indigo-50 backdrop-blur-xl">
          {{ msg.text }}
        </div>

        <div v-else class="mr-auto w-full max-w-[92%]">
          <div
            class="rounded-2xl rounded-bl-md border px-4 py-2.5 text-sm backdrop-blur-xl"
            :class="msg.error ? 'border-rose-300/25 bg-rose-400/10 text-rose-200' : 'border-white/15 bg-white/10 text-slate-100'"
          >
            <span v-if="msg.text">{{ msg.text }}</span>
            <span v-else-if="!msg.done" class="animate-pulse text-slate-400">El agente está procesando…</span>
            <span v-if="sending && i === messages.length - 1 && !msg.text" class="animate-pulse">▌</span>
          </div>

          <div v-if="msg.followup" class="glass-strong mt-3 flex flex-wrap items-center justify-between gap-3 border-amber-300/25 bg-amber-400/10 px-4 py-3">
            <p class="text-sm text-amber-100">
              <span class="font-semibold">Pregunta de seguimiento:</span> {{ msg.followup }}
            </p>
            <button class="btn-ghost shrink-0" @click="applyFollowup(msg.followup)">Responder</button>
          </div>

          <div v-if="msg.extraction && Object.keys(msg.extraction).length" class="glass-strong mt-3 p-4">
            <div class="flex items-center justify-between gap-2">
              <h3 class="text-sm font-semibold text-white">Extracción estructurada</h3>
              <StateChip :estado="estadoValue(msg.extraction)" />
            </div>
            <dl class="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5 sm:grid-cols-3">
              <template v-for="def in FIELD_DEFS" :key="def.key">
                <div v-if="fieldValue(msg.extraction, def) !== undefined">
                  <dt class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{{ def.label }}</dt>
                  <dd class="mt-0.5 text-sm text-slate-100">{{ displayValue(def.key, fieldValue(msg.extraction, def)) }}</dd>
                </div>
              </template>
            </dl>
            <div v-if="confidencePct(msg.extraction) !== null" class="mt-3">
              <div class="flex justify-between text-[11px] text-slate-400">
                <span>Confianza</span><span>{{ confidencePct(msg.extraction)!.toFixed(0) }} %</span>
              </div>
              <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div
                  class="h-full rounded-full bg-gradient-to-r from-indigo-400 to-emerald-400 transition-all"
                  :style="{ width: `${confidencePct(msg.extraction)}%` }"
                />
              </div>
            </div>
            <div class="mt-4 flex justify-end">
              <button
                class="btn-primary"
                :disabled="confirmed[i]"
                @click="confirmed[i] = true; show('Registro confirmado')"
              >
                {{ confirmed[i] ? '✓ Confirmado' : 'Confirmar registro' }}
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>

    <div class="glass p-4 pb-[max(env(safe-area-inset-bottom),env(keyboard-inset-bottom,0px))]">
      <label for="capture" class="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-400">
        Captura rápida
      </label>
      <textarea
        id="capture"
        ref="captureEl"
        v-model="input"
        rows="4"
        class="glass-input resize-none text-base leading-relaxed"
        placeholder="Dicta o escribe lo observado en campo: instalación, ciudad, modalidad, cantidad, fabricante, modelo, antigüedad…"
        :disabled="sending"
        @keydown.enter.exact.prevent="send"
      />
      <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <button class="btn-ghost" :disabled="dictating || transcribing" @click="examplesOpen = true">
            💡 Ejemplos
          </button>
          <button
            class="btn-ghost"
            :class="dictating ? 'border-rose-300/40 bg-rose-400/20 text-rose-200' : ''"
            :disabled="transcribing"
            :title="dictating ? 'Detener dictado' : 'Dictar con el micrófono'"
            @click="toggleDictation"
          >
            <span :class="dictating ? 'animate-pulse' : ''">{{ dictating ? '■' : '🎙️' }}</span>
            {{ dictating ? 'Escuchando…' : transcribing ? 'Transcribiendo…' : 'Dictar' }}
          </button>
          <span v-if="dictating" class="glass-chip border-rose-300/40 bg-rose-400/15 font-mono text-rose-200">
            ⏱ {{ recordTimeLabel }}
          </span>
          <button v-if="dictating" class="btn-ghost px-3 py-1.5 text-xs" @click="cancelRecording">Cancelar</button>
          <p v-else-if="!transcribing" class="hidden text-xs text-slate-500 sm:block">
            Toca Dictar para grabar una observación
          </p>
        </div>
        <p class="hidden text-xs text-slate-500 lg:block">Enter para enviar · Mayús+Enter para salto de línea</p>
        <button class="btn-primary min-w-36" :disabled="sending || !input.trim()" @click="send">
          {{ sending ? 'Procesando…' : 'Enviar al agente' }}
        </button>
      </div>
    </div>

    <ExamplesDialog v-model="examplesOpen" @pick="applyExample" />

    <!-- Priming de permiso de micrófono (solo la primera vez) -->
    <Teleport to="body">
      <div v-if="micModal === 'priming'" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-slate-950/70 backdrop-blur-sm" @click="micModal = null" />
        <div class="glass-strong relative w-full max-w-md p-6" role="dialog" aria-modal="true" aria-label="Permiso de micrófono">
          <p class="text-3xl">🎙️</p>
          <h2 class="mt-3 text-lg font-bold text-white">Permitir micrófono</h2>
          <p class="mt-2 text-sm leading-relaxed text-slate-300">
            SynapseCME usa el micrófono para transcribir tus observaciones de campo a texto. El audio se envía al
            servidor local para transcribirse y no se guarda. El navegador te pedirá confirmar el permiso.
          </p>
          <div class="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
            <button class="btn-ghost" @click="micModal = null">Ahora no</button>
            <button class="btn-primary" @click="allowMicrophone">Permitir micrófono</button>
          </div>
        </div>
      </div>

      <!-- Permiso denegado: instrucciones accionables, sin reintentos ciegos -->
      <div v-else-if="micModal === 'denied'" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-slate-950/70 backdrop-blur-sm" @click="micModal = null" />
        <div class="glass-strong relative w-full max-w-md p-6" role="dialog" aria-modal="true" aria-label="Micrófono bloqueado">
          <p class="text-3xl">🚫</p>
          <h2 class="mt-3 text-lg font-bold text-white">Micrófono bloqueado</h2>
          <p class="mt-2 text-sm leading-relaxed text-slate-300">
            El permiso de micrófono está denegado. Para volver a dictar, habilítalo en la configuración del sitio:
            toca el icono 🔒 de la barra de direcciones, cambia el permiso de micrófono a «Permitir» y recarga la
            página.
          </p>
          <div class="mt-5 flex justify-end">
            <button class="btn-primary" @click="micModal = null">Entendido</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
