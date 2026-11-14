import json

import httpx
import pytest
from pydantic import ValidationError

from app.api.debug import get_recording_gateway
from app.bootstrap import build_llm
from app.core.config import Settings
from app.infra.loadtest.fakes import CANNED_REPLY, FakeLatencyLLM, RecordingGateway
from app.main import create_app


def settings(**overrides: object) -> Settings:
    return Settings(**{"_env_file": None, **overrides})  # type: ignore[arg-type]


class TestLoadModeIsNeverProduction:
    def test_load_mode_is_refused_in_production(self) -> None:
        with pytest.raises(ValidationError, match="never be enabled"):
            settings(load_test_mode=True, environment="production")

    def test_the_check_is_case_insensitive(self) -> None:
        with pytest.raises(ValidationError):
            settings(load_test_mode=True, environment="Production")

    def test_load_mode_is_fine_in_development_and_staging(self) -> None:
        assert settings(load_test_mode=True, environment="development").load_test_mode
        assert settings(load_test_mode=True, environment="staging").load_test_mode

    def test_production_without_load_mode_is_fine_and_load_mode_is_off_by_default(self) -> None:
        assert not settings(environment="production").load_test_mode
        assert not settings().load_test_mode


class TestFakes:
    async def test_the_fake_llm_waits_then_returns_a_canned_structured_reply(self) -> None:
        response = await FakeLatencyLLM(0.0, 0.0).chat([], response_schema={"type": "object"})

        assert json.loads(response.content) == {"message": CANNED_REPLY, "product_handles": []}

    async def test_a_plain_text_request_gets_plain_text(self) -> None:
        response = await FakeLatencyLLM(0.0, 0.0).chat([])

        assert response.content == "Likes bold pieces."

    async def test_the_recording_gateway_records_instead_of_sending(self) -> None:
        gateway = RecordingGateway()

        await gateway.send_text("chat-1", "hello")
        await gateway.send_image("chat-1", "https://img/a.jpg", "*Clutch*")
        await gateway.start_typing("chat-1")  # accepted, and invisible

        assert [(s.chat_id, s.kind, s.text) for s in gateway.sends] == [
            ("chat-1", "text", "hello"),
            ("chat-1", "image", "*Clutch*"),
        ]
        gateway.reset()
        assert gateway.sends == []

    def test_load_mode_wires_the_fake_llm_so_no_api_key_is_needed(self) -> None:
        llm = build_llm(settings(load_test_mode=True, openai_api_key="", openrouter_api_key=""))

        assert isinstance(llm, FakeLatencyLLM)


class TestDebugEndpoints:
    def client(self, load_test_mode: bool, gateway: RecordingGateway) -> httpx.AsyncClient:
        app = create_app(load_test_mode=load_test_mode)
        app.dependency_overrides[get_recording_gateway] = lambda: gateway
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def test_they_do_not_exist_outside_load_mode(self) -> None:
        async with self.client(False, RecordingGateway()) as client:
            assert (await client.get("/debug/sent")).status_code == 404

    async def test_in_load_mode_they_list_and_reset_the_recorded_sends(self) -> None:
        gateway = RecordingGateway()
        await gateway.send_text("299999000001@c.us", "hi")

        async with self.client(True, gateway) as client:
            listed = (await client.get("/debug/sent")).json()
            await client.post("/debug/reset")
            after = (await client.get("/debug/sent")).json()

        assert listed == [{"chat_id": "299999000001@c.us", "kind": "text", "text": "hi"}]
        assert after == []
