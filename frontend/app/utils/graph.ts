/* Colores y etiquetas de los tipos de nodo del grafo de red.
 * Compartido por ForceGraph (pintado) y la leyenda de la página de red. */

export const GRAPH_TYPE_COLORS: Record<string, string> = {
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
