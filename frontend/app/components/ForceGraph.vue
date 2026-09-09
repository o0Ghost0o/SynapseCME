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
const activePulse = ref<string | null>(null)

const TYPE_COLORS: Record<string, string> = {
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
  if (t.includes('region') || t.includes('country') || t.includes('pais')) return 15
  if (t.includes('instal') || t.includes('facility') || t.includes('hospital')) return 12
  return 9
}

function runSimulation() {
  const ids = props.nodes.map((n) => n.id)
  const pos = new Map<string, SimPoint>()
  ids.forEach((id, i) => {
    const angle = (i / Math.max(ids.length, 1)) * Math.PI * 2
    pos.set(id, { x: Math.cos(angle) * 170, y: Math.sin(angle) * 170, vx: 0, vy: 0 })
  })

  const pairs = props.links.filter((l) => pos.has(l.source) && pos.has(l.target))
  const REPULSION = 5200
  const SPRING_LEN = 110
  const SPRING_K = 0.03
  const GRAVITY = 0.012

  for (let iter = 0; iter < 260; iter++) {
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
        const force = Math.min(REPULSION / distSq, 30)
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        a.vx += fx
        a.vy += fy
        b.vx -= fx
        b.vy -= fy
      }
    }
    for (const l of pairs) {
      const a = pos.get(l.source)!
      const b = pos.get(l.target)!
      const dx = b.x - a.x
      const dy = b.y - a.y
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
      const force = (dist - SPRING_LEN) * SPRING_K
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      a.vx += fx
      a.vy += fy
      b.vx -= fx
      b.vy -= fy
    }
    for (const p of pos.values()) {
      p.vx -= p.x * GRAVITY
      p.vy -= p.y * GRAVITY
      const speed = Math.sqrt(p.vx * p.vx + p.vy * p.vy)
      if (speed > 12) {
        p.vx = (p.vx / speed) * 12
        p.vy = (p.vy / speed) * 12
      }
      p.x += p.vx
      p.y += p.vy
      p.vx *= 0.82
      p.vy *= 0.82
    }
  }

  // Centrar el resultado
  if (ids.length) {
    let cx = 0
    let cy = 0
    for (const p of pos.values()) {
      cx += p.x
      cy += p.y
    }
    cx /= ids.length
    cy /= ids.length
    for (const p of pos.values()) {
      p.x -= cx
      p.y -= cy
    }
  }
  positions.value = pos
}

let pulseTimer: ReturnType<typeof setTimeout> | undefined

watch(
  () => [props.nodes, props.links] as const,
  () => runSimulation(),
  { deep: true, immediate: true },
)

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

function point(id: string): SimPoint {
  return positions.value.get(id) ?? { x: 0, y: 0, vx: 0, vy: 0 }
}

function nodeById(id: string): GraphNode | undefined {
  return props.nodes.find((n) => n.id === id)
}
</script>

<template>
  <svg
    :viewBox="`${-W / 2} ${-H / 2} ${W} ${H}`"
    class="h-full w-full select-none"
    preserveAspectRatio="xMidYMid meet"
    role="img"
    aria-label="Grafo de red de instalaciones"
  >
    <g>
      <line
        v-for="(link, i) in links"
        :key="`l-${i}`"
        :x1="point(link.source).x"
        :y1="point(link.source).y"
        :x2="point(link.target).x"
        :y2="point(link.target).y"
        class="stroke-white/20"
        stroke-width="1.2"
      />
    </g>
    <g v-for="node in nodes" :key="node.id">
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
        class="cursor-pointer transition hover:fill-opacity-100"
        @mouseenter="hovered = node"
        @mouseleave="hovered = null"
      />
      <text
        v-if="nodes.length <= 80"
        :x="point(node.id).x"
        :y="point(node.id).y + radiusFor(node.type) + 14"
        text-anchor="middle"
        class="fill-slate-300 text-[10px]"
      >
        {{ (node.label || node.id).slice(0, 22) }}
      </text>
      <title>{{ node.label || node.id }} — {{ node.type || 'nodo' }}{{ node.state ? ` · ${node.state}` : '' }}</title>
    </g>
    <g v-if="hovered" pointer-events="none">
      <rect
        :x="point(hovered.id).x + 14"
        :y="point(hovered.id).y - 34"
        rx="10"
        width="190"
        height="44"
        class="fill-slate-900/85 stroke-white/15"
      />
      <text :x="point(hovered.id).x + 26" :y="point(hovered.id).y - 17" class="fill-white text-xs font-semibold">
        {{ hovered.label || hovered.id }}
      </text>
      <text :x="point(hovered.id).x + 26" :y="point(hovered.id).y - 3" class="fill-slate-300 text-[10px]">
        {{ hovered.type || 'nodo' }}{{ hovered.state ? ` · ${hovered.state}` : '' }}
      </text>
    </g>
  </svg>
</template>
