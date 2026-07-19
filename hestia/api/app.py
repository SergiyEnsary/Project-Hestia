from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from hestia.api.routes import chat, echo, health
from hestia.config import HestiaConfig, load_config
from hestia.core.llm.ollama import OllamaProvider
from hestia.core.mnemosyne import Mnemosyne
from hestia.core.orchestrator import Orchestrator
from hestia.core.tools.registry import ToolRegistry
from hestia.interfaces.echo import EchoService
from hestia.modules.base import HestiaModule
from hestia.modules.loader import load_modules, teardown_modules
from hestia.security.logging import install_redacting_filters
from hestia.security.middleware import CorrelationIDMiddleware, SecurityHeadersMiddleware
from hestia.security.rate_limit import ConfigurableRateLimiter

logger = logging.getLogger(__name__)


async def validation_error_handler(
    request: Request,
    _exc: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "invalid_request",
            "correlation_id": request.state.correlation_id,
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config: HestiaConfig = app.state.config
    config.validate_runtime_safety()
    registry = ToolRegistry()
    modules: list[HestiaModule] = []
    llm: OllamaProvider | None = None
    memory: Mnemosyne | None = None
    echo_service: EchoService | None = None
    try:
        modules = await load_modules(config, registry)
        llm = OllamaProvider(config.llm)
        memory = Mnemosyne(config.mnemosyne)
        orchestrator = Orchestrator(config, llm, registry, memory)
        if config.interfaces.echo.enabled:
            echo_service = EchoService(config.interfaces.echo)
            await echo_service.start()

        app.state.orchestrator = orchestrator
        app.state.modules = modules
        app.state.llm = llm
        app.state.memory = memory
        app.state.echo = echo_service

        logger.info("Hestia started on %s:%s", config.server.host, config.server.port)
        yield
    finally:
        await teardown_modules(modules)
        if llm is not None:
            await llm.close()
        if memory is not None:
            memory.close()
        if echo_service is not None:
            await echo_service.close()
        logger.info("Hestia shut down")


def create_app(config: HestiaConfig | None = None) -> FastAPI:
    install_redacting_filters()
    if config is None:
        config = load_config()

    app = FastAPI(
        title="Hestia",
        description="Local-first home assistant AI",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.rate_limiter = ConfigurableRateLimiter()
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.security.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Hestia-Session-ID",
            "X-Request-ID",
        ],
    )
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(health.router)
    app.include_router(chat.router)
    if config.interfaces.echo.enabled:
        app.include_router(echo.router)

    pythia_dist = config.pythia_dist
    if pythia_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(pythia_dist), html=True), name="pythia")

    return app
