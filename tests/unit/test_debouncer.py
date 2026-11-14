import asyncio

from app.services.debouncer import Debouncer
from tests.fakes import InMemoryBuffer, InMemoryLock, instant, quick_yield

CHAT = "201001234567@c.us"


class Replies:
    """Collects what the debouncer hands to the reply logic, plus start/end markers for ordering."""

    def __init__(self, work_seconds: float = 0.0) -> None:
        self.replies: list[tuple[str, str]] = []
        self.timeline: list[str] = []
        self._work = work_seconds

    async def __call__(self, chat_id: str, text: str, sender_name: str) -> None:
        self.timeline.append(f"start:{text}")
        if self._work:
            await asyncio.sleep(self._work)
        self.replies.append((chat_id, text))
        self.timeline.append(f"end:{text}")


async def test_three_quick_messages_get_exactly_one_reply_addressing_all_of_them() -> None:
    replies = Replies()
    debouncer = Debouncer(InMemoryBuffer(), InMemoryLock(), replies, 2.0, 1.0, sleep=instant)

    for text in ("hi", "I want a bag", "for a wedding"):
        await debouncer.submit(CHAT, text)
    await debouncer.wait_idle()

    assert replies.replies == [(CHAT, "hi\nI want a bag\nfor a wedding")]


async def test_submit_returns_immediately_and_the_reply_comes_later() -> None:
    replies = Replies()
    debouncer = Debouncer(InMemoryBuffer(), InMemoryLock(), replies, 2.0, 1.0, sleep=instant)

    await debouncer.submit(CHAT, "hi")

    assert replies.replies == []  # nothing yet: the quiet period has not elapsed
    await debouncer.wait_idle()
    assert replies.replies == [(CHAT, "hi")]


async def test_bursts_in_different_chats_do_not_mix() -> None:
    replies = Replies()
    debouncer = Debouncer(InMemoryBuffer(), InMemoryLock(), replies, 2.0, 1.0, sleep=instant)

    await debouncer.submit("a@c.us", "from a")
    await debouncer.submit("b@c.us", "from b")
    await debouncer.wait_idle()

    assert sorted(replies.replies) == [("a@c.us", "from a"), ("b@c.us", "from b")]


async def test_two_bursts_racing_on_one_chat_never_interleave() -> None:
    replies = Replies(work_seconds=0.05)  # generating a reply takes a while
    debouncer = Debouncer(InMemoryBuffer(), InMemoryLock(), replies, 0.0, 5.0, sleep=quick_yield)

    await debouncer.submit(CHAT, "burst one")
    while "start:burst one" not in replies.timeline:  # wait until reply one is being generated
        await asyncio.sleep(0.005)
    await debouncer.submit(CHAT, "burst two")  # arrives while the first reply is still in flight
    await debouncer.wait_idle()

    assert replies.timeline == ["start:burst one", "end:burst one", "start:burst two", "end:burst two"]
    assert [text for _, text in replies.replies] == ["burst one", "burst two"]  # no duplicates, no merge


async def test_the_lock_is_released_even_when_the_reply_fails() -> None:
    lock = InMemoryLock()

    async def boom(chat_id: str, text: str, sender_name: str) -> None:
        raise RuntimeError("reply failed")

    debouncer = Debouncer(InMemoryBuffer(), lock, boom, 0.0, 1.0, sleep=instant)
    await debouncer.submit(CHAT, "hi")
    await debouncer.wait_idle()

    assert lock.held == {}  # a crashed reply must not block the chat forever


async def test_it_gives_up_when_the_lock_is_never_freed() -> None:
    replies = Replies()
    lock = InMemoryLock()
    await lock.acquire(CHAT)  # someone else holds it, forever
    debouncer = Debouncer(InMemoryBuffer(), lock, replies, 0.0, 0.5, sleep=instant)

    await debouncer.submit(CHAT, "hi")
    await debouncer.wait_idle()

    assert replies.replies == []


async def test_the_sender_name_is_passed_along() -> None:
    seen: list[str] = []

    async def capture(chat_id: str, text: str, sender_name: str) -> None:
        seen.append(sender_name)

    debouncer = Debouncer(InMemoryBuffer(), InMemoryLock(), capture, 0.0, 1.0, sleep=instant)
    await debouncer.submit(CHAT, "hi", "Sara")
    await debouncer.wait_idle()

    assert seen == ["Sara"]
