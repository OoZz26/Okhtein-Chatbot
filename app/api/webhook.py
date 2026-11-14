"""POST /webhook: receives WAHA events. Verify, map, acknowledge at once, process in the background."""

import hashlib
import hmac
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request

from app.bootstrap import build_incoming_message_service
from app.core.config import get_settings
from app.infra.whatsapp.waha_mapper import map_webhook
from app.services.incoming_message_service import IncomingMessageService

logger = logging.getLogger(__name__)
router = APIRouter()


def get_incoming_message_service() -> IncomingMessageService:
    """FastAPI dependency. Tests replace it through `app.dependency_overrides`."""
    return build_incoming_message_service()


def get_hmac_key() -> str:
    return get_settings().waha_webhook_hmac_key


def is_valid_signature(body: bytes, signature: str | None, key: str) -> bool:
    if not key or not signature:
        return False  # fail closed: no key configured means nobody is authenticated
    expected = hmac.new(key.encode(), body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    service: Annotated[IncomingMessageService, Depends(get_incoming_message_service)],
    hmac_key: Annotated[str, Depends(get_hmac_key)],
    x_webhook_hmac: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    body = await request.body()
    if not is_valid_signature(body, x_webhook_hmac, hmac_key):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        event: Any = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Body is not valid JSON") from exc
    message = map_webhook(event) if isinstance(event, dict) else None
    if message is None:
        return {"status": "ignored"}
    background_tasks.add_task(service.handle, message)
    return {"status": "accepted"}
