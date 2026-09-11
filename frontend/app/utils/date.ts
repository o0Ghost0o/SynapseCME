/**
 * Client-side date and timezone helpers for SynapseCME.
 * Ensures consistent timezone-aware display across chat, equipment timeline, and API payloads.
 */

export function getClientTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

export function getClientISOString(date: Date = new Date()): string {
  return date.toISOString()
}

export function parseDateSafe(input?: string | Date | null): Date | null {
  if (!input) return null
  if (input instanceof Date) return Number.isNaN(input.getTime()) ? null : input
  const d = new Date(input)
  return Number.isNaN(d.getTime()) ? null : d
}

export function formatClientTime(input?: string | Date | null): string {
  const d = parseDateSafe(input)
  if (!d) return '—'
  return d.toLocaleTimeString('es-ES', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatClientRelative(input?: string | Date | null): string {
  const d = parseDateSafe(input)
  if (!d) return '—'

  const now = new Date()
  const timeStr = formatClientTime(d)

  // Compare calendar days in local timezone
  const isToday =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()

  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const isYesterday =
    d.getFullYear() === yesterday.getFullYear() &&
    d.getMonth() === yesterday.getMonth() &&
    d.getDate() === yesterday.getDate()

  if (isToday) {
    return `hoy · ${timeStr}`
  }
  if (isYesterday) {
    return `ayer · ${timeStr}`
  }

  // Same year: "11 sep · 14:32", Different year: "11 sep 2025 · 14:32"
  const day = d.getDate()
  const month = d.toLocaleDateString('es-ES', { month: 'short' }).replace('.', '')
  if (d.getFullYear() === now.getFullYear()) {
    return `${day} ${month} · ${timeStr}`
  }
  return `${day} ${month} ${d.getFullYear()} · ${timeStr}`
}
