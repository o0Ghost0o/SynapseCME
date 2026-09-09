# SynapseCME

Plataforma descentralizada, *agent-first*, que convierte observaciones de campo no estructuradas sobre equipamiento hospitalario en una base de datos **GraphRAG** viva, estructurada y confiable. Toda la inferencia corre **on-edge** con QVAC/Ollama sobre hardware local NVIDIA RTX — cero APIs de nube, privacidad absoluta.

## Arquitectura

```
┌─────────────────────────────────────────┐
│  CLIENTE — Nuxt 4 (Web / Capacitor)     │
│  Captura agente · Panel 360 · Red viva  │
└──────────────┬──────────────────────────┘
               │  red local (REST + SSE + WS)
┌──────────────▼──────────────────────────┐
│  BACKEND — FastAPI (uv)                 │
│  Agente GraphRAG · tool calling · WS    │
└──────┬────────────────────┬─────────────┘
       │                    │
┌──────▼─────────┐  ┌───────▼────────────┐
│ INFERENCIA     │  │ DATOS              │
│ QVAC/Ollama    │  │ Neo4j (grafo)      │
│ MedPsy Q4_K_M  │  │ PostgreSQL (estado)│
│ bge-small v1.5 │  │ + log transacciones│
└────────────────┘  └────────────────────┘
```

## Hardware de referencia

| Componente | Especificación |
|---|---|
| GPU | **NVIDIA GeForce RTX 3060 Ti — 8 GB VRAM** |
| Modelo principal | MedPsy instruct, quant **Q4_K_M** (~4.5 GB) |
| Embeddings | `bge-m3` multilingüe (~1.2 GB) |
| Presupuesto VRAM residente | ≤ 6 GB (deja margen de contexto CUDA) |

> Nota: el stack corre igual en CPU (sin `docker-compose.gpu.yml`), con inferencia más lenta. Esto permite desarrollar en cualquier máquina y adoptar la GPU automáticamente al desplegar en el nodo RTX.

## Puesta en marcha

Requisitos: Docker + Docker Compose. Opcionalmente Bun (frontend en desarrollo) y uv (backend en desarrollo).

```bash
cp .env.example .env

# Cualquier máquina (CPU):
docker compose up -d

# En el nodo NVIDIA (RTX 3060 Ti):
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

El servicio QVAC **descarga los modelos automáticamente al primer arranque** (y solo si faltan en el directorio persistente): hace `ollama pull` de `medpsy:q4_k_m` y `bge-m3`. Si MedPsy no está en el registro, coloca su GGUF en `./models/medpsy.gguf` y el entrypoint lo importa con `ollama create`. `./scripts/pull-models.sh` sigue disponible para actualizaciones manuales.

Servicios: **solo el gateway es público** — `http://localhost:3000` (o `https://synapse_cme.vertexdc.com` tras tu proxy) sirve la app y enruta `/api/*` y `/ws/*` al backend. Neo4j, PostgreSQL, QVAC y el backend son internos (accesibles vía `docker compose exec` si necesitas mantenimiento; para abrir el Neo4j Browser o la API localmente, publica el puerto temporalmente en `docker-compose.yml`).

### Persistencia

Los datos sobreviven reinicios y recreación de contenedores vía bind mounts bajo `$VOLUMES_ROOT` (default `./volumes`): `neo4j/` (grafo), `postgres/` (estado operativo, métricas y log de transacciones) y `qvac/` (modelos descargados, para no repetir pulls de GB). Para borrarlo todo: `docker compose down` y elimina esos directorios del host.

### Datos sintéticos y pruebas

```bash
docker compose exec backend uv run python /app/data/synthetic/seed.py --wipe   # grafo ficticio
./scripts/e2e.sh                                                                # E2E contra el stack vivo
cd backend && uv sync && uv run pytest                                          # 43 tests unitarios
```

## Flujo de la aplicación

1. **Captura en campo** (`/chat`): el ingeniero dicta o escribe en español — *"Visité el Hospital Aurora en Panamá, vi 3 resonancias y 2 tomógrafos, una RM tiene como 8 años"*. El agente (MedPsy con salida estructurada) extrae entidades; si el nodo de inferencia no responde, un extractor determinista en español mantiene la app operativa.
2. **GraphRAG**: el motor traduce la extracción en mutaciones del grafo (MERGE de la jerarquía región → país → ciudad → instalación → equipo), detecta duplicados y pondera consenso entre observadores para promover estados: **Desconocido → Estimado → Reportado → Confirmado**.
3. **Panel 360** (`/dashboard`): agregado ejecutivo por región/país/instalación, cuadrícula de modalidades, antigüedad y oportunidades de renovación tecnológica.
4. **Red en vivo** (`/network`): grafo interactivo en tiempo real, clientes conectados (apps de campo, paneles) y **registro de transacciones** en vivo por WebSocket.
5. **Métricas** (`/metricas`): tabla de rendimiento Track 02.

## Métricas de rendimiento (Track 02)

Capturadas automáticamente por request en `perf_log` (model load time, prompt/generation tokens, TTFT, throughput) y visibles en `/api/metrics` y `/metricas`.

| Modelo | Carga (ms) | Prompt tok | Gen tok | TTFT (ms) | Throughput (tok/s) |
|---|---|---|---|---|---|
| MedPsy Q4_K_M (RTX 3060 Ti) | _pendiente: benchmark en el nodo RTX_ | | | | |

## Declaración de bases preexistentes

- App construida sobre plantillas/estándares de código propios del equipo; sin scaffolding generado de terceros con licencias restrictivas.
- Modelos: MedPsy (según términos del modelo) y `bge-m3` (MIT, BAAI) servidos localmente vía Ollama/QVAC. `bge-m3` es multilingüe (optimo para observaciones en español).
- Todos los datos del repo son **sintéticos y ficticios**; ningún dato real de clientes o pacientes.

## API (resumen)

`POST /api/chat` (SSE) · `GET /api/facility/{id}` · `GET /api/hierarchy` · `GET /api/network` · `GET /api/metrics` · `GET /api/transactions` (+ `/export.csv`) · `WS /ws/events` · `GET /api/health`

## Licencia

[MIT](LICENSE)
