/**
 * Utility for compressing photo evidence on the client using HTML5 Canvas.
 * Produces ~150KB JPEG base64 Data URLs suitable for localStorage and offline queueing.
 */
export async function compressImage(
  file: File,
  maxDimension = 1280,
  quality = 0.8,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const img = new Image()
      img.onload = () => {
        let { width, height } = img
        if (width > maxDimension || height > maxDimension) {
          if (width > height) {
            height = Math.round((height * maxDimension) / width)
            width = maxDimension
          } else {
            width = Math.round((width * maxDimension) / height)
            height = maxDimension
          }
        }

        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext('2d')
        if (!ctx) {
          resolve(e.target?.result as string)
          return
        }

        ctx.drawImage(img, 0, 0, width, height)
        const dataUrl = canvas.toDataURL('image/jpeg', quality)
        resolve(dataUrl)
      }
      img.onerror = () => reject(new Error('No se pudo cargar la imagen'))
      img.src = e.target?.result as string
    }
    reader.onerror = () => reject(new Error('No se pudo leer el archivo'))
    reader.readAsDataURL(file)
  })
}

/**
 * Normaliza y resuelve la URL de una foto de evidencia.
 * Soporta de forma resiliente:
 * - Data URLs base64 ('data:image/...')
 * - URLs absolutas ('http://...', 'https://...')
 * - Rutas de API ya formadas ('/api/evidence/ev_...')
 * - Rutas malformadas con prefijo duplicado ('/api/evidence//api/evidence/ev_...')
 * - Nombres de archivo puros ('ev_...')
 */
export function formatEvidenceUrl(evidence?: string | null): string {
  if (!evidence) return ''
  const trimmed = String(evidence).trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('data:') || trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return trimmed
  }

  // Extraer el nombre de archivo limpio de cualquier ruta o subruta
  const parts = trimmed.split('/').filter(Boolean)
  const filename = parts.pop()
  if (filename && (filename.startsWith('ev_') || !filename.includes(':'))) {
    return `/api/evidence/${filename}`
  }
  return trimmed.startsWith('/') ? trimmed : `/${trimmed}`
}
