import json
from datetime import UTC, datetime

from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.discovery import CustomerProfile
from app.domain.long_term_profile import LongTermProfile, bound
from app.domain.models import ChatMessage, LLMResponse
from app.domain.profile_summarizer import LLMProfileSummarizer
from app.domain.tools.base import ToolRegistry
from tests.fakes import (
    FakeLLM,
    FakeSummarizer,
    InMemoryProducts,
    MemoryRig,
    ReturningRig,
    make_chat_service,
    make_memory,
    make_product,
    make_returning,
)

CHAT = "201001234567@c.us"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class TestLongTermProfileMerge:
    def test_newer_information_overrides_older_preferences(self) -> None:
        old = LongTermProfile(slots=CustomerProfile(colour="gold", occasion="wedding"))

        merged = old.merge_session(CustomerProfile(colour="black"), [], NOW, shown_limit=20)

        assert merged.slots.colour == "black"  # the customer changed their mind
        assert merged.slots.occasion == "wedding"  # what was not mentioned again is kept

    def test_blank_session_slots_never_erase_what_we_know(self) -> None:
        old = LongTermProfile(slots=CustomerProfile(colour="gold"))

        assert old.merge_session(CustomerProfile(), [], NOW, 20).slots.colour == "gold"

    def test_products_shown_are_unique_in_order_and_bounded(self) -> None:
        profile = LongTermProfile(products_shown=("a", "b"))

        merged = profile.merge_session(CustomerProfile(), ["b", "c", "d"], NOW, shown_limit=3)

        assert merged.products_shown == ("b", "c", "d")  # no duplicates; only the newest 3 kept

    def test_the_summary_is_bounded_and_cut_at_a_word(self) -> None:
        long_text = "Likes bold gold pieces and evening clutches " * 20

        summary = LongTermProfile().with_summary(long_text, NOW, NOW, max_chars=80).summary

        assert len(summary) <= 80
        assert summary.endswith("…")
        assert not summary.removesuffix("…").endswith(" ")

    def test_short_summaries_are_kept_whole(self) -> None:
        assert bound("Likes gold.", 80) == "Likes gold."

    def test_describe_tells_the_agent_what_is_known(self) -> None:
        text = LongTermProfile(
            slots=CustomerProfile(colour="gold"),
            summary="Likes bold pieces.",
            products_shown=("lotus-clutch",),
        ).describe()

        assert "Likes bold pieces." in text
        assert "colour: gold" in text
        assert "lotus-clutch" in text

    def test_an_empty_profile_is_empty(self) -> None:
        assert LongTermProfile().is_empty
        assert not LongTermProfile(summary="x").is_empty


class TestSummarizer:
    async def test_it_asks_the_llm_for_a_short_summary_without_links(self) -> None:
        llm = FakeLLM([LLMResponse("  Likes bold gold pieces.  ")])

        summary = await LLMProfileSummarizer(llm).summarize(
            [
                ChatMessage("user", "bold gold ring"),
                ChatMessage("assistant", "See https://eg.okhtein.com/products/x"),
            ],
            CustomerProfile(colour="gold"),
        )

        assert summary == "Likes bold gold pieces."
        prompt = llm.calls[0][1].content
        assert "bold gold ring" in prompt
        assert "https://" not in prompt  # links are noise for a summary
        assert "colour: gold" in prompt


async def visit(rig: MemoryRig, text: str, reply: str, hours_later: float = 0) -> None:
    """Record one exchange in the conversation store, optionally some hours after the previous one."""
    rig.clock.advance(hours=hours_later)
    await rig.service.record(CHAT, ChatMessage("user", text))
    await rig.service.record(CHAT, ChatMessage("assistant", reply))


class TestReturningCustomerService:
    async def test_a_first_ever_message_has_no_profile_and_no_welcome_back(self) -> None:
        returning = make_returning()

        context = await returning.service.context_for(CHAT, new_session=True)

        assert context.notes == ""
        assert not context.welcome_back
        assert returning.summarizer.calls == []

    async def test_a_new_session_summarises_the_previous_one_and_welcomes_the_customer_back(self) -> None:
        rig = make_memory()
        returning = make_returning(rig, FakeSummarizer("Likes bold gold pieces."))
        await visit(rig, "I love bold gold rings", "Here are three gold rings")
        await returning.service.remember(CHAT, CustomerProfile(colour="gold"), ["bond-ring"])

        context = await returning.service.context_for(CHAT, new_session=True)

        assert context.welcome_back
        assert "Likes bold gold pieces." in context.notes
        assert "colour: gold" in context.notes
        assert [m.content for m in returning.summarizer.calls[0]] == [
            "I love bold gold rings",
            "Here are three gold rings",
        ]

    async def test_the_same_visit_is_never_summarised_twice(self) -> None:
        rig = make_memory()
        returning = make_returning(rig)
        await visit(rig, "I love gold", "Lovely")

        await returning.service.context_for(CHAT, new_session=True)
        await returning.service.context_for(CHAT, new_session=True)

        assert len(returning.summarizer.calls) == 1  # the second new-session check found nothing new

    async def test_only_what_happened_since_the_last_summary_is_summarised(self) -> None:
        rig = make_memory()
        returning = make_returning(rig, FakeSummarizer("First visit.", "Both visits."))
        await visit(rig, "gold please", "ok")
        await returning.service.context_for(CHAT, new_session=True)

        await visit(rig, "now silver", "sure", hours_later=48)
        await returning.service.context_for(CHAT, new_session=True)

        assert [m.content for m in returning.summarizer.calls[1]] == ["now silver", "sure"]

    async def test_inside_a_live_session_there_is_no_summary_and_no_welcome(self) -> None:
        rig = make_memory()
        returning = make_returning(rig)
        await visit(rig, "gold please", "ok")
        await returning.service.remember(CHAT, CustomerProfile(colour="gold"), [])

        context = await returning.service.context_for(CHAT, new_session=False)

        assert not context.welcome_back
        assert "colour: gold" in context.notes  # still known, just no greeting
        assert returning.summarizer.calls == []

    async def test_a_single_hello_is_not_worth_summarising(self) -> None:
        rig = make_memory()
        returning = make_returning(rig)
        await rig.service.record(CHAT, ChatMessage("user", "hi"))

        await returning.service.context_for(CHAT, new_session=True)

        assert returning.summarizer.calls == []

    async def test_a_failing_summarizer_never_blocks_the_conversation(self) -> None:
        rig = make_memory()
        returning = make_returning(rig, FakeSummarizer(fail=True))
        await visit(rig, "I love gold", "Lovely")
        await returning.service.remember(CHAT, CustomerProfile(colour="gold"), [])

        context = await returning.service.context_for(CHAT, new_session=True)

        assert context.welcome_back  # still welcomed, from the slots alone
        assert "colour: gold" in context.notes

    async def test_a_long_visit_is_summarised_from_its_end_where_taste_is_clearest(self) -> None:
        rig = make_memory()
        returning = make_returning(rig)
        for i in range(35):  # 70 messages, more than the 60 a summary reads
            await visit(rig, f"message {i}", "ok")
        await visit(rig, "actually I prefer silver now", "Silver it is")

        await returning.service.context_for(CHAT, new_session=True)

        summarised = [m.content for m in returning.summarizer.calls[0]]
        assert len(summarised) == 60
        assert summarised[-2:] == ["actually I prefer silver now", "Silver it is"]  # the end is never skipped

    async def test_a_slow_summary_does_not_hold_up_the_first_reply(self) -> None:
        rig = make_memory()
        returning = make_returning(rig, FakeSummarizer("Likes gold.", delay=0.2), summary_wait_seconds=0.01)
        await visit(rig, "I love gold", "Lovely")
        await returning.service.remember(CHAT, CustomerProfile(colour="gold"), [])

        context = await returning.service.context_for(CHAT, new_session=True)

        assert context.welcome_back and "colour: gold" in context.notes  # welcomed back from the slots
        assert "Likes gold." not in context.notes  # the summary was not ready yet...
        await returning.service.wait_idle()
        assert returning.profiles.profiles[CHAT].summary == "Likes gold."  # ...and is stored for later

    async def test_slots_saved_while_the_summary_runs_are_not_overwritten(self) -> None:
        rig = make_memory()
        returning = make_returning(rig, FakeSummarizer("Likes gold.", delay=0.05), summary_wait_seconds=0.0)
        await visit(rig, "I love gold", "Lovely")

        await returning.service.context_for(CHAT, new_session=True)
        await returning.service.remember(CHAT, CustomerProfile(colour="silver"), [])  # this turn, meanwhile
        await returning.service.wait_idle()

        stored = returning.profiles.profiles[CHAT]
        assert stored.summary == "Likes gold."
        assert stored.slots.colour == "silver"  # the summary did not erase what this turn learned

    async def test_remember_writes_through_each_turn_and_skips_empty_turns(self) -> None:
        returning: ReturningRig = make_returning()

        await returning.service.remember(CHAT, CustomerProfile(), [])
        assert CHAT not in returning.profiles.profiles  # nothing learned, nothing written

        await returning.service.remember(CHAT, CustomerProfile(colour="gold"), ["lotus-clutch"])
        await returning.service.remember(CHAT, CustomerProfile(colour="black"), ["bond-ring"])

        saved = returning.profiles.profiles[CHAT]
        assert saved.slots.colour == "black"  # newer information wins
        assert saved.products_shown == ("lotus-clutch", "bond-ring")


EMPTY = dict.fromkeys(("for_whom", "occasion", "category", "style", "colour", "practicality", "budget"), "")


def reply(message: str, handles: list[str] | None = None, **slots: str) -> LLMResponse:
    return LLMResponse(
        json.dumps(
            {
                "message": message,
                "product_handles": handles or [],
                "stage": "discover",
                "profile_updates": {**EMPTY, **slots},
            }
        )
    )


class TestReturningFlow:
    """ChatService + agent + returning-customer service together."""

    def build(self, *replies: LLMResponse) -> tuple[FakeLLM, MemoryRig, ReturningRig, object]:
        llm = FakeLLM(list(replies))
        rig = make_memory(ttl_seconds=3600)
        returning = make_returning(rig, FakeSummarizer("Likes bold gold pieces."))
        products = InMemoryProducts([make_product("bond-ring")])
        agent = SalesAgent(llm, ToolRegistry([]), products, load_system_prompt(), 3)
        chat = make_chat_service(agent, rig, returning=returning.service)
        return llm, rig, returning, chat

    async def test_after_the_session_expires_the_agent_is_told_the_customer_is_back(self) -> None:
        llm, rig, returning, chat = self.build(
            reply("Gold, lovely!", ["bond-ring"], colour="gold"), reply("Welcome back 🤍")
        )

        await chat.handle_message(CHAT, "bold gold ring please")  # type: ignore[attr-defined]
        await rig.redis.flushall()  # Redis expired...
        rig.clock.advance(hours=3)  # ...and the session TTL (1h) has passed
        await chat.handle_message(CHAT, "hi")  # type: ignore[attr-defined]

        notes = llm.calls[1][0].content.split("## Session notes")[1]
        assert "BACK for a new visit" in notes
        assert "Likes bold gold pieces." in notes  # the summary of visit one
        assert "colour: gold" in notes
        assert "bond-ring" in notes  # shown before: the agent is told not to push it again

    async def test_inside_the_same_session_the_agent_is_not_told_to_welcome_back(self) -> None:
        llm, rig, returning, chat = self.build(reply("Gold!", colour="gold"), reply("Anything else?"))

        await chat.handle_message(CHAT, "gold please")  # type: ignore[attr-defined]
        await chat.handle_message(CHAT, "and a ring")  # type: ignore[attr-defined]

        assert "BACK for a new visit" not in llm.calls[1][0].content

    async def test_a_redis_flush_inside_a_live_session_loses_neither_the_chat_nor_the_profile(self) -> None:
        llm, rig, returning, chat = self.build(reply("Gold!", colour="gold"), reply("Sure"))

        await chat.handle_message(CHAT, "gold please")  # type: ignore[attr-defined]
        await rig.redis.flushall()
        await chat.handle_message(CHAT, "still there?")  # type: ignore[attr-defined]

        second_prompt = llm.calls[1][0].content.split("## Session notes")[1]
        assert "colour: gold" in second_prompt  # preferences survive: written through to long-term memory
        assert [m.content for m in llm.calls[1][1:3]] == ["gold please", "Gold!"]  # and so does the chat

    async def test_new_information_overrides_the_old_preference_for_the_next_visit(self) -> None:
        llm, rig, returning, chat = self.build(
            reply("Gold!", colour="gold"), reply("Silver then!", colour="silver"), reply("Welcome back")
        )

        await chat.handle_message(CHAT, "gold please")  # type: ignore[attr-defined]
        await chat.handle_message(CHAT, "actually silver")  # type: ignore[attr-defined]
        await rig.redis.flushall()
        rig.clock.advance(hours=3)
        await chat.handle_message(CHAT, "hi")  # type: ignore[attr-defined]

        notes = llm.calls[2][0].content.split("## Session notes")[1]
        assert "colour: silver" in notes
        assert "colour: gold" not in notes
