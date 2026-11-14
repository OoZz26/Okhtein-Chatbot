import json
import os
from pathlib import Path

from app.domain.agent.sales_agent import SalesAgent, load_system_prompt
from app.domain.knowledge import UNKNOWN_HEADING, render_store_knowledge
from app.domain.models import LLMResponse
from app.domain.tools.base import ToolRegistry
from app.infra.catalog.file_store_info import FileStoreInfoSource
from tests.fakes import FakeLLM, InMemoryProducts

KNOWLEDGE = """# Okhtein knowledge

## Returns & refunds
- Returns accepted within 14 days of delivery.

## TODO for the store owner (fill these in)
- Shipping times and fees inside Egypt:
- Cash on delivery available? :

## About
Founded by two sisters.
"""


class FakeStoreInfo:
    def __init__(self, text: str) -> None:
        self.text = text

    def get_knowledge(self) -> str:
        return self.text


def agent_with(store_info: FakeStoreInfo | None) -> tuple[SalesAgent, FakeLLM]:
    llm = FakeLLM([LLMResponse(json.dumps({"message": "ok", "product_handles": []}))] * 3)
    agent = SalesAgent(
        llm, ToolRegistry([]), InMemoryProducts([]), load_system_prompt(), 3, store_info=store_info
    )
    return agent, llm


class TestRenderStoreKnowledge:
    def test_known_facts_are_kept(self) -> None:
        rendered = render_store_knowledge(KNOWLEDGE)

        assert "within 14 days" in rendered
        assert "Founded by two sisters." in rendered  # a section AFTER the TODO list survives

    def test_the_todo_list_becomes_an_explicit_unknown_list(self) -> None:
        rendered = render_store_knowledge(KNOWLEDGE)

        assert "TODO" not in rendered
        assert UNKNOWN_HEADING in rendered
        assert "- Shipping times and fees inside Egypt\n" in rendered + "\n"
        assert "- Cash on delivery available?" in rendered

    def test_text_without_a_todo_section_is_unchanged(self) -> None:
        assert render_store_knowledge("## Returns\n- 14 days\n") == "## Returns\n- 14 days"


class TestAgentUsesStoreInfo:
    async def test_the_knowledge_reaches_the_system_prompt(self) -> None:
        agent, llm = agent_with(FakeStoreInfo(KNOWLEDGE))

        await agent.respond("Can I return an item?")

        system_prompt = llm.calls[0][0].content
        assert "within 14 days of delivery" in system_prompt
        assert "ONLY source for store questions" in system_prompt

    async def test_changing_the_source_changes_the_next_answer_context_without_code_changes(self) -> None:
        source = FakeStoreInfo(KNOWLEDGE)
        agent, llm = agent_with(source)

        await agent.respond("returns?")
        source.text = KNOWLEDGE.replace("14 days", "30 days")
        await agent.respond("returns?")

        assert "14 days" in llm.calls[0][0].content
        assert "30 days" in llm.calls[1][0].content

    async def test_no_store_info_means_no_knowledge_section(self) -> None:
        agent, llm = agent_with(None)

        await agent.respond("hi")

        assert (
            "Store knowledge"
            not in llm.calls[0][0].content.split("## Session notes")[0].split("# Output")[-1]
        )


class TestFileStoreInfoSource:
    def test_reads_the_file(self, tmp_path: Path) -> None:
        path = tmp_path / "knowledge.md"
        path.write_text("hello", encoding="utf-8")

        assert FileStoreInfoSource(path).get_knowledge() == "hello"

    def test_an_edited_file_is_picked_up_without_a_restart(self, tmp_path: Path) -> None:
        path = tmp_path / "knowledge.md"
        path.write_text("returns: 14 days", encoding="utf-8")
        source = FileStoreInfoSource(path)
        assert source.get_knowledge() == "returns: 14 days"

        path.write_text("returns: 30 days", encoding="utf-8")
        stat = path.stat()
        os.utime(path, (stat.st_atime, stat.st_mtime + 5))  # make the change visible even on coarse clocks

        assert source.get_knowledge() == "returns: 30 days"

    def test_a_missing_file_gives_empty_knowledge_instead_of_crashing(self, tmp_path: Path) -> None:
        assert FileStoreInfoSource(tmp_path / "nope.md").get_knowledge() == ""

    def test_the_real_knowledge_file_has_the_returns_policy_and_unknowns(self) -> None:
        raw = FileStoreInfoSource(Path("data/knowledge.md")).get_knowledge()
        rendered = render_store_knowledge(raw)

        assert "14 days" in rendered
        assert "Shipping" in rendered.split(UNKNOWN_HEADING)[1]
