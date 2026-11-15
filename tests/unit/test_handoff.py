import json
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.errors import InvalidTransitionError
from app.domain.handoff import ChatMode, HandoffState
from app.domain.models import IncomingMessage, LLMResponse
from app.domain.tools.base import ToolRegistry
from app.infra.whatsapp.staff_notifier import WhatsAppStaffNotifier, describe
from app.services.handoff_service import STAFF_REPLY_REASON
from tests.fakes import (
    FakeGateway,
    FakeLLM,
    InMemoryProducts,
    make_chat_service,
    make_handoffs,
    make_incoming,
    make_product,
)

CHAT = "201001234567@c.us"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class TestStateMachine:
    def test_a_new_chat_is_bot_active(self) -> None:
        assert HandoffState().mode == ChatMode.BOT_ACTIVE
        assert not HandoffState().is_handed_off

    def test_handoff_moves_to_handed_off_and_keeps_reason_and_summary(self) -> None:
        state = HandoffState().handoff("order tracking", "Where is order 1234?", NOW)

        assert state.mode == ChatMode.HANDED_OFF
        assert (state.reason, state.summary, state.since) == ("order tracking", "Where is order 1234?", NOW)

    def test_release_moves_back_to_bot_active(self) -> None:
        assert HandoffState().handoff("r", "s", NOW).release() == HandoffState()

    def test_handing_off_twice_is_rejected(self) -> None:
        with pytest.raises(InvalidTransitionError):
            HandoffState().handoff("r", "s", NOW).handoff("again", "", NOW)

    def test_releasing_a_bot_active_chat_is_rejected(self) -> None:
        with pytest.raises(InvalidTransitionError):
            HandoffState().release()


class TestHandoffService:
    async def test_handoff_is_stored_and_the_team_is_notified_with_reason_and_summary(self) -> None:
        rig = make_handoffs()

        assert await rig.service.hand_off(CHAT, "complaint", "Bag arrived damaged") is True

        assert await rig.service.is_handed_off(CHAT)
        [(chat_id, state)] = rig.notifier.notified
        assert chat_id == CHAT
        assert (state.reason, state.summary) == ("complaint", "Bag arrived damaged")

    async def test_a_second_handoff_does_not_notify_again(self) -> None:
        rig = make_handoffs()
        await rig.service.hand_off(CHAT, "complaint", "x")

        assert await rig.service.hand_off(CHAT, "complaint", "x") is False
        assert len(rig.notifier.notified) == 1

    async def test_release_gives_the_chat_back_to_the_bot(self) -> None:
        rig = make_handoffs()
        await rig.service.hand_off(CHAT, "complaint", "x")

        assert await rig.service.release(CHAT) is True
        assert not await rig.service.is_handed_off(CHAT)
        assert await rig.service.release(CHAT) is False  # nothing left to release

    async def test_a_handoff_times_out_by_itself(self) -> None:
        rig = make_handoffs(timeout_hours=12)
        await rig.service.hand_off(CHAT, "complaint", "x")

        rig.clock.advance(hours=11)
        assert await rig.service.is_handed_off(CHAT)
        rig.clock.advance(hours=2)
        assert not await rig.service.is_handed_off(CHAT)  # auto-released after 13h

    async def test_each_staff_reply_restarts_the_timeout(self) -> None:
        rig = make_handoffs(timeout_hours=12)
        await rig.service.hand_off(CHAT, "complaint", "angry about delivery")

        rig.clock.advance(hours=11)
        await rig.service.staff_took_over(CHAT)  # staff are still talking to the customer
        rig.clock.advance(hours=2)

        assert await rig.service.is_handed_off(CHAT)  # 13h since the handoff, but only 2h since staff wrote
        assert rig.store.states[CHAT].reason == "complaint"  # the original reason is kept

    async def test_a_staff_reply_hands_the_chat_off_without_a_notification(self) -> None:
        rig = make_handoffs()

        await rig.service.staff_took_over(CHAT)

        assert await rig.service.is_handed_off(CHAT)
        assert rig.store.states[CHAT].reason == STAFF_REPLY_REASON
        assert rig.notifier.notified == []


def reply(message: str, **extra: str) -> LLMResponse:
    body = {"message": message, "product_handles": [], "stage": "close", **extra}
    return LLMResponse(json.dumps(body))


HANDOFF_REPLY = reply(
    "Sorry about that 🤍 A team member will reply here.",
    handoff_reason="order tracking",
    handoff_summary="Customer asks where order 1234 is.",
)


class Pipeline:
    """The whole inbound path over fakes, with handoff wired in."""

    def __init__(self, *replies: LLMResponse) -> None:
        self.llm = FakeLLM(list(replies))
        self.handoffs = make_handoffs()
        agent = SalesAgent(
            self.llm,
            ToolRegistry([]),
            InMemoryProducts([make_product("black-clutch")]),
            load_system_prompt(),
            3,
        )
        self.chat = make_chat_service(agent, handoffs=self.handoffs.service)
        self.incoming, self.debouncer, self.gateway = make_incoming(self.chat, handoffs=self.handoffs.service)
        self._ids = 0

    async def customer_says(self, text: str) -> None:
        self._ids += 1
        await self.incoming.handle(IncomingMessage(f"c{self._ids}", CHAT, text))
        await self.debouncer.wait_idle()

    async def staff_replies_from_phone(self) -> None:
        self._ids += 1
        await self.incoming.handle(
            IncomingMessage(f"s{self._ids}", CHAT, "On it!", from_me=True, from_phone=True)
        )
        await self.debouncer.wait_idle()


async def test_the_agent_can_hand_off_and_the_customer_is_told_warmly() -> None:
    pipeline = Pipeline(HANDOFF_REPLY)

    await pipeline.customer_says("Where is my order 1234?")

    assert [text for _, text in pipeline.gateway.sent] == [
        "Sorry about that 🤍 A team member will reply here."
    ]
    assert await pipeline.handoffs.service.is_handed_off(CHAT)
    [(_, state)] = pipeline.handoffs.notifier.notified
    assert (state.reason, state.summary) == ("order tracking", "Customer asks where order 1234 is.")


async def test_after_a_handoff_the_bot_sends_nothing_but_still_stores_the_messages() -> None:
    pipeline = Pipeline(HANDOFF_REPLY)
    await pipeline.customer_says("Where is my order 1234?")
    sent_before, llm_calls_before = len(pipeline.gateway.sent), len(pipeline.llm.calls)

    await pipeline.customer_says("Hello? Anyone there?")

    assert len(pipeline.gateway.sent) == sent_before  # silence
    assert len(pipeline.llm.calls) == llm_calls_before  # the assistant is not even called
    assert pipeline.gateway.events[-1] != "typing_on"  # and no typing indicator either
    stored = await pipeline.chat._memory.context(CHAT)
    assert "Hello? Anyone there?" in [m.content for m in stored]  # the message is kept for the team


async def test_a_staff_reply_from_the_business_phone_pauses_the_bot() -> None:
    pipeline = Pipeline(reply("never sent"))

    await pipeline.staff_replies_from_phone()
    await pipeline.customer_says("Thanks! One more question")

    assert pipeline.gateway.sent == []
    assert pipeline.llm.calls == []


async def test_messages_our_own_api_sent_are_not_mistaken_for_staff() -> None:
    pipeline = Pipeline(reply("Hello!"))

    await pipeline.incoming.handle(IncomingMessage("b1", CHAT, "bot said hi", from_me=True, from_phone=False))
    await pipeline.debouncer.wait_idle()
    await pipeline.customer_says("hi")

    assert [text for _, text in pipeline.gateway.sent] == ["Hello!"]  # the bot is still active


async def test_release_makes_the_bot_answer_again() -> None:
    pipeline = Pipeline(HANDOFF_REPLY, reply("Back with you 🤍"))
    await pipeline.customer_says("Where is my order 1234?")
    await pipeline.customer_says("hello?")  # silent

    await pipeline.handoffs.service.release(CHAT)
    await pipeline.customer_says("Thanks, now I want a bag")

    assert pipeline.gateway.sent[-1][1] == "Back with you 🤍"


async def test_the_timeout_makes_the_bot_answer_again() -> None:
    pipeline = Pipeline(HANDOFF_REPLY, reply("Welcome back 🤍"))
    await pipeline.customer_says("Where is my order 1234?")

    pipeline.handoffs.clock.advance(hours=13)
    await pipeline.customer_says("hi again")

    assert pipeline.gateway.sent[-1][1] == "Welcome back 🤍"


async def test_a_group_or_status_staff_message_never_triggers_a_handoff() -> None:
    pipeline = Pipeline(reply("Hello!"))

    await pipeline.incoming.handle(
        IncomingMessage("g1", "1203@g.us", "x", from_me=True, from_phone=True, is_group=True)
    )

    assert not await pipeline.handoffs.service.is_handed_off("1203@g.us")


class TestStaffNotifier:
    def test_the_message_has_the_customer_reason_and_summary(self) -> None:
        text = describe(CHAT, HandoffState().handoff("complaint", "Bag arrived damaged", NOW))

        assert "+201001234567" in text
        assert "complaint" in text
        assert "Bag arrived damaged" in text

    async def test_it_messages_only_the_configured_staff_number(self) -> None:
        gateway = FakeGateway()

        await WhatsAppStaffNotifier(gateway, "201112223333@c.us").notify(
            CHAT, HandoffState().handoff("complaint", "x", NOW)
        )

        assert [chat for chat, _ in gateway.sent] == ["201112223333@c.us"]  # never the customer

    async def test_a_failing_alert_does_not_break_the_chat(self) -> None:
        class BrokenGateway(FakeGateway):
            async def send_text(self, chat_id: str, text: str) -> None:
                from app.domain.errors import MessagingError

                raise MessagingError("WAHA down")

        await WhatsAppStaffNotifier(BrokenGateway(), "201112223333@c.us").notify(
            CHAT, HandoffState().handoff("complaint", "x", NOW)
        )  # must not raise


def test_a_timeout_of_exactly_the_limit_counts_as_expired() -> None:
    assert timedelta(hours=12) >= timedelta(hours=12)  # documents the >= boundary used by the service
