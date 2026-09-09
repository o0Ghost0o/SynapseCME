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
└──────┬──────────────┬───────────────────┘
       │              │
┌──────▼─────────┐  ┌──▼────────────────────┐
│ INFERENCIA     │  │ DATOS                 │
│ QVAC/Ollama    │  │ Neo4j (grafo)         │
│ MedPsy Q4_K_M  │  │ PostgreSQL (estado)   │
│ bge-small v1.5 │  │ + log transacciones   │
└────────────────┘  └───────────────────────┘
┌──────────────────────────────────────────┐
│ VOZ (CPU) — speaches / faster-whisper    │
│ API OpenAI-compatible (/v1/audio/...)    │
└──────────────────────────────────────────┘
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
cd backend && uv sync && uv run pytest                                          # tests unitarios (63)

# o, sin tocar tu venv, en un contenedor desechable con las dev-deps:
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm backend-test
```

## Flujo de la aplicación

1. **Captura en campo** (`/chat`): el ingeniero dicta o escribe en español — *"Visité el Hospital Aurora en Panamá, vi 3 resonancias y 2 tomógrafos, una RM tiene como 8 años"*. El agente (MedPsy con salida estructurada) extrae entidades; si el nodo de inferencia no responde, un extractor determinista en español mantiene la app operativa.

### Dictado por voz

El servicio `stt` (speaches / faster-whisper, **CPU a propósito**: la RTX se reserva para MedPsy) expone la API OpenAI-compatible de transcripciones dentro de la red interna (`http://stt:8000`). El frontend sube el audio a `POST /api/stt` (rol capturer+) y el backend lo reenvía; si el servicio no responde, el usuario recibe un 503 claro en español en menos de ~15 s. El modelo (`Systran/faster-whisper-small`, ~460 MB, configurable con `STT_MODEL`) se descarga **una sola vez** al caché persistente de HuggingFace en el primer uso. La voz es una transformación de solo lectura: no genera filas en `transaction_log` ni métricas Track 02. Existe variante CUDA (`latest-cuda`) documentada en `docker-compose.gpu.yml` por si algún día sobra VRAM.
2. **GraphRAG**: el motor traduce la extracción en mutaciones del grafo (MERGE de la jerarquía región → país → ciudad → instalación → equipo), detecta duplicados y pondera consenso entre observadores para promover estados: **Desconocido → Estimado → Reportado → Confirmado**.
3. **Panel 360** (`/dashboard`): agregado ejecutivo por región/país/instalación, cuadrícula de modalidades, antigüedad y oportunidades de renovación tecnológica.
4. **Red en vivo** (`/network`): grafo interactivo en tiempo real, clientes conectados (apps de campo, paneles) y **registro de transacciones** en vivo por WebSocket.
5. **Métricas** (`/metricas`): tabla de rendimiento Track 02.

## Autenticación y roles (RBAC)

Todo el API (salvo `/api/auth/*` y `/api/health`) exige `Authorization: Bearer <access_token>`. El token se obtiene en login y expira a los **15 minutos** (JWT HS256 firmado con `JWT_SECRET`). El **refresh token** (7 días, opaco, aleatorio) se guarda en PostgreSQL solo como **sha256** y rota en cada uso: `POST /api/auth/refresh` revoca el anterior y emite un par nuevo; reutilizar un refresh revocado devuelve 401.

| Rol | Permisos |
|---|---|
| `admin` | Todo + gestión de usuarios (`POST/GET /api/auth/users`) |
| `capturer` | Captura de campo (`POST /api/chat`) + todas las lecturas |
| `viewer` | Solo lectura (jerarquía, facilidad, red, métricas, transacciones). `/api/chat` → **403** |

Errores en español: sin token / token inválido → 401; rol insuficiente → 403.

**La identidad capturadora es siempre la del JWT** — el campo `contributor` del cliente se ignora: el nodo Contributor, las relaciones `MADE_BY` y el `actor` de `transaction_log` usan el usuario autenticado. En el WebSocket, el `hello` debe incluir el token: `{"type":"hello","token":"...","client_type":"...","name":"..."}`; conexiones no autenticadas reciben un evento `error` en español y se cierran (código 4401). El usuario se recarga de la base de datos en cada request, así que deshabilitarlo (`disabled`) tiene efecto inmediato.

**Admin inicial:** si la tabla `users` está vacía, el arranque crea un administrador desde `ADMIN_USER` / `ADMIN_PASSWORD` (por defecto `admin` / `synapse-admin`) y lo advierte en los logs — cámbialo en producción. Las tablas `users` y `refresh_tokens` se crean idempotentemente en cada arranque del backend (`db.ensure_schema`), así que despliegues con datos previos no dependen de re-ejecutar `init.sql`.

```bash
# login → access_token + refresh_token
curl -s -X POST localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"synapse-admin"}'

# crear un usuario capturador (requiere rol admin)
curl -s -X POST localhost:8000/api/auth/users \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"username":"marina.solis","password":"synapse-dev","full_name":"Marina Solís","role":"capturer"}'
```

Los usuarios del seed sintético (`data/synthetic/seed.py`) se crean con rol `capturer` y contraseña documentada `synapse-dev` (solo desarrollo).

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

`POST /api/auth/login|refresh|logout` · `GET /api/auth/me` · `POST/GET /api/auth/users` (admin) · `POST /api/chat` (SSE, capturer+) · `POST /api/stt` (multipart audio → texto, capturer+) · `GET /api/facility/{id}` · `GET /api/hierarchy` · `GET /api/network` · `GET /api/metrics` · `GET /api/transactions` (+ `/export.csv`) · `WS /ws/events` (hello con token) · `GET /api/health`

## Licencia

[MIT](LICENSE)
