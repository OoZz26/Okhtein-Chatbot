import httpx
import pytest

from app.api.admin import get_admin_api_key, get_handoff_service
from app.main import create_app
from tests.fakes import HandoffRig, make_handoffs

CHAT = "201001234567@c.us"
KEY = "admin-secret"


def client_for(rig: HandoffRig, key: str = KEY) -> httpx.AsyncClient:
    app = create_app()
    app.dependency_overrides[get_handoff_service] = lambda: rig.service
    app.dependency_overrides[get_admin_api_key] = lambda: key
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def rig() -> HandoffRig:
    return make_handoffs()


async def test_release_gives_the_chat_back_to_the_bot(rig: HandoffRig) -> None:
    await rig.service.hand_off(CHAT, "complaint", "x")

    async with client_for(rig) as client:
        response = await client.post(f"/admin/chats/{CHAT}/release", headers={"X-Admin-Key": KEY})

    assert response.status_code == 200
    assert response.json() == {"chat_id": CHAT, "released": True}
    assert not await rig.service.is_handed_off(CHAT)


async def test_releasing_a_chat_that_is_not_handed_off_says_so(rig: HandoffRig) -> None:
    async with client_for(rig) as client:
        response = await client.post(f"/admin/chats/{CHAT}/release", headers={"X-Admin-Key": KEY})

    assert response.json()["released"] is False


@pytest.mark.parametrize("headers", [{}, {"X-Admin-Key": "wrong"}])
async def test_a_missing_or_wrong_key_is_rejected_and_nothing_is_released(
    rig: HandoffRig, headers: dict[str, str]
) -> None:
    await rig.service.hand_off(CHAT, "complaint", "x")

    async with client_for(rig) as client:
        response = await client.post(f"/admin/chats/{CHAT}/release", headers=headers)

    assert response.status_code == 401
    assert await rig.service.is_handed_off(CHAT)


async def test_the_endpoint_is_closed_when_no_admin_key_is_configured(rig: HandoffRig) -> None:
    await rig.service.hand_off(CHAT, "complaint", "x")

    async with client_for(rig, key="") as client:
        response = await client.post(f"/admin/chats/{CHAT}/release", headers={"X-Admin-Key": ""})

    assert response.status_code == 503
    assert await rig.service.is_handed_off(CHAT)
