from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from hestia.api.routes import chat, health
from hestia.config import HestiaConfig, load_config
from hestia.core.llm.ollama import OllamaProvider
from hestia.core.mnemosyne import Mnemosyne
from hestia.core.orchestrator import Orchestrator
from hestia.core.tools.registry import ToolRegistry
from hestia.modules.loader import load_modules, teardown_modules
from hestia.security.rate_limit import limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    registry = ToolRegistry()
    modules = await load_modules(config, registry)
    llm = OllamaProvider(config.llm)
    memory = Mnemosyne()
    orchestrator = Orchestrator(config, llm, registry, memory)

    app.state.config = config
    app.state.orchestrator = orchestrator
    app.state.modules = modules
    app.state.llm = llm

    logger.info("Hestia started on %s:%s", config.server.host, config.server.port)
    yield

    await teardown_modules(modules)
    await llm.close()
    logger.info("Hestia shut down")


def create_app(config: HestiaConfig | None = None) -> FastAPI:
    app = FastAPI(
        title="Hestia",
        description="Local-first home assistant AI",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    if config is None:
        config = load_config()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.security.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chat.router)

    pythia_dist = config.pythia_dist
    if pythia_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(pythia_dist), html=True), name="pythia")

    return app
