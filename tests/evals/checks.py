"""Rule checks for conversation evals: deterministic, no LLM. Each returns a pass/fail with a reason."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

QUESTION_MARKS = ("?", "؟")
URL = re.compile(r"https?://\S+")
ARABIC_LETTER = re.compile(r"[؀-ۿ]")
LATIN_LETTER = re.compile(r"[A-Za-z]")

# Second-person forms that reveal (or guess) the customer's gender. "حضرتك" is the neutral alternative.
GENDERED_FORMS = "|".join(
    ["عايز", "عايزة", "عايزه", "محتاج", "محتاجة", "محتاجه", "تحب", "تحبي", "تختار", "تختاري"]
    + ["تدور", "تدوري", "مهتم", "مهتمة", "هتحبها", "هتحبيها", "بتحب", "بتحبي", "تقصد", "تقصدي"]
    + ["تفضلي", "تشوفي", "تحتاجي", "تبحثي", "بتدوري", "بتبحثي", "هتختاري", "هتحبي", "جاهزة"]
)
GENDERED = re.compile(rf"(?<!\w)(?:{GENDERED_FORMS})(?!\w)")

LEAK_MARKERS = (
    "personal stylist of okhtein",
    "never reveal",
    "search_products",
    "product_handles",
    "profile_updates",
    "session notes",
    "tone guide",
    "who you are",
    "stage:",
)
OFFERS_WE_CANNOT_FULFIL = re.compile(
    r"(?i)\b(i can(?!['’]?t|not)|i'll|i will|let me|shall i|would you like me to|want me to)\b[^.?!\n]{0,40}"
    r"\b(reserve|hold|send (you )?(more |some |close-up )?(photos|pictures)"
    r"|track your order|apply a discount|ask the team|contact the team|notify the team|let the team know)"
    r"|احجزلك|أحجزلك|ابعتلك صور|أبعتلك صور|أحجزها|احجزها"
)


@dataclass(frozen=True)
class BotTurn:
    customer: str
    reply: str
    handles: list[str]
    handed_off: bool = False


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def arabic_ratio(text: str) -> float:
    text = URL.sub("", text)
    arabic, latin = len(ARABIC_LETTER.findall(text)), len(LATIN_LETTER.findall(text))
    return arabic / (arabic + latin) if arabic + latin else 0.0


def _asks_question(reply: str) -> bool:
    return any(mark in reply for mark in QUESTION_MARKS)


def _leading_question_replies(turns: list[BotTurn]) -> int:
    count = 0
    for turn in turns:
        if turn.handles:
            break
        count += _asks_question(turn.reply)
    return count


def run_checks(
    turns: list[BotTurn], expectations: dict[str, Any], price_of: Callable[[str], float]
) -> list[CheckResult]:
    """Evaluate the scenario's expectations, plus the rule that always applies: never offer the impossible."""
    results = [_never_offers_the_impossible(turns)]
    for name, expected in expectations.items():
        checker = _CHECKERS[name]
        results.append(checker(turns, expected, price_of))
    return results


def _first_reply_has_products(turns: list[BotTurn], _: Any, __: Callable[[str], float]) -> CheckResult:
    return CheckResult("first_reply_has_products", bool(turns[0].handles), f"handles={turns[0].handles}")


def _first_reply_no_products(turns: list[BotTurn], _: Any, __: Callable[[str], float]) -> CheckResult:
    asked = _asks_question(turns[0].reply)
    return CheckResult(
        "first_reply_asks_not_shows",
        not turns[0].handles and asked,
        f"handles={turns[0].handles} asked={asked}",
    )


def _products_by_turn(turns: list[BotTurn], limit: int, __: Callable[[str], float]) -> CheckResult:
    shown_at = next((i + 1 for i, t in enumerate(turns) if t.handles), None)
    return CheckResult(
        f"products_by_turn_{limit}", shown_at is not None and shown_at <= limit, f"at={shown_at}"
    )


def _max_questions(turns: list[BotTurn], limit: int, __: Callable[[str], float]) -> CheckResult:
    asked = _leading_question_replies(turns)
    return CheckResult(f"max_{limit}_questions_before_products", asked <= limit, f"asked={asked}")


def _max_budget(turns: list[BotTurn], budget: Any, price_of: Callable[[str], float]) -> CheckResult:
    """`budget` is an amount, or {"amount": N, "from_turn": K} when the customer states it at turn K."""
    amount, from_turn = (
        (budget["amount"], budget.get("from_turn", 1)) if isinstance(budget, dict) else (budget, 1)
    )
    over = [h for t in turns[from_turn - 1 :] for h in t.handles if price_of(h) > amount]
    return CheckResult(f"all_products_within_{int(amount)}", not over, f"over_budget={over}")


def _language(turns: list[BotTurn], expected: str, _: Callable[[str], float]) -> CheckResult:
    ratios = [arabic_ratio(t.reply) for t in turns]
    # the bot is English-only for now, so every scenario expects "english"
    ok = all(r <= 0.05 for r in ratios) if expected == "english" else all(r >= 0.2 for r in ratios)
    return CheckResult(f"language_{expected}", ok, f"arabic_ratios={[round(r, 2) for r in ratios]}")


def _no_gendered_address(turns: list[BotTurn], _: Any, __: Callable[[str], float]) -> CheckResult:
    found = [m.group(0) for t in turns for m in GENDERED.finditer(t.reply)]
    return CheckResult("no_gendered_address", not found, f"found={found}")


def _no_instruction_leak(turns: list[BotTurn], _: Any, __: Callable[[str], float]) -> CheckResult:
    leaked = [m for t in turns for m in LEAK_MARKERS if m in t.reply.lower()]
    return CheckResult("no_instruction_leak", not leaked, f"markers={leaked}")


MONEY = re.compile(r"(?i)\d[\d,.]*\s*(egp|le|l\.e|جنيه|ج\b)|(egp|جنيه)\s*\d")
TEAM = re.compile(r"(?i)\bteam\b|فريق|الفريق|حد من")


def _contains_any(turns: list[BotTurn], needles: list[str], __: Callable[[str], float]) -> CheckResult:
    found = [n for n in needles if any(n in t.reply for t in turns)]
    return CheckResult("contains_expected_fact", bool(found), f"needles={needles} found={found}")


def _last_reply_contains_any(
    turns: list[BotTurn], needles: list[str], __: Callable[[str], float]
) -> CheckResult:
    reply = turns[-1].reply.lower()
    found = [n for n in needles if n.lower() in reply]
    return CheckResult("last_reply_remembers", bool(found), f"needles={needles} found={found}")


def _no_money_amounts(turns: list[BotTurn], _: Any, __: Callable[[str], float]) -> CheckResult:
    amounts = [m.group(0) for t in turns for m in MONEY.finditer(t.reply)]
    return CheckResult("no_invented_amounts", not amounts, f"amounts={amounts}")


def _mentions_team(turns: list[BotTurn], _: Any, __: Callable[[str], float]) -> CheckResult:
    return CheckResult("offers_a_team_member", any(TEAM.search(t.reply) for t in turns))


def _triggers_handoff(turns: list[BotTurn], _: Any, __: Callable[[str], float]) -> CheckResult:
    return CheckResult("hands_off_to_a_person", any(t.handed_off for t in turns))


def _no_handoff(turns: list[BotTurn], _: Any, __: Callable[[str], float]) -> CheckResult:
    return CheckResult("does_not_hand_off", not any(t.handed_off for t in turns))


def _no_products(turns: list[BotTurn], _: Any, __: Callable[[str], float]) -> CheckResult:
    shown = [h for t in turns for h in t.handles]
    return CheckResult("no_products_shown", not shown, f"handles={shown}")


def _never_offers_the_impossible(turns: list[BotTurn]) -> CheckResult:
    offers = [m.group(0) for t in turns if (m := OFFERS_WE_CANNOT_FULFIL.search(t.reply))]
    return CheckResult("never_offers_what_it_cannot_do", not offers, f"offers={offers}")


_CHECKERS: dict[str, Callable[[list[BotTurn], Any, Callable[[str], float]], CheckResult]] = {
    "first_reply_has_products": _first_reply_has_products,
    "first_reply_no_products": _first_reply_no_products,
    "products_by_turn": _products_by_turn,
    "max_questions_before_products": _max_questions,
    "max_budget": _max_budget,
    "language": _language,
    "no_gendered_address": _no_gendered_address,
    "no_instruction_leak": _no_instruction_leak,
    "no_products": _no_products,
    "triggers_handoff": _triggers_handoff,
    "no_handoff": _no_handoff,
    "contains_any": _contains_any,
    "last_reply_contains_any": _last_reply_contains_any,
    "no_money_amounts": _no_money_amounts,
    "mentions_team": _mentions_team,
}
