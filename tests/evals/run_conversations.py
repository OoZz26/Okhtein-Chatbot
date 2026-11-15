"""Conversation evals: scripted customers talk to the REAL agent; rules + an LLM judge score the replies.

Usage:
    python -m tests.evals.run_conversations              # all scenarios
    python -m tests.evals.run_conversations --only vague_arabic impatient

Needs OPENAI_API_KEY in .env. Costs a few cents. Saves a report to tests/evals/reports/.
Exit code 0 only when every rule passes and the friendliness targets are met.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fakeredis import FakeAsyncRedis

from app.bootstrap import build_agent, build_llm
from app.core.config import Settings, get_settings
from app.domain.discovery import DiscoveryPolicy
from app.domain.profile_summarizer import LLMProfileSummarizer
from app.infra.cache.redis_session_store import RedisSessionStore
from app.infra.catalog.json_repository import JsonProductRepository
from app.infra.llm.openai_provider import OpenAICompatibleProvider
from app.services.chat_service import ChatService
from app.services.returning_customer_service import ReturningCustomerService
from tests.evals.checks import BotTurn, CheckResult, run_checks
from tests.evals.judge import DIMENSIONS, Judge, ReplyScore
from tests.fakes import InMemoryFollowUps, InMemoryProfileStore, make_handoffs, make_memory

EVALS_DIR = Path(__file__).parent
REPORTS_DIR = EVALS_DIR / "reports"
TARGET_AVERAGE = 4.0
TARGET_MINIMUM_PER_SCENARIO = 3.0


@dataclass
class ScenarioResult:
    id: str
    description: str
    turns: list[BotTurn]
    checks: list[CheckResult]
    scores: list[ReplyScore] = field(default_factory=list)

    @property
    def rules_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def average(self) -> float:
        return sum(s.average for s in self.scores) / len(self.scores)

    def dimension_average(self, dimension: str) -> float:
        return sum(s.scores[dimension] for s in self.scores) / len(self.scores)


@dataclass
class EvalStack:
    """One scenario's world: the real agent and LLM, with throwaway in-memory storage."""

    service: ChatService
    expire_session: Callable[[], Awaitable[None]]


def build_stack(settings: Settings) -> EvalStack:
    """A fresh stack per scenario, so expiring one scenario's session cannot disturb the others."""
    rig = make_memory(settings.history_limit, settings.session_ttl_seconds)
    session_redis = FakeAsyncRedis(decode_responses=True)
    returning = ReturningCustomerService(
        InMemoryProfileStore(),
        rig.store,
        LLMProfileSummarizer(build_llm(settings)),  # the real summariser: this is what the eval tests
        settings.profile_summary_max_chars,
        settings.profile_products_shown_limit,
        clock=rig.clock,
    )
    service = ChatService(
        build_agent(),
        rig.service,
        RedisSessionStore(session_redis, settings.session_ttl_seconds),
        DiscoveryPolicy(settings.max_discovery_questions, settings.session_products_shown_limit),
        InMemoryFollowUps(),
        make_handoffs().service,
        returning,
        settings.store_url,
    )

    async def expire_session() -> None:
        """The customer disappears for longer than the session TTL: Redis forgets, the clock moves on."""
        await rig.redis.flushall()
        await session_redis.flushall()
        rig.clock.advance(seconds=settings.session_ttl_seconds + 1)

    return EvalStack(service, expire_session)


async def run_scenario(
    scenario: dict[str, Any], settings: Settings, judge: Judge, prices: dict[str, float]
) -> ScenarioResult:
    stack = build_stack(settings)
    chat_id = f"eval-{scenario['id']}"
    turns: list[BotTurn] = []
    for step in scenario["turns"]:
        if isinstance(step, dict) and step.get("expire_session"):
            await stack.expire_session()
            continue
        result = await stack.service.handle_message(chat_id, step, scenario.get("sender_name", ""))
        turns.append(BotTurn(step, result.reply, result.product_handles, result.handed_off))
    checks = run_checks(turns, scenario["checks"], lambda handle: prices[handle])
    scores = await judge.score(scenario["description"], turns)
    return ScenarioResult(scenario["id"], scenario["description"], turns, checks, scores)


def targets_met(results: list[ScenarioResult]) -> tuple[bool, float]:
    overall = sum(r.average for r in results) / len(results)
    ok = (
        all(r.rules_passed for r in results)
        and overall >= TARGET_AVERAGE
        and all(r.average >= TARGET_MINIMUM_PER_SCENARIO for r in results)
    )
    return ok, overall


def render_table(results: list[ScenarioResult]) -> str:
    header = f"{'scenario':<26}{'rules':<8}" + "".join(f"{d[:7]:<9}" for d in DIMENSIONS) + "avg"
    lines = [header, "-" * len(header)]
    for r in results:
        dims = "".join(f"{r.dimension_average(d):<9.1f}" for d in DIMENSIONS)
        lines.append(f"{r.id:<26}{'PASS' if r.rules_passed else 'FAIL':<8}{dims}{r.average:.2f}")
    ok, overall = targets_met(results)
    lines += [
        "-" * len(header),
        f"overall friendliness average: {overall:.2f} (target >= {TARGET_AVERAGE}, "
        f"no scenario below {TARGET_MINIMUM_PER_SCENARIO})",
        f"RESULT: {'TARGETS MET' if ok else 'TARGETS NOT MET'}",
    ]
    return "\n".join(lines)


def render_report(results: list[ScenarioResult], settings: Settings) -> str:
    out = [
        "# Conversation eval report",
        f"\nRun: {datetime.now():%Y-%m-%d %H:%M} · agent model: `{settings.openai_model}` · "
        f"judge model: `{settings.eval_judge_model}`\n",
        "```\n" + render_table(results) + "\n```\n",
    ]
    for r in results:
        out.append(
            f"## {r.id}: {'PASS' if r.rules_passed else 'FAIL'} · {r.average:.2f}\n\n_{r.description}_\n"
        )
        out.append("**Rule checks**\n")
        out += [f"- {'✅' if c.passed else '❌'} `{c.name}` {c.detail}" for c in r.checks]
        for turn, score in zip(r.turns, r.scores, strict=True):
            out.append(
                f"\n**Customer:** {turn.customer}\n\n**Nour:**\n\n> " + turn.reply.replace("\n", "\n> ")
            )
            dims = ", ".join(f"{d} {score.scores[d]}" for d in DIMENSIONS)
            out.append(f"\n*Judge: {dims}: {score.reason}*")
        out.append("")
    return "\n".join(out)


def save_report(results: list[ScenarioResult], settings: Settings) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = REPORTS_DIR / f"report-{stamp}.md"
    path.write_text(render_report(results, settings), encoding="utf-8")
    (REPORTS_DIR / f"report-{stamp}.json").write_text(
        json.dumps(
            [
                {
                    "id": r.id,
                    "rules_passed": r.rules_passed,
                    "average": r.average,
                    "checks": [c.__dict__ for c in r.checks],
                    "scores": [s.scores | {"reason": s.reason} for s in r.scores],
                    "turns": [t.__dict__ for t in r.turns],
                }
                for r in results
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


async def main(only: list[str], prompt_version: str | None) -> int:
    settings = get_settings()
    if prompt_version:
        settings.prompt_version = prompt_version  # compare prompt versions without editing .env
    scenarios = json.loads((EVALS_DIR / "scenarios.json").read_text(encoding="utf-8"))
    if only:
        scenarios = [s for s in scenarios if s["id"] in only]
    prices = {p.handle: p.price_min for p in JsonProductRepository(Path(settings.products_path)).all()}
    judge = Judge(
        OpenAICompatibleProvider(
            settings.openai_api_key, settings.eval_judge_model, settings.llm_timeout_seconds
        )
    )
    models = (
        f"agent {settings.openai_model}, prompt {settings.prompt_version}, judge {settings.eval_judge_model}"
    )
    print(f"Running {len(scenarios)} scenarios ({models})")
    results = await asyncio.gather(*(run_scenario(s, settings, judge, prices) for s in scenarios))
    print("\n" + render_table(results))
    for r in results:
        for c in r.checks:
            if not c.passed:
                print(f"  ❌ {r.id}: {c.name} {c.detail}")
    print(f"\nReport saved to {save_report(results, settings)}")
    return 0 if targets_met(results)[0] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--only", nargs="*", default=[], help="run only these scenario ids")
    parser.add_argument("--prompt", default=None, help="prompt version to test, e.g. v1 (default: .env)")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.only, args.prompt)))
