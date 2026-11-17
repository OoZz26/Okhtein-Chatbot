"""Admin endpoints for the team. Protected by a shared API key; closed entirely when no key is configured."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth import require_admin
from app.bootstrap import build_handoff_service
from app.services.handoff_service import HandoffService

router = APIRouter(prefix="/admin")


def get_handoff_service() -> HandoffService:
    """FastAPI dependency. Tests replace it through `app.dependency_overrides`."""
    return build_handoff_service()


@router.post("/chats/{chat_id}/release", dependencies=[Depends(require_admin)])
async def release_chat(
    chat_id: str, handoffs: Annotated[HandoffService, Depends(get_handoff_service)]
) -> dict[str, object]:
    """Give a handed-off chat back to the bot."""
    released = await handoffs.release(chat_id)
    return {"chat_id": chat_id, "released": released}
