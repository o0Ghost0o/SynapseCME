<script setup lang="ts">
import { useToast } from '~/composables/useToast'

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
let mediaRecorder: MediaRecorder | null = null
let recorderMime = ''
let recordChunks: Blob[] = []
let recordTimer: ReturnType<typeof setTimeout> | undefined
const MAX_RECORDING_MS = 60000

async function toggleDictation() {
  if (dictating.value) {
    mediaRecorder?.stop()
    return
  }
  if (transcribing.value) return
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    recordChunks = []
    mediaRecorder = new MediaRecorder(stream)
    recorderMime = mediaRecorder.mimeType || 'audio/webm'
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size) recordChunks.push(e.data)
    }
    mediaRecorder.onstop = () => {
      clearTimeout(recordTimer)
      stream.getTracks().forEach((t) => t.stop())
      dictating.value = false
      void uploadRecording()
    }
    mediaRecorder.start()
    dictating.value = true
    recordTimer = setTimeout(() => mediaRecorder?.stop(), MAX_RECORDING_MS)
  } catch {
    dictating.value = false
    show('Permiso de micrófono denegado')
  }
}

async function uploadRecording() {
  if (!recordChunks.length) return
  const blob = new Blob(recordChunks, { type: recorderMime })
  transcribing.value = true
  try {
    const form = new FormData()
    form.append('file', blob, 'dictation.webm')
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
    show('Dictado no disponible')
  } finally {
    transcribing.value = false
  }
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
    case 'token':
      msg.text += typeof event.text === 'string' ? event.text : ''
      scrollDown()
      break
    case 'extraction':
      msg.extraction = (event.data ?? event.extraction ?? {}) as Record<string, unknown>
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
  <div class="flex flex-col gap-4">
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
          <span>📱</span> Modo: App de campo
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

    <div ref="listEl" class="glass flex h-[46vh] flex-col gap-3 overflow-y-auto p-4">
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

    <div class="glass p-4">
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
        <div class="flex items-center gap-2">
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
          <p v-if="dictating" class="text-xs text-rose-300">Toca de nuevo para detener</p>
        </div>
        <p class="hidden text-xs text-slate-500 lg:block">Enter para enviar · Mayús+Enter para salto de línea</p>
        <button class="btn-primary min-w-36" :disabled="sending || !input.trim()" @click="send">
          {{ sending ? 'Procesando…' : 'Enviar al agente' }}
        </button>
      </div>
    </div>
  </div>
</template>
