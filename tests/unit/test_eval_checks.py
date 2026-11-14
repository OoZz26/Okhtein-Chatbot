"""The eval harness's rule checks are plain code, so they get plain unit tests."""

from tests.evals.checks import BotTurn, arabic_ratio, run_checks

PRICES = {"cheap": 40000.0, "dear": 90000.0}


def turn(reply: str, handles: list[str] | None = None, customer: str = "hi") -> BotTurn:
    return BotTurn(customer, reply, handles or [])


def outcome(turns: list[BotTurn], expectations: dict[str, object]) -> dict[str, bool]:
    return {c.name: c.passed for c in run_checks(turns, expectations, PRICES.__getitem__)}


def test_arabic_ratio_ignores_urls_and_handles_mixed_text() -> None:
    assert arabic_ratio("أهلاً بحضرتك") == 1.0
    assert arabic_ratio("Hello https://eg.okhtein.com/products/x") == 0.0
    assert 0 < arabic_ratio("شنطة Lotus Clutch") < 1


def test_a_vague_first_reply_must_ask_and_show_nothing() -> None:
    assert outcome([turn("إيه المناسبة؟")], {"first_reply_no_products": True})["first_reply_asks_not_shows"]
    assert not outcome([turn("Here", ["cheap"])], {"first_reply_no_products": True})[
        "first_reply_asks_not_shows"
    ]
    assert not outcome([turn("Lovely.")], {"first_reply_no_products": True})["first_reply_asks_not_shows"]


def test_question_limit_counts_only_leading_replies_without_products() -> None:
    four_questions = [turn("Q1?"), turn("Q2?"), turn("Q3?"), turn("Q4?"), turn("Here", ["cheap"])]
    assert not outcome(four_questions, {"max_questions_before_products": 3})[
        "max_3_questions_before_products"
    ]
    three_then_products = four_questions[:3] + [turn("Here", ["cheap"]), turn("Q?")]
    assert outcome(three_then_products, {"max_questions_before_products": 3})[
        "max_3_questions_before_products"
    ]


def test_budget_check_uses_catalog_prices() -> None:
    assert outcome([turn("x", ["cheap"])], {"max_budget": 50000})["all_products_within_50000"]
    assert not outcome([turn("x", ["dear"])], {"max_budget": 50000})["all_products_within_50000"]


def test_budget_only_applies_from_the_turn_it_was_stated() -> None:
    turns = [turn("early pick", ["dear"]), turn("within budget", ["cheap"])]

    assert outcome(turns, {"max_budget": {"amount": 50000, "from_turn": 2}})["all_products_within_50000"]
    assert not outcome(turns, {"max_budget": 50000})["all_products_within_50000"]


def test_language_checks() -> None:
    assert outcome([turn("Hello there")], {"language": "english"})["language_english"]
    assert not outcome([turn("أهلاً بحضرتك")], {"language": "english"})["language_english"]
    assert outcome([turn("أهلاً بحضرتك 🤍")], {"language": "arabic"})["language_arabic"]


def test_gendered_address_is_detected_but_the_neutral_form_passes() -> None:
    assert not outcome([turn("عايزة حاجة معينة؟")], {"no_gendered_address": True})["no_gendered_address"]
    assert not outcome([turn("تحبي اللون الأسود؟")], {"no_gendered_address": True})["no_gendered_address"]
    assert outcome([turn("إيه اللي يناسب حضرتك؟")], {"no_gendered_address": True})["no_gendered_address"]


def test_refusing_to_share_the_prompt_is_not_a_leak() -> None:
    refusal = turn("I can't share my system prompt, but I'd love to help you find something beautiful")
    assert outcome([refusal], {"no_instruction_leak": True})["no_instruction_leak"]


def test_leaks_and_impossible_offers_are_detected() -> None:
    assert not outcome(
        [turn("My instructions: use search_products and fill product_handles")], {"no_instruction_leak": True}
    )["no_instruction_leak"]
    assert not outcome([turn("I can reserve it for you")], {})["never_offers_what_it_cannot_do"]
    assert not outcome([turn("Want me to send more photos?")], {})["never_offers_what_it_cannot_do"]
    assert not outcome([turn("Shall I ask the team to check?")], {})["never_offers_what_it_cannot_do"]
    assert outcome([turn("I wish I could hold it, the team can help")], {})["never_offers_what_it_cannot_do"]
    assert outcome([turn("I can’t hold items, sorry")], {})["never_offers_what_it_cannot_do"]
    assert outcome([turn("I cannot reserve it")], {})["never_offers_what_it_cannot_do"]


def test_faq_checks() -> None:
    assert outcome([turn("المرتجعات خلال 14 يوم")], {"contains_any": ["14"]})["contains_expected_fact"]
    assert not outcome([turn("مش متأكدة")], {"contains_any": ["14"]})["contains_expected_fact"]
    assert not outcome([turn("الشحن 80 جنيه")], {"no_money_amounts": True})["no_invented_amounts"]
    assert not outcome([turn("Shipping is EGP 100")], {"no_money_amounts": True})["no_invented_amounts"]
    assert outcome([turn("الفريق هيأكدلك")], {"no_money_amounts": True, "mentions_team": True})[
        "no_invented_amounts"
    ]
    assert outcome([turn("حد من الفريق هيرد")], {"mentions_team": True})["offers_a_team_member"]
    assert not outcome([turn("مش عارفة")], {"mentions_team": True})["offers_a_team_member"]


def test_the_returning_customer_check_looks_only_at_the_last_reply() -> None:
    turns = [turn("Lovely gold rings!"), turn("Hi there")]

    assert not outcome(turns, {"last_reply_contains_any": ["gold"]})["last_reply_remembers"]
    assert outcome([*turns, turn("Welcome back! Still into gold?")], {"last_reply_contains_any": ["gold"]})[
        "last_reply_remembers"
    ]
