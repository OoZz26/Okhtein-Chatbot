"""Admin endpoints for the team. Protected by a shared API key; closed entirely when no key is configured."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from app.bootstrap import build_handoff_service
from app.core.config import get_settings
from app.services.handoff_service import HandoffService

router = APIRouter(prefix="/admin")


def get_handoff_service() -> HandoffService:
    """FastAPI dependency. Tests replace it through `app.dependency_overrides`."""
    return build_handoff_service()


def get_admin_api_key() -> str:
    return get_settings().admin_api_key


def require_admin(
    configured_key: Annotated[str, Depends(get_admin_api_key)],
    x_admin_key: Annotated[str | None, Header()] = None,
) -> None:
    if not configured_key:
        raise HTTPException(status_code=503, detail="Admin API is disabled: set ADMIN_API_KEY")
    if x_admin_key is None or not hmac.compare_digest(configured_key, x_admin_key):
        raise HTTPException(status_code=401, detail="Invalid admin key")


@router.post("/chats/{chat_id}/release", dependencies=[Depends(require_admin)])
async def release_chat(
    chat_id: str, handoffs: Annotated[HandoffService, Depends(get_handoff_service)]
) -> dict[str, object]:
    """Give a handed-off chat back to the bot."""
    released = await handoffs.release(chat_id)
    return {"chat_id": chat_id, "released": released}
