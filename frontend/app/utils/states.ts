export type StateTone = 'emerald' | 'sky' | 'amber' | 'rose' | 'slate'

export function stateTone(estado?: string | null): StateTone {
  const s = (estado || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  if (s.includes('confirm')) return 'emerald'
  if (s.includes('report')) return 'sky'
  if (s.includes('estim')) return 'amber'
  if (s.includes('desconoc') || s.includes('unknown')) return 'rose'
  return 'slate'
}

export const STATE_CHIP_CLASSES: Record<StateTone, string> = {
  emerald: 'border-emerald-300/30 bg-emerald-400/15 text-emerald-200',
  sky: 'border-sky-300/30 bg-sky-400/15 text-sky-200',
  amber: 'border-amber-300/30 bg-amber-400/15 text-amber-200',
  rose: 'border-rose-300/30 bg-rose-400/15 text-rose-200',
  slate: 'border-slate-300/20 bg-slate-400/10 text-slate-300',
}

export const STATE_RING_COLORS: Record<StateTone, string> = {
  emerald: '#34d399',
  sky: '#38bdf8',
  amber: '#fbbf24',
  rose: '#fb7185',
  slate: '#94a3b8',
}
