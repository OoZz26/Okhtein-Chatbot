"""Debug endpoints for load tests. Registered ONLY when LOAD_TEST_MODE is on (never in production)."""

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.bootstrap import build_recording_gateway
from app.infra.loadtest.fakes import RecordingGateway

router = APIRouter(prefix="/debug")


def get_recording_gateway() -> RecordingGateway:
    """FastAPI dependency. Tests replace it through `app.dependency_overrides`."""
    return build_recording_gateway()


@router.get("/sent")
async def sent(gateway: Annotated[RecordingGateway, Depends(get_recording_gateway)]) -> list[dict[str, Any]]:
    """Everything the fake gateway 'sent', oldest first, so a load test can verify the replies."""
    return [asdict(send) for send in gateway.sends]


@router.post("/reset")
async def reset(gateway: Annotated[RecordingGateway, Depends(get_recording_gateway)]) -> dict[str, str]:
    gateway.reset()
    return {"status": "reset"}
