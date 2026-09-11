<script setup lang="ts">
import { formatEvidenceUrl } from '~/utils/evidence'
const route = useRoute()
const { fetchWithAuth } = useApi()
const { show } = useToast()

const loading = ref(true)
const failed = ref(false)
const notFound = ref(false)
const detail = ref<EquipmentDetailData | null>(null)

const equipmentId = computed(() => String(route.params.id || ''))

async function load() {
  loading.value = true
  failed.value = false
  notFound.value = false
  try {
    const res = await fetchWithAuth(`/api/equipment/${encodeURIComponent(equipmentId.value)}`)
    if (res.status === 404) {
      notFound.value = true
      detail.value = null
      return
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    detail.value = normalizeEquipmentDetail(await res.json())
  } catch {
    failed.value = true
    detail.value = null
  } finally {
    loading.value = false
  }
}

const equipment = computed(() => detail.value?.equipment ?? null)

const title = computed(() =>
  [equipment.value?.manufacturer, equipment.value?.model].filter(Boolean).join(' ') || 'Equipo sin modelo',
)

const hasIssues = computed(() =>
  (detail.value?.parameters ?? []).some((p) => p.status === 'warning' || p.status === 'critical'),
)

const parameters = computed(() => detail.value?.parameters ?? [])
const observations = computed(() => detail.value?.observations ?? [])
const parameterHistory = computed(() => detail.value?.parameterHistory ?? [])

function observationParams(obs: ObservationEntry): ParameterEntry[] {
  return parameterHistory.value.filter((p) => p.sourceObservationId === obs.id)
}

function paramValue(p: ParameterEntry): string {
  if (p.value === null || p.value === '') return '—'
  return `${p.value}${p.unit ? ` ${p.unit}` : ''}`
}

watch(equipmentId, load)
onMounted(load)

// —— Edición manual directa (PATCH) ——
const editMode = ref(false)
const savingManual = ref(false)
const lightboxImage = ref<string | null>(null)
const editForm = reactive({
  manufacturer: '',
  model: '',
  ageYears: null as number | null,
  quantity: 1,
  parameters: [] as {
    name: string
    value: string | number | null
    unit: string
    status: 'ok' | 'warning' | 'critical' | null
  }[],
})

function startEditing() {
  if (!equipment.value) return
  editForm.manufacturer = equipment.value.manufacturer || ''
  editForm.model = equipment.value.model || ''
  editForm.ageYears = equipment.value.ageYears
  editForm.quantity = (equipment.value as Record<string, unknown>).quantity ? Number((equipment.value as Record<string, unknown>).quantity) : 1
  editForm.parameters = parameters.value.map((p) => ({
    name: p.name,
    value: p.value,
    unit: p.unit || '',
    status: p.status,
  }))
  editMode.value = true
}

function addParameterRow() {
  editForm.parameters.push({
    name: '',
    value: null,
    unit: '',
    status: 'ok',
  })
}

function removeParameterRow(idx: number) {
  editForm.parameters.splice(idx, 1)
}

async function saveManualEdit() {
  savingManual.value = true
  try {
    const res = await fetchWithAuth(`/api/equipment/${encodeURIComponent(equipmentId.value)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        manufacturer: editForm.manufacturer.trim() || null,
        model: editForm.model.trim() || null,
        age_years: editForm.ageYears,
        quantity: editForm.quantity,
        parameters: editForm.parameters
          .filter((p) => p.name.trim())
          .map((p) => {
            const rawVal = p.value
            const numVal = Number(rawVal)
            return {
              name: p.name.trim(),
              value: rawVal === '' || rawVal === null ? null : (Number.isFinite(numVal) ? numVal : String(rawVal)),
              unit: p.unit.trim() || null,
              status: p.status || null,
            }
          }),
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    show('Ficha técnica actualizada exitosamente')
    editMode.value = false
    await load()
  } catch {
    show('Error al actualizar la ficha del equipo')
  } finally {
    savingManual.value = false
  }
}

// —— Mini-chat de revisión anclado a este equipo ——
interface EqChatParam {
  name: string
  value?: number | string | null
  unit?: string | null
  status?: string | null
}

interface EqChatMessage {
  role: 'user' | 'assistant'
  text: string
  identified: string[]
  params: EqChatParam[]
  followup: string | null
  done: boolean
  error: boolean
}

const chatMessages = ref<EqChatMessage[]>([])
const chatInput = ref('')
const sending = ref(false)
const chatListEl = ref<HTMLElement | null>(null)
const dictation = useDictation(chatInput)

const REVISION_SUGGESTIONS = [
  'El fabricante es Siemens y el modelo es MAGNETOM Vida',
  'La corriente del tubo es 10 mA nominal',
  'El nivel de helio está al 45%, bajo',
]

function chatScrollDown() {
  nextTick(() => {
    if (chatListEl.value) chatListEl.value.scrollTop = chatListEl.value.scrollHeight
  })
}

async function sendRevision(textOverride?: string) {
  const text = (textOverride ?? chatInput.value).trim()
  if (!text || sending.value) return
  chatInput.value = ''
  chatMessages.value.push({ role: 'user', text, identified: [], params: [], followup: null, done: true, error: false })
  const msg = reactive<EqChatMessage>({
    role: 'assistant',
    text: '',
    identified: [],
    params: [],
    followup: null,
    done: false,
    error: false,
  })
  chatMessages.value.push(msg)
  sending.value = true
  chatScrollDown()
  try {
    const res = await fetchWithAuth(`/api/equipment/${encodeURIComponent(equipmentId.value)}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, client_type: 'field_app' }),
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
            handleChatEvent(msg, JSON.parse(payload))
          } catch {
            // línea de mantenimiento del stream: se ignora
          }
        }
      }
    }
    msg.done = true
    show('Revisión guardada en el equipo')
    void load()
  } catch {
    msg.error = true
    msg.text = msg.text || 'No se pudo contactar con el agente. Comprueba que el servidor local esté en marcha.'
  } finally {
    sending.value = false
    chatScrollDown()
  }
}

function handleChatEvent(msg: EqChatMessage, event: Record<string, unknown>) {
  switch (event.type) {
    case 'token':
      msg.text += typeof event.text === 'string' ? event.text : ''
      chatScrollDown()
      break
    case 'extraction': {
      const data = (event.data ?? {}) as {
        items?: {
          manufacturer?: string | null
          model?: string | null
          parameters?: EqChatParam[]
        }[]
      }
      const item = data.items?.[0]
      if (item?.manufacturer) msg.identified.push(`fabricante ${item.manufacturer}`)
      if (item?.model) msg.identified.push(`modelo ${item.model}`)
      msg.params = item?.parameters ?? []
      break
    }
    case 'followup':
      if (typeof event.question === 'string') msg.followup = event.question
      break
  }
}

function applyFollowup(question: string) {
  chatInput.value = question
}

function paramClass(status?: string | null): string {
  if (!status) return ''
  return PARAMETER_STATUS_CLASSES[status as 'ok' | 'warning' | 'critical'] ?? ''
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <button class="btn-ghost self-start" @click="navigateTo('/dashboard')">← Volver al panel</button>

    <div v-if="loading" class="glass p-10 text-center text-sm text-[#7a8499]">
      <span class="animate-pulse">Cargando equipo…</span>
    </div>

    <ApiUnavailable v-else-if="failed" @retry="load" />

    <div v-else-if="notFound" class="glass mx-auto max-w-md p-8 text-center">
      <span class="mx-auto grid h-14 w-14 place-items-center rounded-full border border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]">
        <Icon name="search" :size="26" />
      </span>
      <h1 class="mt-3 font-display text-xl font-bold text-[#101828]">Equipo no encontrado</h1>
      <p class="mt-2 text-sm text-[#5b6780]">
        No existe un equipo con el identificador «{{ equipmentId }}» en el grafo.
      </p>
      <button class="btn-primary mt-5" @click="navigateTo('/dashboard')">Volver al panel</button>
    </div>

    <template v-else-if="equipment">
      <div class="glass-strong p-5">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <h1 class="font-display text-xl font-bold text-[#101828]">{{ title }}</h1>
            <p class="mt-1 flex items-center gap-1.5 text-sm text-[#5b6780]">
              <Icon name="hospital" :size="14" class="shrink-0 text-[#1d63d8]" />
              {{ equipment.facilityName
              }}<span v-if="equipment.city || equipment.country">
                · {{ [equipment.city, equipment.country].filter(Boolean).join(', ') }}
              </span>
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <button
              class="btn-ghost flex items-center gap-1.5 text-xs py-1.5 px-3"
              @click="editMode ? editMode = false : startEditing()"
            >
              <Icon :name="editMode ? 'close' : 'edit'" :size="13" />
              {{ editMode ? 'Cancelar edición' : 'Editar manualmente' }}
            </button>
            <span class="glass-chip">{{ equipment.modality }}</span>
            <span v-if="equipment.ageYears !== null" class="glass-chip">{{ equipment.ageYears }} años</span>
            <StateChip :estado="equipment.state" />
          </div>
        </div>
      </div>

      <!-- Formulario de edición manual directa -->
      <section v-if="editMode" class="glass-strong border-[#c4ddfb] bg-[#f8fbff] p-5 shadow-sm">
        <div class="flex items-center justify-between gap-2 border-b border-[#e3e8f2] pb-3">
          <div>
            <h2 class="font-display text-sm font-semibold text-[#101828]">Edición manual de ficha</h2>
            <p class="text-xs text-[#5b6780]">Modifica directamente los datos del equipo y sus magnitudes técnicas.</p>
          </div>
          <button class="btn-ghost text-xs" @click="editMode = false">
            <Icon name="close" :size="13" /> Cerrar
          </button>
        </div>

        <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
          <div>
            <label class="text-[11px] font-semibold uppercase text-[#7a8499]">Fabricante</label>
            <input v-model="editForm.manufacturer" class="glass-input mt-1 text-sm py-1.5" placeholder="Ej: GE, Siemens" />
          </div>
          <div>
            <label class="text-[11px] font-semibold uppercase text-[#7a8499]">Modelo</label>
            <input v-model="editForm.model" class="glass-input mt-1 text-sm py-1.5" placeholder="Ej: LightSpeed" />
          </div>
          <div>
            <label class="text-[11px] font-semibold uppercase text-[#7a8499]">Antigüedad (años)</label>
            <input v-model.number="editForm.ageYears" type="number" step="0.5" class="glass-input mt-1 text-sm py-1.5" placeholder="Ej: 4" />
          </div>
          <div>
            <label class="text-[11px] font-semibold uppercase text-[#7a8499]">Cantidad</label>
            <input v-model.number="editForm.quantity" type="number" min="1" class="glass-input mt-1 text-sm py-1.5" placeholder="1" />
          </div>
        </div>

        <div class="mt-5">
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-xs font-semibold uppercase tracking-wider text-[#7a8499]">Parámetros técnicos</h3>
            <button type="button" class="btn-ghost text-xs py-1 px-2.5" @click="addParameterRow">
              <Icon name="plus" :size="12" /> Añadir parámetro
            </button>
          </div>

          <div v-if="editForm.parameters.length" class="mt-2.5 flex flex-col gap-2">
            <div
              v-for="(p, idx) in editForm.parameters"
              :key="idx"
              class="flex flex-wrap items-center gap-2 rounded-xl border border-[#e3e8f2] bg-white p-2.5"
            >
              <input
                v-model="p.name"
                class="glass-input text-xs py-1 flex-1 min-w-[120px]"
                placeholder="Nombre (ej: voltaje)"
              />
              <input
                v-model="p.value"
                class="glass-input text-xs py-1 w-24"
                placeholder="Valor"
              />
              <input
                v-model="p.unit"
                class="glass-input text-xs py-1 w-20"
                placeholder="Unidad"
              />
              <select
                v-model="p.status"
                class="glass-input text-xs py-1 w-28"
              >
                <option :value="null">Sin estado</option>
                <option value="ok">Ok (normal)</option>
                <option value="warning">Warning</option>
                <option value="critical">Critical</option>
              </select>
              <button
                type="button"
                class="btn-ghost text-xs text-[#b42318] hover:bg-[#fdf0f0] p-1.5"
                title="Eliminar parámetro"
                @click="removeParameterRow(idx)"
              >
                <Icon name="trash" :size="13" />
              </button>
            </div>
          </div>
          <p v-else class="mt-2 text-xs text-[#98a2b8] italic">No hay parámetros definidos. Pulsa «Añadir parámetro» para agregar uno.</p>
        </div>

        <div class="mt-5 flex justify-end gap-2 border-t border-[#e3e8f2] pt-3">
          <button class="btn-ghost text-xs" :disabled="savingManual" @click="editMode = false">Cancelar</button>
          <button class="btn-primary text-xs flex items-center gap-1.5" :disabled="savingManual" @click="saveManualEdit">
            <Icon v-if="!savingManual" name="check" :size="13" />
            {{ savingManual ? 'Guardando…' : 'Guardar cambios' }}
          </button>
        </div>
      </section>

      <div
        v-if="hasIssues"
        class="glass flex items-center gap-3 border-[#f2e2a8] bg-[#fffaeb] px-4 py-3"
      >
        <Icon name="alert" :size="18" class="shrink-0 text-[#d99a00]" />
        <p class="text-sm text-[#8a6100]">Posible mantenimiento/reparación: hay parámetros fuera de rango.</p>
      </div>

      <!-- Mini-chat de revisión: el agente actualiza esta ficha -->
      <section class="glass p-5" data-testid="equipment-chat">
        <h2 class="font-display text-sm font-semibold text-[#101828]">Revisar con el agente</h2>
        <p class="mt-0.5 text-xs text-[#7a8499]">
          Contale una corrección o medición de este equipo (marca, modelo, parámetros); el agente actualiza su ficha.
        </p>

        <div ref="chatListEl" class="mt-3 flex max-h-72 min-h-16 flex-col gap-3 overflow-y-auto pr-1">
          <div v-if="!chatMessages.length" class="flex flex-wrap items-center gap-2">
            <span class="text-xs text-[#7a8499]">Ejemplos:</span>
            <button
              v-for="s in REVISION_SUGGESTIONS"
              :key="s"
              class="glass-chip rounded-full border-[#d5e4fb] bg-[#f4f8fe] text-[#1d63d8] transition hover:border-[#c4ddfb] hover:bg-[#eaf3fe]"
              @click="sendRevision(s)"
            >
              <Icon name="message" :size="12" class="shrink-0" />
              {{ s }}
            </button>
          </div>

          <template v-for="(msg, i) in chatMessages" :key="i">
            <div
              v-if="msg.role === 'user'"
              class="ml-auto max-w-[80%] rounded-2xl rounded-br-md border border-[#c4ddfb] bg-[#eaf3fe] px-4 py-2.5 text-sm text-[#101828]"
            >
              {{ msg.text }}
            </div>
            <div v-else class="mr-auto w-full max-w-[92%]">
              <div
                class="rounded-2xl rounded-bl-md border px-4 py-2.5 text-sm"
                :class="msg.error ? 'border-[#f0d3d3] bg-[#fdf5f5] text-[#8a2018]' : 'border-[#e3e8f2] bg-white text-[#1a2233]'"
                data-testid="equipment-chat-answer"
              >
                <span v-if="msg.text">{{ msg.text }}</span>
                <span v-else-if="!msg.done" class="animate-pulse text-[#7a8499]">El agente está procesando…</span>
                <div v-if="msg.identified.length" class="mt-2 flex flex-wrap gap-1.5">
                  <span v-for="bit in msg.identified" :key="bit" class="glass-chip border-[#bfe8d2] bg-[#eefbf4] text-[#067647]">
                    <Icon name="edit" :size="11" class="shrink-0" />
                    {{ bit }}
                  </span>
                </div>
                <div v-if="msg.params.length" class="mt-2 flex flex-wrap gap-1.5">
                  <span
                    v-for="p in msg.params"
                    :key="p.name"
                    class="glass-chip"
                    :class="paramClass(p.status)"
                  >
                    {{ p.name }}: {{ p.value ?? '—' }}{{ p.unit ? ` ${p.unit}` : '' }}
                  </span>
                </div>
              </div>
              <button
                v-if="msg.followup"
                class="glass-chip mt-2 rounded-full border-[#d5e4fb] bg-[#f4f8fe] text-[#1d63d8] transition hover:border-[#c4ddfb] hover:bg-[#eaf3fe]"
                @click="applyFollowup(msg.followup as string)"
              >
                <Icon name="message" :size="12" class="shrink-0" />
                {{ msg.followup }}
              </button>
            </div>
          </template>
        </div>

        <div class="mt-3 flex items-end gap-2">
          <button
            class="btn-ghost shrink-0 px-3 py-2.5"
            :class="dictation.dictating.value ? 'border-[#f5a9a9] bg-[#fdf0f0] text-[#b42318]' : ''"
            :disabled="sending || dictation.transcribing.value"
            :title="dictation.dictating.value ? 'Detener dictado' : 'Dictar con el micrófono'"
            @click="dictation.toggle()"
          >
            <span :class="dictation.dictating.value ? 'animate-pulse' : ''">
              <Icon :name="dictation.dictating.value ? 'close' : 'mic'" :size="16" />
            </span>
            <span class="hidden sm:inline">
              {{ dictation.dictating.value ? 'Escuchando…' : dictation.transcribing.value ? 'Transcribiendo…' : 'Dictar' }}
            </span>
          </button>
          <span
            v-if="dictation.dictating.value"
            class="glass-chip shrink-0 border-[#f5a9a9] bg-[#fdf0f0] font-mono text-[#b42318]"
          >
            {{ dictation.recordTimeLabel.value }}
          </span>
          <button v-if="dictation.dictating.value" class="btn-ghost shrink-0 px-3 py-1.5 text-xs" @click="dictation.cancel()">
            Cancelar
          </button>
          <textarea
            v-model="chatInput"
            data-testid="equipment-chat-input"
            rows="1"
            class="glass-input min-h-[42px] flex-1 resize-none px-3 py-2.5 text-sm"
            placeholder="Ej.: «El fabricante es Philips y la corriente del tubo es 10 mA nominal»"
            @keydown.enter.exact.prevent="sendRevision()"
          />
          <button
            class="btn-primary shrink-0 px-4 py-2.5"
            :disabled="sending || !chatInput.trim()"
            data-testid="equipment-chat-send"
            @click="sendRevision()"
          >
            {{ sending ? 'Procesando…' : 'Enviar' }}
          </button>
        </div>

        <!-- Modal de permiso de micrófono (previo al primer uso) -->
        <div
          v-if="dictation.micModal.value === 'priming'"
          class="fixed inset-0 z-50 flex items-center justify-center bg-[#101828]/40 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
        >
          <div class="glass-strong w-full max-w-sm p-6 text-center">
            <span class="mx-auto grid h-12 w-12 place-items-center rounded-full border border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]">
              <Icon name="mic" :size="22" />
            </span>
            <h3 class="mt-3 text-lg font-bold text-[#101828]">Permiso de micrófono</h3>
            <p class="mt-2 text-sm text-[#5b6780]">
              Para dictar revisiones necesitamos acceso al micrófono. Tu navegador te pedirá confirmación.
            </p>
            <div class="mt-5 flex justify-center gap-2">
              <button class="btn-ghost" @click="dictation.micModal.value = null">Cancelar</button>
              <button class="btn-primary" @click="dictation.allowMicrophone()">Permitir micrófono</button>
            </div>
          </div>
        </div>

        <!-- Modal de micrófono denegado -->
        <div
          v-if="dictation.micModal.value === 'denied'"
          class="fixed inset-0 z-50 flex items-center justify-center bg-[#101828]/40 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
        >
          <div class="glass-strong w-full max-w-sm p-6 text-center">
            <span class="mx-auto grid h-12 w-12 place-items-center rounded-full border border-[#f5a9a9] bg-[#fdf0f0] text-[#b42318]">
              <Icon name="mic-off" :size="22" />
            </span>
            <h3 class="mt-3 text-lg font-bold text-[#101828]">Micrófono bloqueado</h3>
            <p class="mt-2 text-sm text-[#5b6780]">
              El permiso de micrófono está denegado. Para volver a dictar, habilítalo en la configuración del sitio:
              toca el candado de la barra de direcciones → Permisos → Micrófono → Permitir.
            </p>
            <div class="mt-5 flex justify-center">
              <button class="btn-primary" @click="dictation.micModal.value = null">Entendido</button>
            </div>
          </div>
        </div>
      </section>

      <section class="glass p-5">
        <h2 class="font-display text-sm font-semibold text-[#101828]">Parámetros</h2>
        <p class="mt-0.5 text-xs text-[#7a8499]">Último valor registrado por magnitud técnica.</p>
        <ul v-if="parameters.length" class="mt-3 flex flex-col gap-2">
          <li
            v-for="p in parameters"
            :key="p.id"
            class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#e9edf5] bg-[#f7f9fd] px-3 py-2"
          >
            <div class="min-w-0">
              <p class="text-sm capitalize text-[#1a2233]">{{ p.name }}</p>
              <p class="text-[11px] text-[#7a8499]">{{ relativeDate(p.createdAt) }}</p>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-sm font-semibold text-[#101828]">{{ paramValue(p) }}</span>
              <span v-if="p.status" class="glass-chip" :class="PARAMETER_STATUS_CLASSES[p.status]">
                {{ PARAMETER_STATUS_LABELS[p.status] }}
              </span>
              <span v-else class="glass-chip">sin clasificar</span>
            </div>
          </li>
        </ul>
        <p v-else class="mt-3 rounded-xl border border-dashed border-[#d4dbe8] p-4 text-center text-xs text-[#7a8499]">
          Todavía no hay parámetros registrados para este equipo.
        </p>
      </section>

      <section class="glass p-5">
        <h2 class="font-display text-sm font-semibold text-[#101828]">Historial de observaciones</h2>
        <p class="mt-0.5 text-xs text-[#7a8499]">{{ observations.length }} observaciones en el grafo.</p>
        <ol v-if="observations.length" class="mt-4 flex flex-col gap-4 border-l border-[#e3e8f2] pl-4">
          <li v-for="obs in observations" :key="obs.id" class="relative">
            <span class="absolute -left-[21.5px] top-1.5 h-2.5 w-2.5 rounded-full border border-[#c4ddfb] bg-[#1d63d8]" />
            <p class="text-sm leading-relaxed text-[#1a2233]">{{ obs.text }}</p>
            <div v-if="obs.evidence" class="mt-2">
              <img
                :src="formatEvidenceUrl(obs.evidence)"
                alt="Evidencia fotográfica"
                class="max-h-36 rounded-lg border border-[#c4ddfb] object-cover cursor-pointer transition hover:opacity-90 shadow-sm"
                @click="lightboxImage = obs.evidence"
              />
            </div>
            <div class="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-[#7a8499]">
              <span class="glass-chip">
                <Icon name="user" :size="11" class="shrink-0" />
                {{ obs.contributor }}
              </span>
              <span class="glass-chip">
                <Icon name="clock" :size="11" class="shrink-0" />
                {{ relativeDate(obs.createdAt) }}
              </span>
              <span v-if="obs.confidence !== null" class="glass-chip">
                Confianza {{ Math.round(obs.confidence * 100) }}%
              </span>
            </div>
            <div v-if="observationParams(obs).length" class="mt-2 flex flex-wrap gap-1.5">
              <span
                v-for="p in observationParams(obs)"
                :key="p.id"
                class="glass-chip"
                :class="p.status ? PARAMETER_STATUS_CLASSES[p.status] : ''"
              >
                {{ p.name }}: {{ paramValue(p) }}
              </span>
            </div>
          </li>
        </ol>
        <p v-else class="mt-3 rounded-xl border border-dashed border-[#d4dbe8] p-4 text-center text-xs text-[#7a8499]">
          Sin observaciones registradas todavía.
        </p>
      </section>
    </template>

    <!-- Modal Lightbox para fotos de evidencia -->
    <Teleport to="body">
      <div
        v-if="lightboxImage"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
        @click="lightboxImage = null"
      >
        <div class="relative max-h-[90vh] max-w-[90vw]" @click.stop>
          <img
            :src="formatEvidenceUrl(lightboxImage)"
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
