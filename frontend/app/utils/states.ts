export type StateTone = 'emerald' | 'sky' | 'amber' | 'rose' | 'slate'

export function stateTone(estado?: string | null): StateTone {
  const s = (estado || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  if (s.includes('confirm')) return 'emerald'
  if (s.includes('online') || s.includes('activ')) return 'emerald'
  if (s.includes('report')) return 'sky'
  if (s.includes('estim')) return 'amber'
  if (s.includes('desconoc') || s.includes('unknown')) return 'rose'
  return 'slate'
}

export const STATE_CHIP_CLASSES: Record<StateTone, string> = {
  emerald: 'border-[#bfe8d2] bg-[#eefbf4] text-[#067647]',
  sky: 'border-[#c4ddfb] bg-[#eaf3fe] text-[#1d63d8]',
  amber: 'border-[#f2e2a8] bg-[#fffaeb] text-[#8a6100]',
  rose: 'border-[#f5a9a9] bg-[#fdf0f0] text-[#b42318]',
  slate: 'border-[#e3e8f2] bg-[#f4f6fb] text-[#7a8499]',
}

export const STATE_RING_COLORS: Record<StateTone, string> = {
  emerald: '#17b26a',
  sky: '#0284c7',
  amber: '#d99a00',
  rose: '#d92d20',
  slate: '#98a2b8',
}

/* Badges de parámetros técnicos (status inferido del texto de observación). */
export const PARAMETER_STATUS_CLASSES: Record<'ok' | 'warning' | 'critical', string> = {
  ok: 'border-[#bfe8d2] bg-[#eefbf4] text-[#067647]',
  warning: 'border-[#f2e2a8] bg-[#fffaeb] text-[#8a6100]',
  critical: 'border-[#f5a9a9] bg-[#fdf0f0] text-[#b42318]',
}

export const PARAMETER_STATUS_LABELS: Record<'ok' | 'warning' | 'critical', string> = {
  ok: 'nominal',
  warning: 'atención',
  critical: 'fuera de rango',
}
