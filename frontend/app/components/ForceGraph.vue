<script setup lang="ts">
import { STATE_RING_COLORS } from '~/utils/states'

export interface GraphNode {
  id: string
  label?: string
  type?: string
  state?: string
}

export interface GraphLink {
  source: string
  target: string
  type?: string
}

interface SimPoint {
  x: number
  y: number
  vx: number
  vy: number
}

const props = defineProps<{
  nodes: GraphNode[]
  links: GraphLink[]
  pulseId?: string | null
}>()

const W = 960
const H = 600

const positions = ref<Map<string, SimPoint>>(new Map())
const hovered = ref<GraphNode | null>(null)
const mousePos = ref<{ x: number; y: number } | null>(null)
const activePulse = ref<string | null>(null)
const svgEl = ref<SVGSVGElement | null>(null)

const TYPE_COLORS: Record<string, string> = {
  core: '#f8fafc',
  instalacion: '#818cf8',
  facility: '#818cf8',
  hospital: '#818cf8',
  equipo: '#38bdf8',
  equipment: '#38bdf8',
  asset: '#38bdf8',
  modelo: '#34d399',
  model: '#34d399',
  fabricante: '#f472b6',
  manufacturer: '#f472b6',
  region: '#a78bfa',
  pais: '#a78bfa',
  country: '#a78bfa',
  cliente: '#fbbf24',
  client: '#fbbf24',
}
const FALLBACK_PALETTE = ['#818cf8', '#38bdf8', '#34d399', '#f472b6', '#fbbf24', '#a78bfa', '#fb923c']

function colorFor(type?: string): string {
  if (!type) return '#94a3b8'
  const key = type.toLowerCase()
  if (TYPE_COLORS[key]) return TYPE_COLORS[key]
  let hash = 0
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0
  return FALLBACK_PALETTE[hash % FALLBACK_PALETTE.length]
}

function radiusFor(type?: string): number {
  const t = (type || '').toLowerCase()
  if (t === 'core') return 20
  if (t.includes('region') || t.includes('country') || t.includes('pais')) return 15
  if (t.includes('instal') || t.includes('facility') || t.includes('hospital')) return 12
  return 9
}

// ---------------------------------------------------------------------------
// Simulación física continua: se recalienta al cambiar datos o soltar un nodo
// ---------------------------------------------------------------------------

const REPULSION = 5200
const SPRING_LEN = 110
const SPRING_K = 0.03
const GRAVITY = 0.012
const MAX_SPEED = 12

let alpha = 0
let rafId = 0
/** Nodos fijados (mientras se arrastran) — no los mueve la física. */
const pinned = new Set<string>()

function seedPositions() {
  const pos = positions.value
  const seen = new Set<string>()
  props.nodes.forEach((n, i) => {
    seen.add(n.id)
    if (!pos.has(n.id)) {
      const angle = (i / Math.max(props.nodes.length, 1)) * Math.PI * 2
      pos.set(n.id, {
        x: Math.cos(angle) * 170 + (Math.random() - 0.5) * 40,
        y: Math.sin(angle) * 170 + (Math.random() - 0.5) * 40,
        vx: 0,
        vy: 0,
      })
    }
  })
  for (const id of [...pos.keys()]) {
    if (!seen.has(id)) pos.delete(id)
  }
}

function step() {
  const pos = positions.value
  const ids = [...pos.keys()]
  const pairs = props.links.filter((l) => pos.has(l.source) && pos.has(l.target))

  for (let i = 0; i < ids.length; i++) {
    for (let j = i + 1; j < ids.length; j++) {
      const a = pos.get(ids[i])!
      const b = pos.get(ids[j])!
      let dx = a.x - b.x
      let dy = a.y - b.y
      let distSq = dx * dx + dy * dy
      if (distSq < 1) {
        dx = Math.random() - 0.5
        dy = Math.random() - 0.5
        distSq = 1
      }
      const dist = Math.sqrt(distSq)
      const force = Math.min(REPULSION / distSq, 30) * alpha
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      if (!pinned.has(ids[i])) {
        a.vx += fx
        a.vy += fy
      }
      if (!pinned.has(ids[j])) {
        b.vx -= fx
        b.vy -= fy
      }
    }
  }
  for (const l of pairs) {
    const a = pos.get(l.source)!
    const b = pos.get(l.target)!
    const dx = b.x - a.x
    const dy = b.y - a.y
    const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
    const force = (dist - SPRING_LEN) * SPRING_K * alpha
    const fx = (dx / dist) * force
    const fy = (dy / dist) * force
    if (!pinned.has(l.source)) {
      a.vx += fx
      a.vy += fy
    }
    if (!pinned.has(l.target)) {
      b.vx -= fx
      b.vy -= fy
    }
  }
  for (const [id, p] of pos) {
    if (pinned.has(id)) continue
    p.vx -= p.x * GRAVITY * alpha
    p.vy -= p.y * GRAVITY * alpha
    const speed = Math.sqrt(p.vx * p.vx + p.vy * p.vy)
    if (speed > MAX_SPEED) {
      p.vx = (p.vx / speed) * MAX_SPEED
      p.vy = (p.vy / speed) * MAX_SPEED
    }
    p.x += p.vx
    p.y += p.vy
    p.vx *= 0.82
    p.vy *= 0.82
  }
}

function loop() {
  rafId = 0
  if (alpha < 0.008) return
  step()
  alpha *= 0.985
  rafId = requestAnimationFrame(loop)
}

function reheat(strength = 1) {
  alpha = Math.max(alpha, strength)
  if (!rafId) rafId = requestAnimationFrame(loop)
}

// Centrado inicial de masas tras el primer enfriamiento
function centerMass() {
  const pos = positions.value
  if (!pos.size) return
  let cx = 0
  let cy = 0
  for (const p of pos.values()) {
    cx += p.x
    cy += p.y
  }
  cx /= pos.size
  cy /= pos.size
  for (const p of pos.values()) {
    p.x -= cx
    p.y -= cy
  }
}

function rebuild() {
  seedPositions()
  centerMass()
  reheat(1)
}

watch(() => [props.nodes, props.links] as const, rebuild, { deep: true, immediate: true })

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
})

let pulseTimer: ReturnType<typeof setTimeout> | undefined

watch(
  () => props.pulseId,
  (id) => {
    if (!id) return
    activePulse.value = id
    clearTimeout(pulseTimer)
    pulseTimer = setTimeout(() => {
      activePulse.value = null
    }, 1500)
  },
)

// ---------------------------------------------------------------------------
// Arrastre + tooltip que sigue el cursor
// ---------------------------------------------------------------------------

let dragId: string | null = null

function toSvg(evt: PointerEvent): { x: number; y: number } {
  const svg = svgEl.value
  if (!svg) return { x: 0, y: 0 }
  const ctm = svg.getScreenCTM()
  if (!ctm) return { x: 0, y: 0 }
  return new DOMPoint(evt.clientX, evt.clientY).matrixTransform(ctm.inverse())
}

function onNodeDown(node: GraphNode, evt: PointerEvent) {
  evt.preventDefault()
  evt.stopPropagation()
  dragId = node.id
  pinned.add(node.id)
  hovered.value = node
  svgEl.value?.setPointerCapture(evt.pointerId)
}

function onSvgMove(evt: PointerEvent) {
  const p = toSvg(evt)
  mousePos.value = p
  if (dragId) {
    const pt = positions.value.get(dragId)
    if (pt) {
      pt.x = p.x
      pt.y = p.y
      pt.vx = 0
      pt.vy = 0
    }
  }
}

function onSvgUp(evt: PointerEvent) {
  if (dragId) {
    pinned.delete(dragId)
    dragId = null
    svgEl.value?.releasePointerCapture(evt.pointerId)
    reheat(0.5)
  }
}

function onSvgLeave() {
  if (!dragId) {
    mousePos.value = null
    hovered.value = null
  }
}

// ---------------------------------------------------------------------------
// Resaltado de vecinos
// ---------------------------------------------------------------------------

const highlightedIds = computed<Set<string> | null>(() => {
  if (!hovered.value) return null
  const set = new Set([hovered.value.id])
  for (const l of props.links) {
    if (l.source === hovered.value.id) set.add(l.target)
    if (l.target === hovered.value.id) set.add(l.source)
  }
  return set
})

function isLinkHighlighted(link: GraphLink): boolean {
  return !!hovered.value && (link.source === hovered.value.id || link.target === hovered.value.id)
}

function nodeOpacity(node: GraphNode): number {
  const hi = highlightedIds.value
  if (!hi) return 1
  return hi.has(node.id) ? 1 : 0.15
}

function linkOpacity(link: GraphLink): number {
  if (!hovered.value) return 1
  return isLinkHighlighted(link) ? 1 : 0.06
}

/** Tooltip anclado al cursor, volteado cerca del borde derecho. */
const tooltipFlip = computed(() => (mousePos.value ? mousePos.x > W / 4 : false))
const tooltipX = computed(() => {
  const m = mousePos.value
  if (!m) return 0
  return tooltipFlip.value ? m.x - 18 : m.x + 18
})
const tooltipAnchor = computed(() => (tooltipFlip.value ? 'end' : 'start'))

function point(id: string): SimPoint {
  return positions.value.get(id) ?? { x: 0, y: 0, vx: 0, vy: 0 }
}
</script>

<template>
  <svg
    ref="svgEl"
    :viewBox="`${-W / 2} ${-H / 2} ${W} ${H}`"
    class="h-full w-full touch-none select-none"
    preserveAspectRatio="xMidYMid meet"
    role="img"
    aria-label="Grafo de red de instalaciones"
    @pointermove="onSvgMove"
    @pointerup="onSvgUp"
    @pointercancel="onSvgUp"
    @pointerleave="onSvgLeave"
  >
    <g>
      <line
        v-for="(link, i) in links"
        :key="`l-${i}`"
        :x1="point(link.source).x"
        :y1="point(link.source).y"
        :x2="point(link.target).x"
        :y2="point(link.target).y"
        :class="isLinkHighlighted(link) ? 'stroke-sky-300' : 'stroke-white/20'"
        :stroke-width="isLinkHighlighted(link) ? 2.2 : 1.2"
        :opacity="linkOpacity(link)"
        class="transition-opacity duration-150"
      />
    </g>
    <g v-for="node in nodes" :key="node.id" :opacity="nodeOpacity(node)" class="transition-opacity duration-150">
      <circle
        v-if="activePulse && (node.id === activePulse || (node.label && node.label === activePulse))"
        :cx="point(node.id).x"
        :cy="point(node.id).y"
        :r="radiusFor(node.type) + 6"
        fill="none"
        :stroke="STATE_RING_COLORS[stateTone(node.state)]"
        stroke-width="2.5"
        class="pulse-ring"
      />
      <circle
        v-if="hovered && node.id === hovered.id"
        :cx="point(node.id).x"
        :cy="point(node.id).y"
        :r="radiusFor(node.type) + 7"
        :fill="colorFor(node.type)"
        opacity="0.3"
      />
      <circle
        :cx="point(node.id).x"
        :cy="point(node.id).y"
        :r="radiusFor(node.type) + 4"
        fill="none"
        :stroke="STATE_RING_COLORS[stateTone(node.state)]"
        stroke-width="1.6"
        :opacity="node.state ? 0.9 : 0"
      />
      <circle
        :cx="point(node.id).x"
        :cy="point(node.id).y"
        :r="radiusFor(node.type)"
        :fill="colorFor(node.type)"
        fill-opacity="0.85"
        stroke="rgba(255,255,255,0.55)"
        stroke-width="1"
        class="cursor-grab transition hover:fill-opacity-100 active:cursor-grabbing"
        @pointerdown="onNodeDown(node, $event)"
        @pointerenter="hovered = node"
        @pointerleave="hovered = dragId === node.id ? hovered : null"
      />
      <text
        v-if="nodes.length <= 80 || (highlightedIds && highlightedIds.has(node.id))"
        :x="point(node.id).x"
        :y="point(node.id).y + radiusFor(node.type) + 14"
        text-anchor="middle"
        class="fill-slate-300 text-[10px]"
      >
        {{ (node.label || node.id).slice(0, 22) }}
      </text>
      <title>{{ node.label || node.id }} — {{ node.type || 'nodo' }}{{ node.state ? ` · ${node.state}` : '' }}</title>
    </g>
    <g v-if="hovered && mousePos" pointer-events="none">
      <rect
        :x="tooltipFlip ? tooltipX - 204 : tooltipX"
        :y="mousePos.y - 38"
        rx="10"
        width="204"
        height="48"
        class="fill-slate-900/90 stroke-white/15"
      />
      <text :x="tooltipX" :y="mousePos.y - 21" :text-anchor="tooltipAnchor" class="fill-white text-xs font-semibold">
        {{ hovered.label || hovered.id }}
      </text>
      <text :x="tooltipX" :y="mousePos.y - 7" :text-anchor="tooltipAnchor" class="fill-slate-300 text-[10px]">
        {{ hovered.type || 'nodo' }}{{ hovered.state ? ` · ${hovered.state}` : '' }}
      </text>
    </g>
  </svg>
</template>
