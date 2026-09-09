"""SynapseCME FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.agent import service as agent_service
from app.agent.qvac import QvacClient
from app.api import chat, facilities, metrics, transactions, ws
from app.core.config import settings
from app.graph import engine
from app.models import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("synapse.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    db_ok = await db.init_pool(settings.postgres_dsn)
    graph_ok = engine.init_driver(settings)
    agent_service.init_client(settings)

    if graph_ok:
        with contextlib.suppress(Exception):
            await engine.bootstrap_schema()
        if not await engine.check_connectivity():
            logger.warning("Neo4j no responde; las operaciones de grafo quedarán vacías")

    prune_task = asyncio.create_task(ws.prune_presence_loop())
    logger.info(
        "SynapseCME listo (postgres=%s, neo4j=%s, qvac=%s)",
        "ok" if db_ok else "off",
        "ok" if graph_ok else "off",
        settings.qvac_base_url,
    )
    yield
    prune_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await prune_task
    await agent_service.close_client()
    await engine.close_driver()
    await db.close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="SynapseCME", version="0.1.0", lifespan=lifespan)

    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat.router)
    app.include_router(facilities.router)
    app.include_router(metrics.router)
    app.include_router(transactions.router)
    app.include_router(ws.router)

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        client: QvacClient | None = agent_service.get_client()
        models: list[str] = []
        up = False
        if client is not None:
            models = await client.list_models()
            up = bool(models) or await client.is_up()
        if not up:
            logger.warning("QVAC no disponible en %s", settings.qvac_base_url)
        return HealthResponse(status="ok", models=models, qvac="up" if up else "down")

    return app


app = create_app()
