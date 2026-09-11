<script setup lang="ts">
import { useToast } from '~/composables/useToast'
import { EXAMPLE_CATEGORIES, type ExampleItem } from '~/utils/examples'
import type { ConversationSummary } from '~/components/ConversationList.vue'
import type { EquipmentRef } from '~/components/EquipmentRefCard.vue'
import { formatClientRelative, getClientISOString, getClientTimezone } from '~/utils/date'
import { compressImage } from '~/utils/evidence'
import { useChatQueue } from '~/composables/useChatQueue'

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  time?: string
  extraction: Record<string, unknown> | null
  followup: string | null
  done: boolean
  error?: boolean
  // Pregunta al asistente (Fase 5): chip de tool en curso y burbuja de respuesta.
  tool?: string | null
  answer?: boolean
  // Respuesta con equipos referenciados: cards con enlace a su ficha.
  equipment?: EquipmentRef[]
  // Modo de presentación de la respuesta: texto o tarjetas.
  view?: 'text' | 'cards'
  // Mensajes cargados del historial: no se re-ingieren ni se confirman.
  historical?: boolean
  // Enlace al equipo confirmado
  equipmentId?: string | null
  // Evidencia fotográfica opcional
  evidence?: string | null
  // Indicador de encolado offline
  offline?: boolean
}

interface ConversationMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  extraction: Record<string, unknown> | null
  created_at: string
}

const { fetchWithAuth, request } = useApi()
const { show } = useToast()
const { apiOnline, refresh } = useConnection()
const { ensure } = useEvents()
const { user } = useAuth()
const chatQueue = useChatQueue()

const evidenceData = ref<string | null>(null)
const evidenceFileInput = ref<HTMLInputElement | null>(null)
const lightboxImage = ref<string | null>(null)
const editingProposal = reactive<Record<number, boolean>>({})

onMounted(() => {
  ensure({ client_type: 'field_app', name: 'App de campo SynapseCME' })
  void loadConversations()
})

const input = ref('')
const sending = ref(false)
const messages = ref<ChatMessage[]>([])
const listEl = ref<HTMLElement | null>(null)

// —— Sesiones de conversación ——
const conversations = ref<ConversationSummary[]>([])
const activeConversationId = ref<string | null>(null)
const drawerOpen = ref(false)
const loadingHistory = ref(false)

async function loadConversations() {
  try {
    conversations.value = await request<ConversationSummary[]>('/api/conversations')
  } catch {
    // Sin sesiones el chat sigue funcionando en modo legacy
  }
}

function timeLabel(iso?: string): string {
  return formatClientRelative(iso)
}

async function onPhotoSelected(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  try {
    const compressed = await compressImage(file)
    evidenceData.value = compressed
    show('Evidencia fotográfica adjuntada')
  } catch {
    show('Error al procesar la imagen')
  } finally {
    target.value = ''
  }
}

function removeEvidence() {
  evidenceData.value = null
}

// Auto-sincronización cuando se recupera la conexión
watch(
  () => apiOnline.value,
  (online) => {
    if (online && chatQueue.queuedCount.value > 0 && !chatQueue.isSyncing.value) {
      void syncOfflineQueue()
    }
  },
  { immediate: true },
)

async function syncOfflineQueue() {
  if (chatQueue.isSyncing.value || !chatQueue.queuedCount.value) return
  chatQueue.isSyncing.value = true
  show(`Sincronizando ${chatQueue.queuedCount.value} mensaje(s) pendientes…`)

  const payload = chatQueue.getBatchPayload()
  if (!payload) {
    chatQueue.isSyncing.value = false
    return
  }

  const msg = reactive<ChatMessage>({
    role: 'assistant',
    text: '',
    time: formatClientRelative(),
    extraction: null,
    followup: null,
    done: false,
    equipment: [],
    view: 'text',
  })
  messages.value.push(msg)
  scrollDown()

  try {
    const res = await fetchWithAuth('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
    await readSseStream(res.body, msg)
    for (const m of messages.value) {
      if (m.offline) m.offline = false
    }
    chatQueue.clear()
    show('Sincronización en lote completada con éxito')
  } catch {
    msg.error = true
    msg.text = 'Error al sincronizar mensajes pendientes con el agente.'
    show('Fallo al sincronizar mensajes offline')
  } finally {
    chatQueue.isSyncing.value = false
    scrollDown()
  }
}

async function openConversation(id: string) {
  drawerOpen.value = false
  loadingHistory.value = true
  try {
    const conv = await request<{
      id: string
      title: string
      messages: ConversationMessage[]
    }>(`/api/conversations/${id}`)
    activeConversationId.value = id
    messages.value = conv.messages.map((m) => ({
      role: m.role,
      text: m.content,
      time: timeLabel(m.created_at),
      extraction: m.extraction ? normalizeExtraction(m.extraction) : null,
      followup: null,
      done: true,
      equipment: [],
      view: 'text' as const,
      historical: true,
    }))
    scrollDown()
  } catch {
    show('No se pudo cargar la conversación')
  } finally {
    loadingHistory.value = false
  }
}

function newConversation() {
  activeConversationId.value = null
  messages.value = []
  drawerOpen.value = false
  nextTick(() => captureEl.value?.focus())
}

async function deleteConversation(id: string) {
  try {
    const res = await fetchWithAuth(`/api/conversations/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    conversations.value = conversations.value.filter((c) => c.id !== id)
    if (activeConversationId.value === id) newConversation()
    show('Conversación eliminada')
  } catch {
    show('No se pudo eliminar la conversación')
  }
}

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

// Sugerencias de preguntas al asistente (categoría "Preguntas" de los ejemplos).
const questionExamples = computed(
  () => EXAMPLE_CATEGORIES.find((c) => c.id === 'preguntas')?.examples ?? [],
)

// Nombres legibles para el chip de actividad de las tools del asistente.
const TOOL_LABELS: Record<string, string> = {
  list_equipment: 'equipos',
  get_equipment_detail: 'detalle de equipo',
  search_observations: 'observaciones previas',
  get_facility_info: 'instalación',
  ingest_observation: 'registrando observación',
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
    case 'tool': {
      // Actividad del asistente consultando el grafo: chip temporal que la
      // respuesta (evento answer) o el fin del stream reemplaza.
      msg.tool = typeof event.name === 'string' && event.name ? event.name : 'grafo'
      scrollDown()
      break
    }
    case 'answer': {
      // Respuesta normal del asistente a una pregunta (sin card de extracción).
      const t = typeof event.text === 'string' ? event.text : ''
      msg.text = t
      msg.tool = null
      msg.answer = true
      const refs = Array.isArray(event.equipment) ? (event.equipment as EquipmentRef[]) : []
      msg.equipment = refs.filter((r) => r && typeof r.id === 'string' && r.id)
      // Con equipos referenciados, las tarjetas son el modo por defecto.
      msg.view = msg.equipment.length ? 'cards' : 'text'
      scrollDown()
      break
    }
    case 'done':
      msg.done = true
      if (Array.isArray(event.equipment_ids) && event.equipment_ids.length) {
        msg.equipmentId = String(event.equipment_ids[0])
      }
      // Ancla la conversación activa (creada server-side si no venía) y
      // refresca la lista: el título se genera fire-and-forget tras el done,
      // así que la lista se re-carga para mostrarlo cuando llegue.
      if (typeof event.conversation_id === 'string' && event.conversation_id) {
        activeConversationId.value = event.conversation_id
        void loadConversations()
      }
      show(msg.answer ? 'Respuesta del asistente' : 'Registro guardado en el grafo')
      break
  }
}

function scrollDown() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

async function readSseStream(body: ReadableStream<Uint8Array>, msg: ChatMessage) {
  const reader = body.getReader()
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
}

async function send() {
  const text = input.value.trim()
  if ((!text && !evidenceData.value) || sending.value) return
  const currentEvidence = evidenceData.value
  input.value = ''
  evidenceData.value = null

  const clientTime = getClientISOString()
  const clientTz = getClientTimezone()

  // Comprobación offline: encolar localmente sin dar error si no hay conexión
  if (apiOnline.value === false) {
    chatQueue.enqueue(text, {
      evidence: currentEvidence,
      conversation_id: activeConversationId.value,
    })
    messages.value.push({
      role: 'user',
      text,
      time: formatClientRelative(clientTime),
      evidence: currentEvidence,
      extraction: null,
      followup: null,
      done: true,
      offline: true,
    })
    show('Sin conexión. Mensaje guardado en cola local.')
    scrollDown()
    return
  }

  messages.value.push({
    role: 'user',
    text,
    time: formatClientRelative(clientTime),
    evidence: currentEvidence,
    extraction: null,
    followup: null,
    done: true,
  })
  const msg = reactive<ChatMessage>({
    role: 'assistant',
    text: '',
    time: formatClientRelative(clientTime),
    extraction: null,
    followup: null,
    done: false,
    equipment: [],
    view: 'text',
  })
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
        client_timestamp: clientTime,
        client_timezone: clientTz,
        evidence: currentEvidence,
        ...(activeConversationId.value ? { conversation_id: activeConversationId.value } : {}),
      }),
    })
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
    await readSseStream(res.body, msg)
  } catch {
    chatQueue.enqueue(text, {
      evidence: currentEvidence,
      conversation_id: activeConversationId.value,
    })
    msg.error = true
    msg.text = 'Conexión interrumpida. El mensaje se guardó en cola local y se sincronizará al reconectar.'
  } finally {
    sending.value = false
    scrollDown()
  }
}

function applyFollowup(question: string) {
  input.value = question
}

async function copyFullChat() {
  if (!messages.value.length) {
    show('No hay mensajes en la conversación para copiar')
    return
  }
  const lines: string[] = []
  for (const m of messages.value) {
    const sender = m.role === 'user' ? (user.value?.full_name || user.value?.username || 'Usuario') : 'SynapseCME'
    const timeStr = m.time ? ` (${m.time})` : ''
    lines.push(`[${sender}]${timeStr}:`)
    if (m.text) {
      lines.push(m.text)
    }
    if (m.extraction) {
      lines.push('--- Extracción estructurada ---')
      for (const def of FIELD_DEFS) {
        const val = fieldValue(m.extraction, def)
        if (val !== undefined && val !== null && val !== '') {
          lines.push(`${def.label}: ${displayValue(def.key, val)}`)
        }
      }
    }
    if (m.equipment && m.equipment.length) {
      lines.push('--- Equipos referenciados ---')
      for (const eq of m.equipment) {
        const title = [eq.manufacturer, eq.model || 'sin modelo', eq.modality].filter(Boolean).join(' ')
        const loc = [eq.facility_name, eq.country].filter(Boolean).join(' · ')
        const st = eq.state ? ` [${eq.state}]` : ''
        lines.push(`- ${title} | ${loc}${st}`)
      }
    }
    if (m.followup) {
      lines.push(`Pregunta de seguimiento: ${m.followup}`)
    }
    lines.push('')
  }
  const fullText = lines.join('\n').trim()
  try {
    await navigator.clipboard.writeText(fullText)
    show('Conversación copiada al portapapeles')
  } catch {
    show('Error al copiar al portapapeles')
  }
}

const confirmed = reactive<Record<number, boolean>>({})
</script>

<template>
  <div class="flex h-[calc(100dvh-109px)] gap-6">
    <!-- Sidebar de conversaciones (desktop) -->
    <aside class="glass hidden w-[280px] shrink-0 flex-col md:flex" aria-label="Conversaciones">
      <ConversationList
        :conversations="conversations"
        :active-id="activeConversationId"
        @select="openConversation"
        @remove="deleteConversation"
        @create="newConversation"
      />
    </aside>

    <div class="flex min-w-0 flex-1 flex-col gap-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <button class="btn-ghost px-3 py-1.5 md:hidden" @click="drawerOpen = true">
            <Icon name="menu" :size="15" /> Conversaciones
          </button>
          <div>
            <h1 class="font-display text-[25px] font-bold text-[#101828]">Captura agent-first</h1>
            <p class="mt-1 text-sm text-[#5b6780]">
              Describe en lenguaje natural el equipamiento instalado; el agente extrae la estructura al grafo.
            </p>
          </div>
        </div>
      <div class="flex flex-wrap items-center gap-2">
        <span v-if="user" class="glass-chip border-[#bfe8d2] bg-[#eefbf4] text-[#067647]">
          <span class="h-1.5 w-1.5 rounded-full bg-[#17b26a]" />Capturando como {{ user.full_name || user.username }}
        </span>
        <span class="glass-chip border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]">
          Pregunta o dicta una observación
        </span>
        <button
          v-if="messages.length"
          type="button"
          class="glass-chip border-[#d0d5dd] bg-white text-[#344054] hover:bg-[#f8fafc] hover:border-[#98a2b3] cursor-pointer transition flex items-center gap-1.5 px-3 py-1"
          title="Copiar toda la conversación al portapapeles"
          @click="copyFullChat"
        >
          <Icon name="copy" :size="13" class="text-[#475467]" />
          <span class="font-medium">Copiar chat</span>
        </button>
      </div>
    </div>

    <div
      v-if="chatQueue.queuedCount.value > 0"
      class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#f2e2a8] bg-[#fffaeb] px-4 py-2.5"
    >
      <p class="flex items-center gap-2 text-xs font-medium text-[#8a6100]">
        <Icon name="clock" :size="15" class="shrink-0 text-[#d99a00]" />
        <span>Hay <b>{{ chatQueue.queuedCount.value }}</b> observación(es) en cola local pendientes de sincronización.</span>
      </p>
      <button
        v-if="apiOnline"
        class="btn-ghost text-xs font-semibold text-[#8a6100] border-[#e0c46c] hover:bg-[#faedd0] px-3 py-1"
        :disabled="chatQueue.isSyncing.value"
        @click="syncOfflineQueue"
      >
        <Icon name="refresh" :size="12" />
        {{ chatQueue.isSyncing.value ? 'Sincronizando…' : 'Sincronizar lote ahora' }}
      </button>
    </div>

    <div
      v-if="apiOnline === false"
      class="flex flex-wrap items-center gap-3 rounded-xl border border-[#f0d3d3] bg-[#fdf5f5] px-4 py-3"
    >
      <p class="flex flex-1 items-center gap-2.5 text-[13.5px] text-[#8a2018]">
        <Icon name="alert" :size="17" class="shrink-0 text-[#d92d20]" />Servidor local no disponible. Las observaciones
        quedan <b>en cola local</b> y se sincronizarán al recuperar la conexión.
      </p>
      <button class="btn-ghost border-[#f0d3d3] text-[#b42318] hover:bg-[#fdf0f0]" @click="refresh()">
        <Icon name="refresh" :size="13" />Reintentar
      </button>
    </div>

    <div ref="listEl" class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto py-1">
      <div
        v-if="!messages.length"
        class="flex flex-1 flex-col items-center justify-center rounded-2xl border border-[#e3e8f2] bg-white px-10 py-12 text-center shadow-sm"
      >
        <span class="grid h-14 w-14 place-items-center rounded-full border border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]">
          <Icon name="mic" :size="22" />
        </span>
        <p class="mt-4 font-display text-[15px] font-semibold text-[#101828]">Dicta o escribe tu primera observación</p>
        <p class="mt-2 max-w-[520px] text-[13.5px] leading-relaxed text-[#5b6780]">
          Ejemplo: «En el Hospital Aurora de Ciudad de Panamá hay 2 resonancias Siemens MAGNETOM Vida de 9 años, modalidad
          confirmada».
        </p>
        <p class="mt-5 text-xs text-[#7a8499]">¿Prefieres preguntar? Toca una sugerencia:</p>
        <div class="mt-3 flex flex-wrap justify-center gap-2">
          <button
            v-for="q in questionExamples"
            :key="q.id"
            class="rounded-full border border-[#d5e4fb] bg-[#f4f8fe] px-4 py-2 text-[13px] font-medium text-[#1d63d8] transition hover:border-[#c4ddfb] hover:bg-[#eaf3fe]"
            @click="applyExample(q)"
          >
            {{ q.text }}
          </button>
        </div>
      </div>

      <template v-for="(msg, i) in messages" :key="i">
        <div v-if="msg.role === 'user'" class="w-full rounded-2xl border border-[#e3e8f2] bg-white px-4 py-3.5 shadow-sm">
          <div class="mb-2 flex items-center justify-between gap-2.5">
            <div class="flex items-center gap-2.5">
              <span class="grid h-6 w-6 place-items-center rounded-full bg-[#eaf3fe] text-[#1d63d8]">
                <Icon name="user" :size="12" />
              </span>
              <span class="text-xs font-semibold text-[#101828]">{{ user?.full_name || user?.username || 'Observador de campo' }}</span>
              <span v-if="msg.time" class="text-[11.5px] text-[#98a2b8]">{{ msg.time }}</span>
            </div>
            <span v-if="msg.offline" class="glass-chip border-[#f2e2a8] bg-[#fffaeb] text-[#8a6100] text-[10px] font-medium">
              <Icon name="clock" :size="10" /> En cola offline
            </span>
          </div>
          <p v-if="msg.text" class="text-sm leading-relaxed text-[#39445c]">{{ msg.text }}</p>
          <div v-if="msg.evidence" class="mt-2.5">
            <img
              :src="msg.evidence.startsWith('data:') || msg.evidence.startsWith('http') ? msg.evidence : `/api/evidence/${msg.evidence}`"
              alt="Evidencia fotográfica"
              class="max-h-48 rounded-xl border border-[#c4ddfb] object-cover cursor-pointer transition hover:opacity-90 shadow-sm"
              @click="lightboxImage = msg.evidence"
            />
          </div>
        </div>

        <div v-else class="mr-auto w-full max-w-[92%]">
          <span
            v-if="msg.tool"
            class="glass-chip mb-2 inline-flex items-center gap-1.5 border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]"
          >
            <span class="animate-pulse"><Icon name="search" :size="13" /></span> Consultando {{ TOOL_LABELS[msg.tool] || msg.tool }}…
          </span>
          <div
            class="rounded-2xl rounded-bl-md border px-4 py-2.5 text-sm"
            :class="msg.error ? 'border-[#f0d3d3] bg-[#fdf5f5] text-[#8a2018]' : 'border-[#e3e8f2] bg-white text-[#1a2233]'"
            :data-testid="msg.answer ? 'assistant-answer' : undefined"
          >
            <span v-if="msg.text">{{ msg.text }}</span>
            <span v-else-if="!msg.done" class="animate-pulse text-[#98a2b8]">El agente está procesando…</span>
            <span v-if="sending && i === messages.length - 1 && !msg.text" class="animate-pulse">▌</span>
          </div>

          <!-- Modos de presentación de la respuesta con equipos referenciados -->
          <div v-if="msg.equipment && msg.equipment.length" class="mt-2 flex items-center gap-1.5">
            <button
              class="glass-chip text-[11px] transition"
              :class="msg.view !== 'cards' ? 'border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]' : 'text-[#7a8499]'"
              data-testid="view-mode-text"
              @click="msg.view = 'text'"
            >
              Texto
            </button>
            <button
              class="glass-chip text-[11px] transition"
              :class="msg.view === 'cards' ? 'border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]' : 'text-[#7a8499]'"
              data-testid="view-mode-cards"
              @click="msg.view = 'cards'"
            >
              Tarjetas
            </button>
          </div>

          <!-- Tarjetas con enlace a la ficha de cada equipo -->
          <div
            v-if="msg.equipment && msg.equipment.length && msg.view === 'cards'"
            class="mt-2 grid gap-2 sm:grid-cols-2"
            data-testid="assistant-equipment-cards"
          >
            <EquipmentRefCard v-for="eq in msg.equipment" :key="eq.id" :eq="eq" />
          </div>

          <div v-if="msg.followup" class="glass-strong mt-3 flex flex-wrap items-center justify-between gap-3 border-[#f2e2a8] bg-[#fffaeb] px-4 py-3">
            <p class="text-sm text-[#8a6100]">
              <span class="font-semibold">Pregunta de seguimiento:</span> {{ msg.followup }}
            </p>
            <button class="btn-ghost shrink-0" @click="applyFollowup(msg.followup)">Responder</button>
          </div>

          <div v-if="msg.extraction && Object.keys(msg.extraction).length" class="glass-strong mt-3 p-4">
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <h3 class="text-sm font-semibold text-[#101828]">Extracción estructurada</h3>
                <button
                  type="button"
                  class="glass-chip text-[11px] text-[#1d63d8] hover:bg-[#eaf3fe] transition"
                  :disabled="confirmed[i]"
                  @click="editingProposal[i] = !editingProposal[i]"
                >
                  <Icon :name="editingProposal[i] ? 'check' : 'edit'" :size="11" />
                  {{ editingProposal[i] ? 'Listo' : 'Editar propuesta' }}
                </button>
              </div>
              <StateChip :estado="estadoValue(msg.extraction)" />
            </div>

            <dl v-if="!editingProposal[i]" class="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5 sm:grid-cols-3">
              <template v-for="def in FIELD_DEFS" :key="def.key">
                <div v-if="fieldValue(msg.extraction, def) !== undefined">
                  <dt class="text-[11px] font-semibold uppercase tracking-wider text-[#7a8499]">{{ def.label }}</dt>
                  <dd class="mt-0.5 text-sm text-[#1a2233]">{{ displayValue(def.key, fieldValue(msg.extraction, def)) }}</dd>
                </div>
              </template>
            </dl>

            <div v-else class="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2.5 bg-white/60 p-3 rounded-xl border border-[#d5e4fb]">
              <div>
                <label class="text-[10.5px] font-semibold uppercase text-[#7a8499]">Instalación</label>
                <input v-model="msg.extraction.instalacion" class="glass-input mt-0.5 text-xs py-1" />
              </div>
              <div>
                <label class="text-[10.5px] font-semibold uppercase text-[#7a8499]">Modalidad</label>
                <input v-model="msg.extraction.modalidad" class="glass-input mt-0.5 text-xs py-1" />
              </div>
              <div>
                <label class="text-[10.5px] font-semibold uppercase text-[#7a8499]">Fabricante</label>
                <input v-model="msg.extraction.fabricante" class="glass-input mt-0.5 text-xs py-1" />
              </div>
              <div>
                <label class="text-[10.5px] font-semibold uppercase text-[#7a8499]">Modelo</label>
                <input v-model="msg.extraction.modelo" class="glass-input mt-0.5 text-xs py-1" />
              </div>
              <div>
                <label class="text-[10.5px] font-semibold uppercase text-[#7a8499]">Antigüedad (años)</label>
                <input v-model.number="msg.extraction.antiguedad" type="number" class="glass-input mt-0.5 text-xs py-1" />
              </div>
              <div>
                <label class="text-[10.5px] font-semibold uppercase text-[#7a8499]">Cantidad</label>
                <input v-model.number="msg.extraction.cantidad" type="number" class="glass-input mt-0.5 text-xs py-1" />
              </div>
            </div>

            <div v-if="confidencePct(msg.extraction) !== null" class="mt-3">
              <div class="flex justify-between text-[11px] text-[#7a8499]">
                <span>Confianza</span><span>{{ confidencePct(msg.extraction)!.toFixed(0) }} %</span>
              </div>
              <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-[#eef1f7]">
                <div
                  class="h-full rounded-full bg-gradient-to-r from-[#1d63d8] to-[#17b26a] transition-all"
                  :style="{ width: `${confidencePct(msg.extraction)}%` }"
                />
              </div>
            </div>
            <div class="mt-4 flex justify-end gap-2">
              <NuxtLink
                v-if="confirmed[i] && msg.equipmentId"
                :to="'/equipos/' + msg.equipmentId"
                class="btn-primary flex items-center gap-1.5"
              >
                <Icon name="check" :size="14" />
                Ver equipo registrado →
              </NuxtLink>
              <button
                v-else
                class="btn-primary"
                :disabled="confirmed[i] || msg.historical"
                :title="msg.historical ? 'Este registro ya fue confirmado en su momento' : undefined"
                @click="confirmed[i] = true; show('Registro confirmado')"
              >
                <Icon v-if="confirmed[i]" name="check" :size="14" />
                {{ confirmed[i] ? 'Confirmado' : msg.historical ? 'Registro histórico' : 'Confirmar registro' }}
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>

    <div class="glass-strong p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
      <div v-if="evidenceData" class="mb-3 flex items-center justify-between gap-3 rounded-xl border border-[#c4ddfb] bg-[#f4f8fe] p-2.5">
        <div class="flex items-center gap-3">
          <img :src="evidenceData" alt="Vista previa de evidencia" class="h-12 w-12 rounded-lg object-cover border border-[#b2ccf2]" />
          <div>
            <p class="text-xs font-semibold text-[#101828]">Evidencia fotográfica adjuntada</p>
            <p class="text-[11px] text-[#5b6780]">Se vinculará a la observación</p>
          </div>
        </div>
        <button type="button" class="btn-ghost text-xs text-[#b42318] hover:bg-[#fdf0f0]" @click="removeEvidence">
          <Icon name="close" :size="13" /> Quitar
        </button>
      </div>

      <label for="capture" class="mb-1.5 block font-display text-[10.5px] font-semibold uppercase tracking-[0.12em] text-[#1d63d8]">
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
            <Icon name="bulb" :size="15" /> Ejemplos
          </button>
          <input
            ref="evidenceFileInput"
            type="file"
            accept="image/*"
            capture="environment"
            class="hidden"
            @change="onPhotoSelected"
          />
          <button
            type="button"
            class="btn-ghost"
            :class="evidenceData ? 'border-[#1d63d8] bg-[#eaf3fe] text-[#1d63d8]' : ''"
            :disabled="sending"
            title="Adjuntar evidencia fotográfica"
            @click="evidenceFileInput?.click()"
          >
            <Icon name="camera" :size="15" />
            <span class="hidden sm:inline">Foto</span>
          </button>
          <button
            class="btn-ghost"
            :class="dictating ? 'border-[#f5a9a9] bg-[#fdf0f0] text-[#b42318]' : ''"
            :disabled="transcribing"
            :title="dictating ? 'Detener dictado' : 'Dictar con el micrófono'"
            @click="toggleDictation"
          >
            <span :class="dictating ? 'animate-pulse' : ''">
              <Icon :name="dictating ? 'close' : 'mic'" :size="15" />
            </span>
            {{ dictating ? 'Escuchando…' : transcribing ? 'Transcribiendo…' : 'Dictar' }}
          </button>
          <span v-if="dictating" class="glass-chip border-[#f5a9a9] bg-[#fdf0f0] font-mono text-[#b42318]">
            <Icon name="timer" :size="13" /> {{ recordTimeLabel }}
          </span>
          <button v-if="dictating" class="btn-ghost px-3 py-1.5 text-xs" @click="cancelRecording">Cancelar</button>
          <p v-else-if="!transcribing" class="hidden text-xs text-[#98a2b8] sm:block">
            Toca Dictar o Foto para capturar en campo
          </p>
        </div>
        <p class="hidden text-xs text-[#98a2b8] lg:block">Enter para enviar · Mayús+Enter para salto de línea</p>
        <button class="btn-primary min-w-36" :disabled="sending || (!input.trim() && !evidenceData)" @click="send">
          {{ sending ? 'Procesando…' : 'Enviar al agente' }}<Icon v-if="!sending" name="send" :size="14" />
        </button>
      </div>
    </div>
    </div>

    <!-- Drawer de conversaciones (móvil) -->
    <Teleport to="body">
      <div v-if="drawerOpen" class="fixed inset-0 z-50 flex md:hidden">
        <div class="absolute inset-0 bg-[#101828]/40 backdrop-blur-sm" @click="drawerOpen = false" />
        <div
          class="glass-strong relative m-0 flex h-full w-80 max-w-[85vw] flex-col p-0"
          role="dialog"
          aria-modal="true"
          aria-label="Conversaciones"
          @click.stop
        >
          <ConversationList
            :conversations="conversations"
            :active-id="activeConversationId"
            @select="openConversation"
            @remove="deleteConversation"
            @create="newConversation"
          />
        </div>
      </div>
    </Teleport>

    <ExamplesDialog v-model="examplesOpen" @pick="applyExample" />

    <!-- Priming de permiso de micrófono (solo la primera vez) -->
    <Teleport to="body">
      <div v-if="micModal === 'priming'" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-[#101828]/40 backdrop-blur-sm" @click="micModal = null" />
        <div class="glass-strong relative w-full max-w-md p-6" role="dialog" aria-modal="true" aria-label="Permiso de micrófono">
          <span class="grid h-12 w-12 place-items-center rounded-full border border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]">
            <Icon name="mic" :size="22" />
          </span>
          <h2 class="mt-3 text-lg font-bold text-[#101828]">Permitir micrófono</h2>
          <p class="mt-2 text-sm leading-relaxed text-[#5b6780]">
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
        <div class="absolute inset-0 bg-[#101828]/40 backdrop-blur-sm" @click="micModal = null" />
        <div class="glass-strong relative w-full max-w-md p-6" role="dialog" aria-modal="true" aria-label="Micrófono bloqueado">
          <span class="grid h-12 w-12 place-items-center rounded-full border border-[#f5a9a9] bg-[#fdf0f0] text-[#b42318]">
            <Icon name="mic-off" :size="22" />
          </span>
          <h2 class="mt-3 text-lg font-bold text-[#101828]">Micrófono bloqueado</h2>
          <p class="mt-2 text-sm leading-relaxed text-[#5b6780]">
            El permiso de micrófono está denegado. Para volver a dictar, habilítalo en la configuración del sitio:
            toca el candado de la barra de direcciones, cambia el permiso de micrófono a «Permitir» y recarga la
            página.
          </p>
          <div class="mt-5 flex justify-end">
            <button class="btn-primary" @click="micModal = null">Entendido</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Modal Lightbox para evidencia fotográfica -->
    <Teleport to="body">
      <div
        v-if="lightboxImage"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
        @click="lightboxImage = null"
      >
        <div class="relative max-h-[90vh] max-w-[90vw]" @click.stop>
          <img
            :src="lightboxImage.startsWith('data:') || lightboxImage.startsWith('http') ? lightboxImage : `/api/evidence/${lightboxImage}`"
            alt="Evidencia fotográfica completa"
            class="max-h-[85vh] max-w-[85vw] rounded-xl object-contain shadow-2xl"
          />
          <button
            class="absolute -top-3 -right-3 grid h-8 w-8 place-items-center rounded-full bg-white text-[#101828] shadow-md hover:bg-gray-100"
            @click="lightboxImage = null"
          >
            <Icon name="close" :size="16" />
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>
