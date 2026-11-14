from app.domain.models import ProductCard
from app.services.reply_sender import ReplySender
from tests.fakes import FakeGateway, NoLimit

CHAT = "201001234567@c.us"
CARD = ProductCard(
    "Black Clutch", "40,000 EGP", "https://eg.okhtein.com/products/black-clutch", "https://img/a.jpg"
)


class Sleeps:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def sender(
    gateway: FakeGateway,
    sleeps: Sleeps,
    limiter: object | None = None,
    per_char: float = 0.1,
    cap: float = 2.0,
) -> ReplySender:
    return ReplySender(gateway, limiter or NoLimit(), 3, per_char, cap, sleep=sleeps)  # type: ignore[arg-type]


async def test_typing_shows_before_each_message() -> None:
    gateway = FakeGateway()
    await sender(gateway, Sleeps()).send(CHAT, "Lovely ✨\n\nWhich colour?", [])

    assert gateway.events == ["typing_on", "text", "typing_on", "text"]


async def test_the_typing_pause_is_proportional_to_length_but_capped() -> None:
    sleeps = Sleeps()
    await sender(FakeGateway(), sleeps, per_char=0.1, cap=2.0).send(CHAT, "x" * 5 + "\n\n" + "y" * 500, [])

    assert sleeps.delays == [0.5, 2.0]  # 5 chars -> 0.5s; 500 chars would be 50s, capped at 2s


async def test_long_replies_are_split_into_at_most_three_bubbles() -> None:
    gateway = FakeGateway()
    await sender(gateway, Sleeps()).send(CHAT, "\n\n".join(f"part {i}" for i in range(6)), [])

    assert len(gateway.sent) == 3


async def test_product_cards_are_sent_as_images_after_the_text() -> None:
    gateway = FakeGateway()
    await sender(gateway, Sleeps()).send(CHAT, "Here you go", [CARD])

    assert gateway.events == ["typing_on", "text", "image"]
    assert gateway.images == [
        (
            CHAT,
            "https://img/a.jpg",
            "*Black Clutch*\n40,000 EGP\nhttps://eg.okhtein.com/products/black-clutch",
        )
    ]


async def test_an_image_failure_falls_back_to_a_text_link() -> None:
    gateway = FakeGateway(fail_images=True)
    await sender(gateway, Sleeps()).send(CHAT, "Here you go", [CARD])

    assert gateway.images == []
    assert gateway.sent[-1] == (CHAT, CARD.caption)  # same name, price and link, as text
    assert "https://eg.okhtein.com/products/black-clutch" in gateway.sent[-1][1]


class CountingLimiter:
    """Allows 2 sends, then asks callers to wait 7 seconds once, then allows again."""

    def __init__(self) -> None:
        self.calls = 0

    async def seconds_until_allowed(self) -> float:
        self.calls += 1
        return 7.0 if self.calls == 3 else 0.0


async def test_the_rate_limit_makes_the_sender_wait() -> None:
    gateway, sleeps = FakeGateway(), Sleeps()
    await sender(gateway, sleeps, CountingLimiter(), per_char=0.0).send(CHAT, "a\n\nb\n\nc", [])

    assert 7.0 in sleeps.delays  # the third message waited for the next window
    assert len(gateway.sent) == 3  # and was still sent afterwards, nothing dropped
