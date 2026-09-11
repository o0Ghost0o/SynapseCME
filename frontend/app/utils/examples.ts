// Ejemplos listos para pegar en la captura del chat, organizados por categoría.
// El click en un ejemplo pega el texto en el textarea sin enviarlo: el usuario
// decide cuándo enviarlo al agente.

export interface ExampleItem {
  id: string
  category: string
  label: string
  text: string
}

export interface ExampleCategory {
  id: string
  label: string
  icon: string
  examples: ExampleItem[]
}

export const EXAMPLE_CATEGORIES: ExampleCategory[] = [
  {
    id: 'mr',
    label: 'Resonancia',
    icon: 'activity',
    examples: [
      {
        id: 'mr-helio',
        category: 'Resonancia',
        label: 'Nivel de helio bajo',
        text: 'En el Hospital Aurora de Ciudad de Panamá, Panamá, hay 1 resonancia Siemens MAGNETOM Vida 3T de 6 años; el nivel de helio está al 45% (nominal 60–100%) y la presión de criógeno es normal.',
      },
      {
        id: 'mr-nominal',
        category: 'Resonancia',
        label: 'Equipo nominal',
        text: 'El Hospital Istmo en David, Panamá, tiene 2 resonancias Philips Ingenia Elition X de 3 años, estado nominal, sin desviaciones de campo reportadas.',
      },
    ],
  },
  {
    id: 'ct',
    label: 'CT',
    icon: 'grid',
    examples: [
      {
        id: 'ct-anodo',
        category: 'CT',
        label: 'Calentamiento de ánodo',
        text: 'La Clínica del Norte en Bogotá, Colombia, tiene un CT GE Revolution EVO de 8 años; el calentamiento del ánodo es alto tras 300 cortes seguidos y el tubo tiene 1.2 millones de cortes.',
      },
      {
        id: 'ct-nominal',
        category: 'CT',
        label: 'Tubo dentro de vida útil',
        text: 'En la Clínica Monte Azul de Penonomé, Panamá, hay 1 tomógrafo Canon Aquilion Prime de 4 años, estado nominal, con 400 mil cortes en el tubo (vida útil estimada: 2 millones).',
      },
    ],
  },
  {
    id: 'us',
    label: 'Ultrasonido',
    icon: 'gauge',
    examples: [
      {
        id: 'us-sonda',
        category: 'Ultrasonido',
        label: 'Sonda con conector intermitente',
        text: 'Clínica Puerto Verde en Colón, Panamá: 2 ecógrafos Philips EPIQ Elite de 3 años, estado nominal; 1 sonda de cardiología con conector intermitente.',
      },
      {
        id: 'us-nominal',
        category: 'Ultrasonido',
        label: 'Parque nominal',
        text: 'En el Centro Médico Bahía de San José, Costa Rica, hay 3 ecógrafos GE Voluson E10 de 2 años, todos con estado nominal y mantenimiento preventivo al día.',
      },
    ],
  },
  {
    id: 'xr',
    label: 'Rayos X',
    icon: 'zap',
    examples: [
      {
        id: 'xr-corriente',
        category: 'Rayos X',
        label: 'Corriente de tubo fuera de rango',
        text: 'Hospital del Faro en Cartagena, Colombia: Siemens Cios Spin, corriente del tubo a 15 mA fuera de rango (nominal 5–10 mA), requiere revisión antes de cirugía programada.',
      },
      {
        id: 'xr-nominal',
        category: 'Rayos X',
        label: 'Arco en C nominal',
        text: 'El Hospital Aurora en Ciudad de Panamá, Panamá, tiene 1 arco en C OEC Elite CFD de 5 años, estado nominal, sin desgaste anómalo en el intensificador de imagen.',
      },
    ],
  },
  {
    id: 'linac',
    label: 'Acelerador lineal',
    icon: 'shield',
    examples: [
      {
        id: 'linac-dosis',
        category: 'Acelerador lineal',
        label: 'Tasa de dosis nominal',
        text: 'Centro Médico Andino en Lima, Perú: Varian TrueBeam de 7 años, tasa de dosis 600 MU/min nominal, sin desviaciones en los chequeos mensuales.',
      },
    ],
  },
  {
    id: 'preguntas',
    label: 'Preguntas',
    icon: 'message',
    examples: [
      {
        id: 'q-fuera-rango',
        category: 'Preguntas',
        label: 'Equipos fuera de rango',
        text: '¿Qué equipos tienen parámetros fuera de rango?',
      },
      {
        id: 'q-resonancias',
        category: 'Preguntas',
        label: 'Conteo por ciudad',
        text: '¿Cuántas resonancias hay en Ciudad de Panamá?',
      },
    ],
  },
]

export const ALL_EXAMPLES: ExampleItem[] = EXAMPLE_CATEGORIES.flatMap((c) => c.examples)
