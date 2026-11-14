"""FastAPI application factory. Run with: uvicorn app.main:app --reload"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import bootstrap
from app.api import chat, health, webhook
from app.core.logging import configure_logging
from app.domain.errors import ConfigurationError, LLMError

logger = logging.getLogger(__name__)

Hook = Callable[[], Awaitable[None]]


async def _llm_unavailable(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "The assistant is unavailable right now."})


async def _misconfigured(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Configuration problem: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


def create_app(startup: Hook | None = None, shutdown: Hook | None = None) -> FastAPI:
    """Build the app. Startup/shutdown hooks are injected so tests can run without Docker services."""
    configure_logging()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if startup:
            await startup()
        yield
        if shutdown:
            await shutdown()

    app = FastAPI(title="Okhtein WhatsApp Bot", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(webhook.router)
    app.add_exception_handler(LLMError, _llm_unavailable)
    app.add_exception_handler(ConfigurationError, _misconfigured)
    return app


app = create_app(startup=bootstrap.init_storage, shutdown=bootstrap.close_storage)
