<script setup lang="ts">
export interface ConversationSummary {
  id: string
  title: string
  last_message_at: string
}

const props = defineProps<{
  conversations: ConversationSummary[]
  activeId: string | null
}>()

const emit = defineEmits<{
  select: [id: string]
  remove: [id: string]
  create: []
}>()

function relDate(iso: string): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const mins = Math.floor((Date.now() - t) / 60000)
  if (mins < 1) return 'ahora'
  if (mins < 60) return `hace ${mins} min`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `hace ${hours} h`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'ayer'
  return `hace ${days} días`
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col">
    <div class="flex items-center justify-between gap-2 p-3">
      <h2 class="text-sm font-semibold uppercase tracking-wider text-slate-400">
        Conversaciones
      </h2>
      <button
        class="btn-ghost px-3 py-1.5 text-xs"
        data-testid="new-conversation"
        title="Nueva conversación"
        @click="emit('create')"
      >
        ＋ Nueva
      </button>
    </div>
    <ul class="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
      <li v-for="conv in props.conversations" :key="conv.id">
        <div
          class="group flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors"
          :class="
            conv.id === props.activeId
              ? 'border border-indigo-300/30 bg-indigo-400/15'
              : 'border border-transparent hover:bg-white/5'
          "
          :data-testid="'conversation-item'"
          role="button"
          tabindex="0"
          @click="emit('select', conv.id)"
          @keydown.enter="emit('select', conv.id)"
        >
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm" :class="conv.id === props.activeId ? 'text-white' : 'text-slate-200'">
              {{ conv.title.trim() || 'Nueva conversación' }}
            </p>
            <p class="mt-0.5 text-[11px] text-slate-500">{{ relDate(conv.last_message_at) }}</p>
          </div>
          <button
            class="shrink-0 rounded-lg px-2 py-1 text-xs text-slate-500 opacity-0 transition-opacity hover:bg-rose-400/15 hover:text-rose-300 focus:opacity-100 group-hover:opacity-100"
            :data-testid="'delete-conversation'"
            :aria-label="`Eliminar conversación ${conv.title.trim() || 'nueva'}`"
            @click.stop="emit('remove', conv.id)"
          >
            🗑
          </button>
        </div>
      </li>
      <li v-if="!props.conversations.length" class="px-3 py-6 text-center text-xs text-slate-500">
        Todavía no hay conversaciones.<br />Enviá una observación para empezar.
      </li>
    </ul>
  </div>
</template>
