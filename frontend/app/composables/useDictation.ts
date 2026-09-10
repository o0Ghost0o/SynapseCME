// Dictado por micrófono (MediaRecorder + POST /api/stt): la transcripción se
// anexa al ref de texto que se le pase. Extraído de chat.vue para reutilizarlo
// en el mini-chat de revisión de equipo.

export function useDictation(target: Ref<string>) {
  const { fetchWithAuth } = useApi()
  const { show } = useToast()

  const dictating = ref(false)
  const transcribing = ref(false)
  const recordSecs = ref(0)
  const micModal = ref<'priming' | 'denied' | null>(null)
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

  const recordTimeLabel = computed(() => {
    const m = Math.floor(recordSecs.value / 60)
    const s = (recordSecs.value % 60).toFixed(0).padStart(2, '0')
    return `${m}:${s}`
  })

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

  async function toggle() {
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

  function cancel() {
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
        target.value = target.value.trim() ? `${target.value.trim()} ${text}` : text
      }
    } catch {
      show('El servicio de dictado (STT) no está disponible')
    } finally {
      transcribing.value = false
    }
  }

  return {
    dictating,
    transcribing,
    recordTimeLabel,
    micModal,
    toggle,
    cancel,
    allowMicrophone,
  }
}
