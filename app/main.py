"""FastAPI application factory. Run with: uvicorn app.main:app --reload"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import chat, health
from app.domain.errors import ConfigurationError, LLMError

logger = logging.getLogger(__name__)


async def _llm_unavailable(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "The assistant is unavailable right now."})


async def _misconfigured(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Configuration problem: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = FastAPI(title="Okhtein WhatsApp Bot")
    app.include_router(health.router)
    app.include_router(chat.router)
    app.add_exception_handler(LLMError, _llm_unavailable)
    app.add_exception_handler(ConfigurationError, _misconfigured)
    return app


app = create_app()
