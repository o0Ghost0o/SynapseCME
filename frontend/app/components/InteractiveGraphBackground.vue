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

interface SynapticPulse {
  linkIdx: number
  progress: number
  speed: number
  color: string
  forward: boolean
}

const NODES_DATA: NodeDef[] = [
  { id: 'hospital', label: 'Hospital Central', type: 'facility', color: '#38bdf8', ax: 0.16, ay: 0.18, r: 7 },
  { id: 'rtx', label: 'Inferencia RTX 4090', type: 'core', color: '#00f2fe', ax: 0.42, ay: 0.15, r: 10, isHub: true },
  { id: 'ct', label: 'Tomógrafo CT', type: 'equipment', color: '#60a5fa', ax: 0.74, ay: 0.18, r: 7 },
  { id: 'rm', label: 'Resonancia Magnética', type: 'equipment', color: '#818cf8', ax: 0.88, ay: 0.32, r: 6 },
  { id: 'consensus', label: 'Consenso Ponderado', type: 'consensus', color: '#34d399', ax: 0.26, ay: 0.36, r: 8 },
  { id: 'graphrag', label: 'GraphRAG Core', type: 'core', color: '#00f2fe', ax: 0.60, ay: 0.38, r: 11, isHub: true },
  { id: 'params', label: 'Parámetros Técnicos', type: 'param', color: '#a78bfa', ax: 0.82, ay: 0.52, r: 6 },
  { id: 'observation', label: 'Observación en Campo', type: 'obs', color: '#38bdf8', ax: 0.45, ay: 0.58, r: 7 },
  { id: 'ponderation', label: 'Algoritmo de Confianza', type: 'calc', color: '#2dd4bf', ax: 0.14, ay: 0.52, r: 6 },
  { id: 'db', label: 'Base Instalada Neo4j', type: 'db', color: '#00f2fe', ax: 0.70, ay: 0.72, r: 8 },
  { id: 'edge', label: 'Nodo Edge On-Premise', type: 'hardware', color: '#60a5fa', ax: 0.88, ay: 0.80, r: 7 },
  { id: 'audit', label: 'Auditoría PostgreSQL', type: 'audit', color: '#a78bfa', ax: 0.35, ay: 0.78, r: 6 },
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
const pulses: SynapticPulse[] = []

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
      speedX: 0.0008 + (i % 3) * 0.00025,
      speedY: 0.0007 + (i % 4) * 0.0002,
      ampX: 12 + (i % 5) * 4,
      ampY: 10 + (i % 4) * 3,
      isResetting: false,
      scale: 1,
    })
  })
}

function initPulses() {
  pulses.length = 0
  const count = 6
  for (let i = 0; i < count; i++) {
    pulses.push({
      linkIdx: Math.floor(Math.random() * LINKS_DATA.length),
      progress: Math.random(),
      speed: 0.0003 + Math.random() * 0.0004,
      color: i % 2 === 0 ? '#00f2fe' : '#4facfe',
      forward: Math.random() > 0.5,
    })
  }
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
    initPulses()
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
    const hitRadius = Math.max(node.def.r + 16, 28)
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
    const margin = 20
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

  const K_SPRING = 45
  const DAMPING = 6

  nodes.forEach((node, i) => {
    const driftX = Math.sin(timestamp * node.speedX + node.phaseX) * node.ampX
    const driftY = Math.cos(timestamp * node.speedY + node.phaseY) * node.ampY
    const targetX = node.def.ax * width + driftX
    const targetY = node.def.ay * height + driftY

    const isDragged = draggedNodeIndex === i
    const isHovered = hoveredNodeIndex === i

    const targetScale = isDragged ? 1.45 : isHovered ? 1.35 : 1.0
    node.scale += (targetScale - node.scale) * 0.15

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

      if (Math.hypot(dx, dy) < 0.6 && Math.hypot(node.vx, node.vy) < 0.6) {
        node.isResetting = false
        node.x = targetX
        node.y = targetY
        node.vx = 0
        node.vy = 0
      }
    } else {
      let desiredX = targetX
      let desiredY = targetY

      if (mousePos && !isDragged) {
        const distToMouse = Math.hypot(node.x - mousePos.x, node.y - mousePos.y)
        const magnetRadius = 85
        if (distToMouse < magnetRadius) {
          const pull = (1 - distToMouse / magnetRadius) * 20
          const angle = Math.atan2(mousePos.y - node.y, mousePos.x - node.x)
          desiredX += Math.cos(angle) * pull
          desiredY += Math.sin(angle) * pull
        }
      }

      node.x += (desiredX - node.x) * 0.08
      node.y += (desiredY - node.y) * 0.08
    }
  })

  pulses.forEach((pulse) => {
    pulse.progress += pulse.speed * (dt * 1000)
    if (pulse.progress >= 1) {
      pulse.progress = 0
      pulse.linkIdx = Math.floor(Math.random() * LINKS_DATA.length)
      pulse.forward = Math.random() > 0.5
      pulse.speed = 0.0003 + Math.random() * 0.0004
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

  // 1. Links
  LINKS_DATA.forEach((link) => {
    const sourceNode = nodes[link.source]
    const targetNode = nodes[link.target]
    if (!sourceNode || !targetNode) return

    const isConnectedToHovered =
      hoveredNodeIndex === link.source || hoveredNodeIndex === link.target
    const isConnectedToDragged =
      draggedNodeIndex === link.source || draggedNodeIndex === link.target

    ctx!.save()
    if (isConnectedToDragged) {
      ctx!.strokeStyle = 'rgba(0, 242, 254, 0.85)'
      ctx!.lineWidth = 2.4
      ctx!.shadowColor = '#00f2fe'
      ctx!.shadowBlur = 12
    } else if (isConnectedToHovered) {
      ctx!.strokeStyle = 'rgba(0, 242, 254, 0.6)'
      ctx!.lineWidth = 1.8
      ctx!.shadowColor = '#00f2fe'
      ctx!.shadowBlur = 8
    } else {
      ctx!.strokeStyle = 'rgba(148, 178, 255, 0.22)'
      ctx!.lineWidth = 1.0
      ctx!.shadowBlur = 0
    }

    ctx!.beginPath()
    ctx!.moveTo(sourceNode.x, sourceNode.y)
    ctx!.lineTo(targetNode.x, targetNode.y)
    ctx!.stroke()
    ctx!.restore()
  })

  // 2. Synaptic Pulses
  pulses.forEach((pulse) => {
    const link = LINKS_DATA[pulse.linkIdx]
    if (!link) return
    const s = nodes[pulse.forward ? link.source : link.target]
    const t = nodes[pulse.forward ? link.target : link.source]
    if (!s || !t) return

    const px = s.x + (t.x - s.x) * pulse.progress
    const py = s.y + (t.y - s.y) * pulse.progress

    ctx!.save()
    ctx!.fillStyle = pulse.color
    ctx!.shadowColor = pulse.color
    ctx!.shadowBlur = 10
    ctx!.beginPath()
    ctx!.arc(px, py, 2.8, 0, Math.PI * 2)
    ctx!.fill()
    ctx!.restore()
  })

  // 3. Nodes
  nodes.forEach((node, i) => {
    const isHovered = hoveredNodeIndex === i
    const isDragged = draggedNodeIndex === i
    const currentR = node.def.r * node.scale

    ctx!.save()

    // Outer concentric pulse ring for hubs or active nodes
    if (node.def.isHub || isHovered || isDragged) {
      const pulsePhase = (timestamp * 0.002 + i) % (Math.PI * 2)
      const ringRadius = currentR + 5 + Math.sin(pulsePhase) * 3
      ctx!.beginPath()
      ctx!.arc(node.x, node.y, ringRadius, 0, Math.PI * 2)
      ctx!.strokeStyle = isDragged
        ? 'rgba(0, 242, 254, 0.7)'
        : isHovered
          ? 'rgba(0, 242, 254, 0.5)'
          : 'rgba(0, 242, 254, 0.25)'
      ctx!.lineWidth = 1.2
      ctx!.stroke()
    }

    // Glow halo
    if (isDragged) {
      ctx!.shadowColor = '#00f2fe'
      ctx!.shadowBlur = 18
    } else if (isHovered) {
      ctx!.shadowColor = node.def.color
      ctx!.shadowBlur = 14
    } else {
      ctx!.shadowColor = node.def.color
      ctx!.shadowBlur = node.def.isHub ? 8 : 4
    }

    // Node body gradient
    const grad = ctx!.createRadialGradient(
      node.x - currentR * 0.3,
      node.y - currentR * 0.3,
      currentR * 0.1,
      node.x,
      node.y,
      currentR,
    )
    grad.addColorStop(0, '#ffffff')
    grad.addColorStop(0.3, node.def.color)
    grad.addColorStop(1, '#0e244d')

    ctx!.beginPath()
    ctx!.arc(node.x, node.y, currentR, 0, Math.PI * 2)
    ctx!.fillStyle = grad
    ctx!.fill()

    // Outer border stroke
    ctx!.strokeStyle = isDragged ? '#ffffff' : node.def.color
    ctx!.lineWidth = 1.5
    ctx!.stroke()

    ctx!.restore()
  })

  // 4. Tooltip for Hovered / Dragged Node
  const activeIdx = draggedNodeIndex !== null ? draggedNodeIndex : hoveredNodeIndex
  if (activeIdx !== null && nodes[activeIdx]) {
    const activeNode = nodes[activeIdx]
    const label = activeNode.def.label
    const isDragging = draggedNodeIndex === activeIdx
    const subtext = isDragging ? 'Arrastrando (suelta para reiniciar)' : 'Nodo GraphRAG'

    ctx!.save()
    ctx!.font = '600 11px system-ui, -apple-system, sans-serif'
    const textMetrics = ctx!.measureText(label)
    const boxW = Math.max(textMetrics.width + 24, 110)
    const boxH = 36
    const boxX = Math.max(8, Math.min(width - boxW - 8, activeNode.x - boxW / 2))
    const boxY = activeNode.y - activeNode.def.r * activeNode.scale - boxH - 12

    // Tooltip background
    ctx!.fillStyle = 'rgba(14, 22, 48, 0.92)'
    ctx!.strokeStyle = isDragging ? 'rgba(0, 242, 254, 0.8)' : 'rgba(56, 189, 248, 0.4)'
    ctx!.lineWidth = 1
    ctx!.shadowColor = '#00f2fe'
    ctx!.shadowBlur = 10
    drawRoundedRect(ctx!, boxX, boxY, boxW, boxH, 8)
    ctx!.fill()
    ctx!.stroke()

    // Dot indicator
    ctx!.shadowBlur = 0
    ctx!.fillStyle = activeNode.def.color
    ctx!.beginPath()
    ctx!.arc(boxX + 12, boxY + 14, 3.5, 0, Math.PI * 2)
    ctx!.fill()

    // Label
    ctx!.fillStyle = '#f8fafc'
    ctx!.fillText(label, boxX + 22, boxY + 17)

    // Subtitle
    ctx!.font = '500 9.5px system-ui, -apple-system, sans-serif'
    ctx!.fillStyle = isDragging ? '#00f2fe' : '#94a3b8'
    ctx!.fillText(subtext, boxX + 12, boxY + 29)

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
