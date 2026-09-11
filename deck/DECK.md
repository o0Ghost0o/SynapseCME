---
marp: true
theme: default
class: invert
style: |
  section {
    background-color: #0f172a;
    font-family: 'system-ui', sans-serif;
  }
  h1 {
    color: #f8fafc;
    font-size: 3.5em;
    font-weight: 800;
  }
  h2 {
    color: #38bdf8;
    font-weight: 600;
  }
  strong {
    color: #0ea5e9;
  }
  li {
    margin-bottom: 15px;
    font-size: 1.2em;
    color: #cbd5e1;
  }
---

<!-- _class: lead -->
# Synapse**CME**
## Inteligencia Soberana para la Base Instalada Hospitalaria
Privacidad absoluta. Inferencia 100% on-edge. Cero fricción.

---

## El Punto Ciego de la Infraestructura Médica
El conocimiento de campo se pierde en notas personales o en la memoria.

* **Fricción Manual:** Documentar a mano toma tiempo y genera inconsistencias.
* **Falta de Conectividad:** Los equipos clave (resonadores, tomógrafos) operan en sótanos o búnkeres sin acceso a internet.
* **Privacidad Estricta:** La información corporativa y médica **no puede ni debe** enviarse a APIs públicas en la nube.

---

## Conoce a SynapseCME
Plataforma descentralizada y **Agent-First**.

* **Habla, no escribas:** *"Visité el Hospital Aurora, vi 2 tomógrafos GE..."*
* **Offline-First:** Captura datos en búnkeres sin red. Todo se encola localmente y se sincroniza al reconectar.
* **Privacidad 100%:** Todo se procesa localmente en hardware edge usando QVAC. Nada sale de la red del hospital.

---

## De la Voz al Grafo (Cómo funciona)

1. **Captura:** Dictado en lenguaje natural y fotos comprimidas directo desde la PWA (Nuxt 4).
2. **Inferencia Local:** Transcripción en el dispositivo y extracción de entidades clave (modalidad, marca, antigüedad) con el modelo especializado **MedPsy**.
3. **GraphRAG y Consenso:** La base de datos Neo4j cruza los reportes para detectar duplicados y elevar la confianza del equipo (*Desconocido ➔ Confirmado*).

---

## Stack 100% Local y Descentralizado

* **Cliente:** Nuxt 4 (PWA / Capacitor) con cola transaccional para resiliencia offline.
* **Backend:** FastAPI (Python) con Tool Calling y validación heurística.
* **Inferencia:** SDK de QVAC + **MedPsy (Q4_K_M)** corriendo sobre hardware NVIDIA RTX local.
* **Datos:** Neo4j (Grafos de Conocimiento) + PostgreSQL (Auditoría y Transacciones).

---

## Alineación Estratégica con los Retos

* **Philips (Base Instalada):** Elimina formularios. Crea un inventario vivo, detecta oportunidades de renovación y ofrece un panel 360 en tiempo real.
* **Tether (QVAC Psy):** Uso nativo de `@qvac/sdk` y el modelo **MedPsy** en hardware edge, con registro auditable de métricas (TTFT, throughput).
* **Sovereign Edge:** Cero APIs en la nube. Soluciona de raíz el problema de conectividad intermitente y privacidad de datos corporativos sensibles.

---

## El Futuro de SynapseCME
La mejor IA corporativa no está en la nube. Está en el borde.

* **Firmas digitales en actas:** Registro *Take-off / Handover* directamente en el grafo.
* **Clustering analítico:** Predicción de fallos y descubrimiento de patrones anómalos usando embeddings locales.
* **Jerarquías de revisión:** Trazabilidad completa de quién aprueba cada observación.
