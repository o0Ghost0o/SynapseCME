import { ref, computed, watch, onMounted } from 'vue'
import { getClientISOString, getClientTimezone } from '~/utils/date'

export interface QueuedMessage {
  id: string
  message: string
  client_timestamp: string
  client_timezone: string
  evidence?: string | null
  conversation_id?: string | null
}

const STORAGE_KEY = 'synapse_offline_chat_queue'
const queue = ref<QueuedMessage[]>([])
const isSyncing = ref(false)

function loadQueue() {
  if (!import.meta.client) return
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      queue.value = JSON.parse(raw)
    }
  } catch {
    queue.value = []
  }
}

function persistQueue() {
  if (!import.meta.client) return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(queue.value))
  } catch {
    // localStorage quota exceeded or unavailable
  }
}

export function useChatQueue() {
  if (import.meta.client && queue.value.length === 0) {
    loadQueue()
  }

  const queuedCount = computed(() => queue.value.length)

  function enqueue(
    message: string,
    options?: { evidence?: string | null; conversation_id?: string | null },
  ): QueuedMessage {
    const item: QueuedMessage = {
      id: `offline-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      message: message.trim(),
      client_timestamp: getClientISOString(),
      client_timezone: getClientTimezone(),
      evidence: options?.evidence || null,
      conversation_id: options?.conversation_id || null,
    }
    queue.value.push(item)
    persistQueue()
    return item
  }

  function remove(id: string) {
    queue.value = queue.value.filter((i) => i.id !== id)
    persistQueue()
  }

  function clear() {
    queue.value = []
    persistQueue()
  }

  function getBatchPayload() {
    if (!queue.value.length) return null
    const messages = queue.value.map((i) => i.message).filter(Boolean)
    const oldest = queue.value[0]
    // Evidence from the latest message that had evidence
    const evidenceItem = [...queue.value].reverse().find((i) => i.evidence)
    const convItem = [...queue.value].reverse().find((i) => i.conversation_id)

    return {
      messages,
      message: messages.join('\n'),
      client_timestamp: oldest.client_timestamp,
      client_timezone: oldest.client_timezone,
      evidence: evidenceItem?.evidence || null,
      conversation_id: convItem?.conversation_id || undefined,
      client_type: 'field_app',
    }
  }

  return {
    queue,
    queuedCount,
    isSyncing,
    enqueue,
    remove,
    clear,
    getBatchPayload,
    loadQueue,
  }
}
