/* Normalizadores defensivos: el backend aún no está implementado, así que
   aceptamos varias formas de respuesta y las llevamos a una forma conocida. */

export interface HierarchyItem {
  id: string
  name: string
}

function asArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>
    for (const key of ['entries', 'items', 'regions', 'countries', 'facilities', 'results', 'data']) {
      if (Array.isArray(obj[key])) return obj[key] as unknown[]
    }
  }
  return []
}

export function normalizeHierarchy(data: unknown): HierarchyItem[] {
  return asArray(data)
    .map((item) => {
      if (typeof item === 'string') return { id: item, name: item }
      if (item && typeof item === 'object') {
        const obj = item as Record<string, unknown>
        const name = obj.name ?? obj.label ?? obj.id ?? obj.code
        return { id: String(obj.id ?? name ?? ''), name: String(name ?? 'Sin nombre') }
      }
      return { id: String(item), name: String(item) }
    })
    .filter((item) => item.name)
}

/* Árbol anidado real del backend: {regions:[{name, countries:[{name,
   facilities:[{id,name}]}]}]}. El endpoint /api/hierarchy ignora los query
   params: siempre devuelve el árbol completo. */
export interface FacilityRef {
  id: string
  name: string
}

export interface CountryNode {
  name: string
  facilities: FacilityRef[]
}

export interface RegionNode {
  name: string
  countries: CountryNode[]
}

export function normalizeHierarchyTree(data: unknown): RegionNode[] {
  if (!data || typeof data !== 'object') return []
  const regions = (data as Record<string, unknown>).regions
  if (!Array.isArray(regions)) return []
  return regions
    .filter((r) => r && typeof r === 'object')
    .map((r) => {
      const ro = r as Record<string, unknown>
      const countries = Array.isArray(ro.countries) ? ro.countries : []
      return {
        name: String(ro.name ?? ro.region ?? 'Sin nombre'),
        countries: countries
          .filter((c) => c && typeof c === 'object')
          .map((c) => {
            const co = c as Record<string, unknown>
            const facilities = Array.isArray(co.facilities) ? co.facilities : []
            return {
              name: String(co.name ?? co.country ?? 'Sin nombre'),
              facilities: facilities
                .filter((f) => f && typeof f === 'object')
                .map((f) => {
                  const fo = f as Record<string, unknown>
                  return { id: String(fo.id ?? fo.name ?? ''), name: String(fo.name ?? fo.id ?? '') }
                })
                .filter((f) => f.id),
            }
          }),
      }
    })
}

export interface EquipmentItem {
  id: string
  modality: string
  state: string
  age: number | null
  manufacturer: string
  model: string
  updatedAt: string
}

export interface FacilityInfo {
  id: string
  name: string
  city: string
  country: string
  equipment: EquipmentItem[]
}

const num = (v: unknown): number | null => {
  const n = typeof v === 'string' ? Number(v) : typeof v === 'number' ? v : NaN
  return Number.isFinite(n) && n >= 0 ? n : null
}

export function normalizeFacility(data: unknown, id: string): FacilityInfo {
  const obj = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>
  const rawEquipment = asArray(obj.equipment ?? obj.equipos ?? obj.assets ?? obj.modalities)
  return {
    id: String(obj.id ?? id),
    name: String(obj.name ?? obj.label ?? obj.installation ?? 'Instalación'),
    city: String(obj.city ?? obj.ciudad ?? ''),
    country: String(obj.country ?? obj.pais ?? ''),
    equipment: rawEquipment.map((e, i) => {
      const eo = (e && typeof e === 'object' ? e : {}) as Record<string, unknown>
      return {
        id: String(eo.id ?? `${id}-${i}`),
        modality: String(eo.modality ?? eo.modalidad ?? eo.type ?? 'Otro'),
        state: String(eo.state ?? eo.estado ?? 'desconocido'),
        age: num(eo.age ?? eo.antiguedad ?? eo.age_years ?? eo.years),
        manufacturer: String(eo.manufacturer ?? eo.fabricante ?? ''),
        model: String(eo.model ?? eo.modelo ?? ''),
        updatedAt: String(eo.updated_at ?? eo.updatedAt ?? ''),
      }
    }),
  }
}

export interface MetricEntry {
  model: string
  modelLoadMs: number | null
  promptTokens: number | null
  generationTokens: number | null
  ttftMs: number | null
  totalMs: number | null
  tps: number | null
  createdAt: string
}

export function normalizeMetrics(data: unknown): MetricEntry[] {
  return asArray(data).map((e) => {
    const obj = (e && typeof e === 'object' ? e : {}) as Record<string, unknown>
    return {
      model: String(obj.model ?? 'desconocido'),
      modelLoadMs: num(obj.model_load_ms ?? obj.modelLoadMs),
      promptTokens: num(obj.prompt_tokens ?? obj.promptTokens),
      generationTokens: num(obj.generation_tokens ?? obj.generationTokens),
      ttftMs: num(obj.ttft_ms ?? obj.ttftMs),
      totalMs: num(obj.total_ms ?? obj.totalMs),
      tps: num(obj.throughput_tps ?? obj.tps),
      createdAt: String(obj.created_at ?? obj.createdAt ?? ''),
    }
  })
}

export function avg(values: Array<number | null>): number | null {
  const valid = values.filter((v): v is number => v !== null)
  if (!valid.length) return null
  return valid.reduce((a, b) => a + b, 0) / valid.length
}

export function fmtTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function fmtDate(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function fmtNum(v: number | null, digits = 0): string {
  if (v === null) return '—'
  return v.toLocaleString('es-ES', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}
