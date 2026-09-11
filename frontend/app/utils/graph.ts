/* Colores y etiquetas de los tipos de nodo del grafo de red.
 * Compartido por ForceGraph (pintado) y la leyenda de la página de red. */

export const GRAPH_TYPE_COLORS: Record<string, string> = {
  core: '#101828',
  instalacion: '#6366f1',
  facility: '#6366f1',
  hospital: '#6366f1',
  equipo: '#0284c7',
  equipment: '#0284c7',
  asset: '#0284c7',
  modelo: '#0ea5e9',
  model: '#0ea5e9',
  fabricante: '#7c3aed',
  manufacturer: '#7c3aed',
  region: '#a78bfa',
  pais: '#a78bfa',
  country: '#a78bfa',
  cliente: '#d99a00',
  client: '#d99a00',
}

/* Etiqueta legible por nivel; los alias (en/es) comparten color y etiqueta. */
export const GRAPH_TYPE_LABELS: Record<string, string> = {
  core: 'Núcleo',
  instalacion: 'Instalación',
  facility: 'Instalación',
  hospital: 'Instalación',
  equipo: 'Equipo',
  equipment: 'Equipo',
  asset: 'Equipo',
  modelo: 'Modelo',
  model: 'Modelo',
  fabricante: 'Fabricante',
  manufacturer: 'Fabricante',
  region: 'Región / País',
  pais: 'Región / País',
  country: 'Región / País',
  cliente: 'Cliente',
  client: 'Cliente',
}
