<script setup lang="ts">
interface NodeDef {
  id: string
  label: string
  type: string
  color: string
  ax: number // normalized anchor X [0, 1]
  ay: number // normalized anchor Y [0, 1]
  r: number
  isHub?: boolean
}

interface ActiveNode {
  def: NodeDef
  x: number
  y: number
  vx: number
  vy: number
  phaseX: number
  phaseY: number
  speedX: number
  speedY: number
  ampX: number
  ampY: number
  isResetting: boolean
  scale: number
}

interface LinkDef {
  source: number
  target: number
}

// Nodes styled with the flat palette from synapse-dark.svg
const NODES_DATA: NodeDef[] = [
  { id: 'hospital', label: 'Hospital Central', type: 'facility', color: '#4facfe', ax: 0.16, ay: 0.18, r: 6 },
  { id: 'rtx', label: 'Inferencia RTX 4090', type: 'core', color: '#00f2fe', ax: 0.42, ay: 0.15, r: 8, isHub: true },
  { id: 'ct', label: 'Tomógrafo CT', type: 'equipment', color: '#4facfe', ax: 0.74, ay: 0.18, r: 6 },
  { id: 'rm', label: 'Resonancia Magnética', type: 'equipment', color: '#94a3b8', ax: 0.88, ay: 0.32, r: 5 },
  { id: 'consensus', label: 'Consenso Ponderado', type: 'consensus', color: '#00f2fe', ax: 0.26, ay: 0.36, r: 7 },
  { id: 'graphrag', label: 'GraphRAG Core', type: 'core', color: '#00f2fe', ax: 0.60, ay: 0.38, r: 9, isHub: true },
  { id: 'params', label: 'Parámetros Técnicos', type: 'param', color: '#94a3b8', ax: 0.82, ay: 0.52, r: 5 },
  { id: 'observation', label: 'Observación en Campo', type: 'obs', color: '#4facfe', ax: 0.45, ay: 0.58, r: 6 },
  { id: 'ponderation', label: 'Algoritmo de Confianza', type: 'calc', color: '#94a3b8', ax: 0.14, ay: 0.52, r: 5 },
  { id: 'db', label: 'Base Instalada Neo4j', type: 'db', color: '#00f2fe', ax: 0.70, ay: 0.72, r: 7 },
  { id: 'edge', label: 'Nodo Edge On-Premise', type: 'hardware', color: '#4facfe', ax: 0.88, ay: 0.80, r: 6 },
  { id: 'audit', label: 'Auditoría PostgreSQL', type: 'audit', color: '#94a3b8', ax: 0.35, ay: 0.78, r: 5 },
]

const LINKS_DATA: LinkDef[] = [
  { source: 0, target: 1 },
  { source: 1, target: 2 },
  { source: 2, target: 3 },
  { source: 0, target: 4 },
  { source: 1, target: 4 },
  { source: 1, target: 5 },
  { source: 2, target: 5 },
  { source: 3, target: 6 },
  { source: 4, target: 5 },
  { source: 4, target: 7 },
  { source: 5, target: 6 },
  { source: 5, target: 7 },
  { source: 6, target: 9 },
  { source: 4, target: 8 },
  { source: 7, target: 8 },
  { source: 7, target: 9 },
  { source: 7, target: 11 },
  { source: 6, target: 10 },
  { source: 9, target: 10 },
  { source: 9, target: 11 },
  { source: 0, target: 8 },
]

const containerRef = ref<HTMLDivElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)

let ctx: CanvasRenderingContext2D | null = null
let animationFrameId = 0
let resizeObserver: ResizeObserver | null = null

let width = 0
let height = 0

const nodes: ActiveNode[] = []

let hoveredNodeIndex: number | null = null
let draggedNodeIndex: number | null = null
let mousePos: { x: number; y: number } | null = null
let lastTime = 0

function initNodes() {
  nodes.length = 0
  NODES_DATA.forEach((def, i) => {
    const px = def.ax * width
    const py = def.ay * height
    nodes.push({
      def,
      x: px,
      y: py,
      vx: 0,
      vy: 0,
      phaseX: i * 1.37,
      phaseY: i * 2.19,
      // Very gentle, calm, slow idle movement
      speedX: 0.0003 + (i % 3) * 0.0001,
      speedY: 0.00025 + (i % 4) * 0.0001,
      ampX: 2.5 + (i % 3) * 1.0,
      ampY: 2.0 + (i % 2) * 1.0,
      isResetting: false,
      scale: 1,
    })
  })
}

function resize() {
  if (!containerRef.value || !canvasRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return

  width = rect.width
  height = rect.height
  const dpr = Math.min(window.devicePixelRatio || 1, 2)

  canvasRef.value.width = Math.round(width * dpr)
  canvasRef.value.height = Math.round(height * dpr)
  canvasRef.value.style.width = `${width}px`
  canvasRef.value.style.height = `${height}px`

  ctx = canvasRef.value.getContext('2d')
  if (ctx) {
    ctx.scale(dpr, dpr)
  }

  if (nodes.length === 0) {
    initNodes()
  } else {
    nodes.forEach((node) => {
      if (!node.isResetting && draggedNodeIndex === null) {
        node.x = node.def.ax * width
        node.y = node.def.ay * height
      }
    })
  }
}

function getPointerPos(e: PointerEvent): { x: number; y: number } {
  if (!canvasRef.value) return { x: 0, y: 0 }
  const rect = canvasRef.value.getBoundingClientRect()
  return {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top,
  }
}

function findNodeAt(pos: { x: number; y: number }): number | null {
  for (let i = nodes.length - 1; i >= 0; i--) {
    const node = nodes[i]
    const hitRadius = Math.max(node.def.r + 14, 24)
    const dist = Math.hypot(node.x - pos.x, node.y - pos.y)
    if (dist <= hitRadius) {
      return i
    }
  }
  return null
}

function onPointerDown(e: PointerEvent) {
  const pos = getPointerPos(e)
  const idx = findNodeAt(pos)
  if (idx !== null) {
    draggedNodeIndex = idx
    const node = nodes[idx]
    node.isResetting = false
    node.vx = 0
    node.vy = 0
    node.x = pos.x
    node.y = pos.y
    if (canvasRef.value) {
      canvasRef.value.setPointerCapture(e.pointerId)
      canvasRef.value.style.cursor = 'grabbing'
    }
  }
}

function onPointerMove(e: PointerEvent) {
  const pos = getPointerPos(e)
  mousePos = pos

  if (draggedNodeIndex !== null) {
    const node = nodes[draggedNodeIndex]
    const margin = 16
    node.x = Math.max(margin, Math.min(width - margin, pos.x))
    node.y = Math.max(margin, Math.min(height - margin, pos.y))
    node.vx = 0
    node.vy = 0
  } else {
    hoveredNodeIndex = findNodeAt(pos)
    if (canvasRef.value) {
      canvasRef.value.style.cursor = hoveredNodeIndex !== null ? 'grab' : 'default'
    }
  }
}

function onPointerUp(e: PointerEvent) {
  if (draggedNodeIndex !== null) {
    const node = nodes[draggedNodeIndex]
    node.isResetting = true
    if (canvasRef.value) {
      try {
        canvasRef.value.releasePointerCapture(e.pointerId)
      } catch {
        // pointer capture already released
      }
      canvasRef.value.style.cursor = hoveredNodeIndex !== null ? 'grab' : 'default'
    }
    draggedNodeIndex = null
  }
}

function onPointerLeave() {
  if (draggedNodeIndex === null) {
    hoveredNodeIndex = null
    mousePos = null
    if (canvasRef.value) {
      canvasRef.value.style.cursor = 'default'
    }
  }
}

function updatePhysics(timestamp: number) {
  if (!lastTime) lastTime = timestamp
  const dt = Math.min((timestamp - lastTime) / 1000, 0.05)
  lastTime = timestamp

  const K_SPRING = 55
  const DAMPING = 8

  nodes.forEach((node, i) => {
    // Subtle idle drift target
    const driftX = Math.sin(timestamp * node.speedX + node.phaseX) * node.ampX
    const driftY = Math.cos(timestamp * node.speedY + node.phaseY) * node.ampY
    const targetX = node.def.ax * width + driftX
    const targetY = node.def.ay * height + driftY

    const isDragged = draggedNodeIndex === i
    const isHovered = hoveredNodeIndex === i

    const targetScale = isDragged ? 1.35 : isHovered ? 1.25 : 1.0
    node.scale += (targetScale - node.scale) * 0.2

    if (isDragged) {
      return
    }

    if (node.isResetting) {
      const dx = node.x - targetX
      const dy = node.y - targetY

      const ax = -K_SPRING * dx - DAMPING * node.vx
      const ay = -K_SPRING * dy - DAMPING * node.vy

      node.vx += ax * dt
      node.vy += ay * dt

      node.x += node.vx * dt
      node.y += node.vy * dt

      if (Math.hypot(dx, dy) < 0.5 && Math.hypot(node.vx, node.vy) < 0.5) {
        node.isResetting = false
        node.x = targetX
        node.y = targetY
        node.vx = 0
        node.vy = 0
      }
    } else {
      // Subtle organic settling to target
      node.x += (targetX - node.x) * 0.1
      node.y += (targetY - node.y) * 0.1
    }
  })
}

function drawRoundedRect(
  c: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  radius: number,
) {
  c.beginPath()
  c.moveTo(x + radius, y)
  c.lineTo(x + w - radius, y)
  c.quadraticCurveTo(x + w, y, x + w, y + radius)
  c.lineTo(x + w, y + h - radius)
  c.quadraticCurveTo(x + w, y + h, x + w - radius, y + h)
  c.lineTo(x + radius, y + h)
  c.quadraticCurveTo(x, y + h, x, y + h - radius)
  c.lineTo(x, y + radius)
  c.quadraticCurveTo(x, y, x + radius, y)
  c.closePath()
}

function render(timestamp: number) {
  if (!ctx || width <= 0 || height <= 0) {
    animationFrameId = requestAnimationFrame(render)
    return
  }

  updatePhysics(timestamp)

  ctx.clearRect(0, 0, width, height)

  // 1. Flat Links (matching synapse-dark.svg stroke #334155 and active #00f2fe)
  LINKS_DATA.forEach((link) => {
    const sourceNode = nodes[link.source]
    const targetNode = nodes[link.target]
    if (!sourceNode || !targetNode) return

    const isConnectedToHovered =
      hoveredNodeIndex === link.source || hoveredNodeIndex === link.target
    const isConnectedToDragged =
      draggedNodeIndex === link.source || draggedNodeIndex === link.target

    ctx!.beginPath()
    ctx!.moveTo(sourceNode.x, sourceNode.y)
    ctx!.lineTo(targetNode.x, targetNode.y)

    if (isConnectedToDragged) {
      ctx!.strokeStyle = '#00f2fe'
      ctx!.lineWidth = 2.0
    } else if (isConnectedToHovered) {
      ctx!.strokeStyle = '#38bdf8'
      ctx!.lineWidth = 1.6
    } else {
      ctx!.strokeStyle = 'rgba(51, 65, 85, 0.7)' // #334155 base stroke
      ctx!.lineWidth = 1.2
    }

    ctx!.stroke()
  })

  // 2. Flat Nodes (clean vector styling from synapse-dark.svg)
  nodes.forEach((node, i) => {
    const isHovered = hoveredNodeIndex === i
    const isDragged = draggedNodeIndex === i
    const currentR = node.def.r * node.scale

    // Interactive ring on hover/drag
    if (isHovered || isDragged) {
      ctx!.beginPath()
      ctx!.arc(node.x, node.y, currentR + 3.5, 0, Math.PI * 2)
      ctx!.strokeStyle = '#00f2fe'
      ctx!.lineWidth = 1.5
      ctx!.stroke()
    }

    // Flat filled circle
    ctx!.beginPath()
    ctx!.arc(node.x, node.y, currentR, 0, Math.PI * 2)
    ctx!.fillStyle = isDragged ? '#ffffff' : node.def.color
    ctx!.fill()
  })

  // 3. Tooltip on Hover / Drag
  const activeIdx = draggedNodeIndex !== null ? draggedNodeIndex : hoveredNodeIndex
  if (activeIdx !== null && nodes[activeIdx]) {
    const activeNode = nodes[activeIdx]
    const label = activeNode.def.label
    const isDragging = draggedNodeIndex === activeIdx
    const subtext = isDragging ? 'Soltar para reiniciar' : 'Nodo GraphRAG'

    ctx!.save()
    ctx!.font = '600 11px system-ui, -apple-system, sans-serif'
    const textMetrics = ctx!.measureText(label)
    const boxW = Math.max(textMetrics.width + 24, 105)
    const boxH = 34
    const boxX = Math.max(8, Math.min(width - boxW - 8, activeNode.x - boxW / 2))
    const boxY = activeNode.y - activeNode.def.r * activeNode.scale - boxH - 10

    // Tooltip container (flat slate background with crisp border)
    ctx!.fillStyle = 'rgba(15, 23, 42, 0.94)'
    ctx!.strokeStyle = isDragging ? '#00f2fe' : '#38bdf8'
    ctx!.lineWidth = 1
    drawRoundedRect(ctx!, boxX, boxY, boxW, boxH, 6)
    ctx!.fill()
    ctx!.stroke()

    // Dot indicator
    ctx!.fillStyle = activeNode.def.color
    ctx!.beginPath()
    ctx!.arc(boxX + 11, boxY + 13, 3, 0, Math.PI * 2)
    ctx!.fill()

    // Label
    ctx!.fillStyle = '#f8fafc'
    ctx!.fillText(label, boxX + 20, boxY + 16)

    // Subtitle
    ctx!.font = '500 9px system-ui, -apple-system, sans-serif'
    ctx!.fillStyle = isDragging ? '#00f2fe' : '#94a3b8'
    ctx!.fillText(subtext, boxX + 11, boxY + 27)

    ctx!.restore()
  }

  animationFrameId = requestAnimationFrame(render)
}

onMounted(() => {
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      resize()
    })
    resizeObserver.observe(containerRef.value)
  }
  resize()
  animationFrameId = requestAnimationFrame(render)
})

onBeforeUnmount(() => {
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId)
  }
  if (resizeObserver) {
    resizeObserver.disconnect()
  }
})
</script>

<template>
  <div ref="containerRef" class="absolute inset-0 h-full w-full overflow-hidden select-none">
    <canvas
      ref="canvasRef"
      class="h-full w-full touch-none"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @pointerleave="onPointerLeave"
    />
  </div>
</template>
