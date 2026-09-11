# Pitch: SynapseCME

**Inteligencia Soberana para la Base Instalada Hospitalaria**

### 1. El Problema: El punto ciego de la infraestructura médica

Todos los días, ingenieros y especialistas visitan hospitales. Ven resonadores, tomógrafos, equipos de soporte vital. Pero hoy, ese conocimiento crítico se pierde en notas personales de texto o en la memoria. El resultado es que las organizaciones tienen un "punto ciego" sobre la realidad tecnológica de sus clientes.

¿Por qué no usar IA tradicional para resolverlo? Por dos grandes barreras:

1. **Conectividad:** Los equipos médicos pesados están en sótanos o búnkeres de radiación sin internet.
2. **Privacidad:** Es información corporativa y médica altamente sensible que **no puede ni debe** enviarse a la nube (OpenAI, Anthropic, etc.).

### 2. La Solución: SynapseCME

Presentamos **SynapseCME**: una plataforma descentralizada y *agent-first* que convierte observaciones de campo no estructuradas en una base de datos GraphRAG viva, estructurada y auditable.

El ingeniero simplemente saca su dispositivo, sin importar si tiene internet, y dicta: *"Visité el Hospital Aurora, vi 2 tomógrafos GE, uno parece de hace 5 años"*. Puede adjuntar una foto y guardar el teléfono.

Eso es todo. SynapseCME hace el resto.

### 3. La Magia Técnica (Cómo funciona bajo el capó)

SynapseCME opera con una arquitectura **100% local y soberana**, impulsada por hardware NVIDIA RTX.

* **Offline-First:** Si el ingeniero está en un búnker, la PWA (Nuxt 4) encola transaccionalmente el texto, el audio y las fotos comprimidas. Al recuperar la red, sincroniza atómicamente.
* **Inferencia Especializada:** Utilizando el **SDK de QVAC**, el audio se transcribe localmente (faster-whisper) y el texto pasa por **MedPsy (Q4_K_M)**. Este modelo especializado extrae las entidades exactas (modalidad, marca, antigüedad) sin tocar una sola API en la nube.
* **GraphRAG y Consenso:** Los datos no van a una tabla plana, van a un **Grafo Neo4j**. Si dos ingenieros reportan el mismo equipo en diferentes meses, el sistema genera un consenso ponderado, elevando el estado del equipo de *Desconocido* a *Estimado*, *Reportado* o *Confirmado*.

### 4. Por qué SynapseCME domina los 3 Retos

**🏆 Para Philips (Inteligencia de Base Instalada):**
Resolvemos su reto de negocio al 100%. Eliminamos los formularios burocráticos. El parque instalado se actualiza hablando. Identificamos oportunidades de renovación calculando antigüedades y mostramos un Panel 360 ejecutivo en tiempo real, todo con inferencia estrictamente en el dispositivo/red local.

**🏆 Para Tether (QVAC Psy):**
Demostramos el poder de los modelos de dominio específico. Usamos **MedPsy** como motor central para la extracción de entidades médicas. Todo corre sobre hardware de consumo (RTX), reportando métricas claras de rendimiento (TTFT, throughput), y utilizando `@qvac/sdk` para inferencia y tool calling sin excusas.

**🏆 Para Sovereign Intelligence at the Edge:**
Construimos IA para lugares donde la nube simplemente no llega (búnkeres de hospitales) y donde no debería llegar (soberanía de datos sensibles). Un *gateway* único, procesamiento en el borde, y privacidad absoluta.

### 5. Hacia dónde evoluciona (El Futuro)

SynapseCME no es solo un prototipo, es la base de un ecosistema corporativo. Ya tenemos mapeada la arquitectura para integrar:

* **Firmas digitales en actas** directas en el grafo (take-off/handover).
* **Jerarquías de revisión** para trazabilidad de aprobaciones.
* **Clustering analítico** basado en los embeddings locales para predecir fallos y descubrir patrones anómalos entre hospitales de características similares.

**Cierre:**
SynapseCME demuestra que la mejor Inteligencia Artificial para el sector corporativo y médico no está en la nube; está en el borde, es privada, es experta, y escucha a tus ingenieros.

---
