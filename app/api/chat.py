"""POST /chat: thin HTTP wrapper around ChatService."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.bootstrap import build_chat_service
from app.services.chat_service import ChatService

router = APIRouter()


class ChatRequest(BaseModel):
    chat_id: str = Field(min_length=1, examples=["201001234567@c.us"])
    text: str = Field(min_length=1, examples=["I want a black clutch under 50000"])


class ChatResponse(BaseModel):
    reply: str
    product_handles: list[str]
    links: list[str]
    stage: str


def get_chat_service() -> ChatService:
    """FastAPI dependency. Tests replace it through `app.dependency_overrides`."""
    return build_chat_service()


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, service: Annotated[ChatService, Depends(get_chat_service)]) -> ChatResponse:
    result = await service.handle_message(body.chat_id, body.text)
    return ChatResponse(
        reply=result.reply,
        product_handles=result.product_handles,
        links=result.links,
        stage=result.stage.value,
    )
