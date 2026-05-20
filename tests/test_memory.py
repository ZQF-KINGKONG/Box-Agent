"""Tests for box_agent.memory — MemoryManager (core + context)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from box_agent.memory import MemoryManager


@pytest.fixture
def memory_dir(tmp_path: Path) -> Path:
    d = tmp_path / "memory"
    d.mkdir()
    return d


@pytest.fixture
def mgr(memory_dir: Path) -> MemoryManager:
    return MemoryManager(memory_dir=str(memory_dir))


# ── Core memory (MEMORY.md) ───────────────────────────────────


def test_read_write_core(mgr: MemoryManager):
    assert mgr.read_core() == ""
    mgr.write_core("- user prefers Chinese")
    assert "user prefers Chinese" in mgr.read_core()

    mgr.write_core("- new preference")
    content = mgr.read_core()
    assert "new preference" in content
    assert "user prefers Chinese" not in content


def test_append_core(mgr: MemoryManager):
    mgr.append_core("- item 1")
    mgr.append_core("- item 2")
    content = mgr.read_core()
    assert "item 1" in content
    assert "item 2" in content


def test_read_core_missing_file(mgr: MemoryManager):
    assert mgr.read_core() == ""


# ── Legacy aliases ────────────────────────────────────────────


def test_legacy_aliases(mgr: MemoryManager):
    mgr.write_manual_memory("- legacy content")
    assert "legacy content" in mgr.read_manual_memory()
    assert "legacy content" in mgr.read_all()


# ── Context memory (CONTEXT.md) ──────────────────────────────


def test_read_write_context(mgr: MemoryManager):
    assert mgr.read_context() == ""
    mgr.write_context("- Q2 goal: dashboard")
    assert "Q2 goal" in mgr.read_context()


def test_append_context(mgr: MemoryManager):
    mgr.append_context("- project A")
    mgr.append_context("- project B")
    content = mgr.read_context()
    assert "project A" in content
    assert "project B" in content


def test_core_and_context_independent(mgr: MemoryManager):
    """Writing to one file doesn't affect the other."""
    mgr.write_core("- user: Alice")
    mgr.write_context("- project: Dashboard")

    assert "Alice" in mgr.read_core()
    assert "Dashboard" not in mgr.read_core()
    assert "Dashboard" in mgr.read_context()
    assert "Alice" not in mgr.read_context()


def test_append_context_dedup_against_core(mgr: MemoryManager):
    """Lines already in Core are filtered out when appending to Context."""
    mgr.write_core("- user: Alice\n- prefers Chinese")
    mgr.append_context("- user: Alice\n- Q2 goal: dashboard\n- prefers Chinese")
    context = mgr.read_context()
    assert "Q2 goal" in context
    assert "Alice" not in context
    assert "Chinese" not in context


def test_append_context_dedup_against_existing_context(mgr: MemoryManager):
    """Lines already in Context are not appended again."""
    mgr.write_context("- Q2 goal: dashboard\n- weekly report format: progress/issues/plan")
    mgr.append_context("- q2 goal: dashboard\n- team lead: Bob\n- weekly report format: progress/issues/plan")

    context = mgr.read_context()
    assert context.count("Q2 goal") == 1
    assert context.count("weekly report format") == 1
    assert "team lead: Bob" in context


def test_append_context_dedup_within_single_append(mgr: MemoryManager):
    """Duplicate lines within one append call are only saved once."""
    mgr.append_context("- project A\n- Project A\n- project B")
    context = mgr.read_context()
    assert context.lower().count("project a") == 1
    assert "project B" in context


def test_append_context_all_filtered(mgr: MemoryManager):
    """If all lines are Core duplicates, nothing is written to Context."""
    mgr.write_core("- user: Alice")
    mgr.append_context("- user: Alice")
    assert mgr.read_context() == ""


def test_apply_context_operations_add_replace_drop_noop(mgr: MemoryManager):
    mgr.write_core("- user: Alice")
    mgr.write_context("- Q2 goal: dashboard\n- old transient detail")

    changed = mgr.apply_context_operations([
        {
            "action": "replace",
            "old": "- Q2 goal: dashboard",
            "new": "- Q2 goal: launch dashboard by 6/30",
        },
        {"action": "add", "content": "- user: Alice"},
        {"action": "add", "content": "- weekly report format: progress/issues/plan"},
        {"action": "drop", "content": "- old transient detail"},
        {"action": "noop", "content": "- ignored"},
    ])

    assert changed is True
    context = mgr.read_context()
    assert "launch dashboard by 6/30" in context
    assert "weekly report format" in context
    assert "old transient detail" not in context
    assert "user: Alice" not in context


async def test_update_context_with_llm_applies_model_plan(mgr: MemoryManager):
    mgr.write_context("- Q2 goal: dashboard")
    llm = MagicMock()
    response = MagicMock()
    response.content = (
        '{"operations": ['
        '{"action": "replace", "old": "- Q2 goal: dashboard", "new": "- Q2 goal: launch dashboard by 6/30", "reason": "more specific"},'
        '{"action": "add", "content": "- weekly report format: progress/issues/plan", "reason": "new template"}'
        ']}'
    )
    llm.generate = AsyncMock(return_value=response)

    status = await mgr.update_context_with_llm("- Q2 goal is to launch dashboard by 6/30", llm)

    assert status == "applied"
    context = mgr.read_context()
    assert "launch dashboard by 6/30" in context
    assert "weekly report format" in context
    assert llm.generate.await_count == 1


async def test_update_context_with_llm_falls_back_to_append_on_bad_json(mgr: MemoryManager):
    llm = MagicMock()
    response = MagicMock()
    response.content = "not json"
    llm.generate = AsyncMock(return_value=response)

    status = await mgr.update_context_with_llm("- project deadline: June", llm)

    assert status == "fallback_appended"
    assert "project deadline: June" in mgr.read_context()


# ── Search ────────────────────────────────────────────────────


def test_search_match(mgr: MemoryManager):
    mgr.write_context("- weekly report format: progress/issues/plan\n- Q2 goal: data dashboard\n- team lead: Bob")
    results = mgr.search("weekly")
    assert len(results) == 1
    assert "weekly report" in results[0]


def test_search_case_insensitive(mgr: MemoryManager):
    mgr.write_context("- Project Alpha is important")
    results = mgr.search("project alpha")
    assert len(results) == 1


def test_search_multiple_matches(mgr: MemoryManager):
    mgr.write_context("- report format A\n- report template B\n- unrelated item")
    results = mgr.search("report")
    assert len(results) == 2


def test_search_no_match(mgr: MemoryManager):
    mgr.write_context("- some content")
    results = mgr.search("nonexistent")
    assert results == []


def test_search_empty_context(mgr: MemoryManager):
    results = mgr.search("anything")
    assert results == []


def test_search_empty_query(mgr: MemoryManager):
    mgr.write_context("- some content")
    results = mgr.search("")
    assert results == []


def test_auto_match_context_matches_related_phrase_conservatively(mgr: MemoryManager):
    mgr.write_context(
        "- PPTX QA环境最新记录：在本轮AI科技公司入职培训PPT中，render_pptx.py 可成功导出PDF。\n"
        "- 会话连续性反馈：用户会以“科技公司入职培训 ppt 做好了吗”等方式追问既有交付状态。\n"
        "- Quick Bar history should default to visible records."
    )

    matches = mgr.auto_match_context("科技公司入职培训 PPT 做好了吗")

    assert [item["text"] for item in matches] == [
        "- PPTX QA环境最新记录：在本轮AI科技公司入职培训PPT中，render_pptx.py 可成功导出PDF。",
        "- 会话连续性反馈：用户会以“科技公司入职培训 ppt 做好了吗”等方式追问既有交付状态。",
    ]


def test_auto_match_context_ignores_weak_single_word_overlap(mgr: MemoryManager):
    mgr.write_context("- PPTX QA环境最新记录：在本轮AI科技公司入职培训PPT中，render_pptx.py 可成功导出PDF。")

    assert mgr.auto_match_context("帮我写一个培训方案") == []


def test_auto_match_context_ignores_host_appended_file_output_rules(mgr: MemoryManager):
    mgr.write_context(
        "- [文件输出规范] 当你生成了多个文件，将它们打包成 ZIP 并提供下载链接。\n"
        "- PPTX QA环境最新记录：在本轮AI科技公司入职培训PPT中，render_pptx.py 可成功导出PDF。"
    )

    matches = mgr.auto_match_context("科技公司入职培训 都需要注意什么\n\n[文件输出规范] 当你生成了多个文件")

    assert [item["text"] for item in matches] == [
        "- PPTX QA环境最新记录：在本轮AI科技公司入职培训PPT中，render_pptx.py 可成功导出PDF。"
    ]


def test_auto_match_context_filters_file_delivery_memory_unless_user_asks_delivery(mgr: MemoryManager):
    mgr.write_context(
        "- 科技公司入职培训文件交付偏好：若生成多个文件必须使用 zip 命令打包。\n"
        "- 会话连续性反馈：用户会以“科技公司入职培训 ppt 做好了吗”等方式追问既有交付状态。"
    )

    assert [
        item["text"] for item in mgr.auto_match_context("科技公司入职培训 都需要注意什么")
    ] == [
        "- 会话连续性反馈：用户会以“科技公司入职培训 ppt 做好了吗”等方式追问既有交付状态。"
    ]
    assert [
        item["text"] for item in mgr.auto_match_context("科技公司入职培训 文件怎么打包交付")
    ][0] == "- 科技公司入职培训文件交付偏好：若生成多个文件必须使用 zip 命令打包。"


def test_auto_match_context_filters_title_meta_memory_unless_user_asks_title(mgr: MemoryManager):
    mgr.write_context(
        "- 会话标题提炼偏好：遇到“查询 科技公司入职培训”时标题可提炼为“科技公司入职培训”。\n"
        "- 会话连续性反馈：用户会以“科技公司入职培训 ppt 做好了吗”等方式追问既有交付状态。"
    )

    assert [
        item["text"] for item in mgr.auto_match_context("科技公司入职培训 都需要注意什么")
    ] == [
        "- 会话连续性反馈：用户会以“科技公司入职培训 ppt 做好了吗”等方式追问既有交付状态。"
    ]
    assert [
        item["text"] for item in mgr.auto_match_context("科技公司入职培训 这个会话标题怎么提炼")
    ][0] == "- 会话标题提炼偏好：遇到“查询 科技公司入职培训”时标题可提炼为“科技公司入职培训”。"


# ── Recall ─────────────────────────────────────────────────────


def test_recall_empty(mgr: MemoryManager):
    assert mgr.recall() == ""


def test_recall_only_core(mgr: MemoryManager):
    mgr.write_core("- always use English")
    mgr.write_context("- project context that should NOT be recalled")
    block = mgr.recall()
    assert "--- MEMORY START ---" in block
    assert "always use English" in block
    assert "project context" not in block


def test_recall_does_not_include_context(mgr: MemoryManager):
    """Context memory must not appear in recall — only via search."""
    mgr.write_context("- secret context")
    block = mgr.recall()
    assert block == ""  # No core memory → empty


# ── build_memory_block ────────────────────────────────────────


def test_build_memory_block_format():
    block = MemoryManager.build_memory_block("- core item")
    assert block.startswith("--- MEMORY START ---")
    assert block.endswith("--- MEMORY END ---")
    assert "[Core Memory]" in block


def test_build_memory_block_empty():
    assert MemoryManager.build_memory_block("") == ""


def test_build_memory_block_core_only():
    block = MemoryManager.build_memory_block("- core item")
    assert "[Core Memory]" in block
    assert "core item" in block


def test_auto_match_context_bumps_hits_and_last_used(mgr: MemoryManager):
    """auto_match_context must increment hits/last_used on matched entries.

    Without this side effect, prompt-time recall never accumulates evidence
    that an entry is useful, and the promotion gate (hit_threshold) is
    permanently unreachable.
    """
    from box_agent.memory import _new_entry, write_context_file

    matched = _new_entry("- 科技公司入职培训PPT 已完成 render 导出")
    unmatched = _new_entry("- 完全不相关的另一个事实")
    original_last_used = matched.last_used
    write_context_file(mgr.context_file, [matched, unmatched])

    results = mgr.auto_match_context("科技公司入职培训 PPT 做好了吗")
    assert results, "expected at least one auto-match hit"

    entries = {e.id: e for e in mgr._read_context_entries()}
    assert entries[matched.id].hits == 1
    assert entries[matched.id].last_used >= original_last_used
    assert entries[matched.id].last_used != ""
    # untouched entry stays at 0 hits.
    assert entries[unmatched.id].hits == 0


def test_auto_match_context_no_match_does_not_touch_entries(mgr: MemoryManager):
    from box_agent.memory import _new_entry, write_context_file

    entry = _new_entry("- 不会被匹配到的内容")
    write_context_file(mgr.context_file, [entry])

    assert mgr.auto_match_context("完全无关的话题") == []
    survivor = mgr._read_context_entries()[0]
    assert survivor.hits == 0
    assert survivor.last_used == entry.last_used


# ── append_context Jaccard fuzzy dedup ────────────────────────


def test_append_context_jaccard_merges_paraphrased_line(memory_dir):
    """Paraphrased restatements of an existing entry should bump hits, not
    create a new entry. Without this the promotion gate's hit_threshold is
    permanently sabotaged by LLM extractor wording drift."""
    mgr = MemoryManager(memory_dir=str(memory_dir), dedup_jaccard_threshold=0.6)
    mgr.append_context("- user is generating brazil football introduction ppt")
    before = mgr._read_context_entries()
    assert len(before) == 1
    assert before[0].hits == 0

    # Same fact, different wording — most tokens overlap.
    mgr.append_context("- user generating brazil football ppt introduction")

    after = mgr._read_context_entries()
    assert len(after) == 1, "paraphrase should have merged, not been appended"
    assert after[0].hits == 1
    assert after[0].last_used >= before[0].last_used


def test_append_context_jaccard_keeps_distinct_facts(memory_dir):
    mgr = MemoryManager(memory_dir=str(memory_dir), dedup_jaccard_threshold=0.85)
    mgr.append_context("- user prefers chinese responses")
    mgr.append_context("- project uses uv for dependency management")

    entries = mgr._read_context_entries()
    assert len(entries) == 2
    assert all(e.hits == 0 for e in entries)


def test_append_context_threshold_zero_disables_distinct_lines(memory_dir):
    """At extremely low threshold (0.0) ANY non-empty existing entry would
    catch every new line. Default threshold (0.85) must not behave this way."""
    mgr = MemoryManager(memory_dir=str(memory_dir), dedup_jaccard_threshold=0.85)
    mgr.append_context("- aaa bbb ccc")
    mgr.append_context("- xxx yyy zzz")
    assert len(mgr._read_context_entries()) == 2


# ── Title-generation filter ──────────────────────────────────


def test_auto_match_context_ignores_title_generation_prompts(mgr: MemoryManager):
    """Host-injected title-generation prompts must not bump hits."""
    from box_agent.memory import _new_entry, write_context_file

    entry = _new_entry("- 科技公司入职培训PPT 已完成 render 导出")
    write_context_file(mgr.context_file, [entry])

    # Host prompt — has no interrogative marker, matches title-gen pattern.
    assert mgr.auto_match_context("请为这段对话提炼一个简短标题：科技公司入职培训") == []

    survivor = mgr._read_context_entries()[0]
    assert survivor.hits == 0


def test_auto_match_context_user_question_about_title_still_matches(mgr: MemoryManager):
    """A user question about title-related memory must not be classified as a
    host title-generation prompt — the interrogative-marker guard prevents the
    title-gen pattern matcher from kicking in even when the prompt mentions
    titles."""
    from box_agent.memory import _is_title_generation_query

    # Host prompts (no interrogative) — classified as title-gen.
    assert _is_title_generation_query("请为这段对话提炼一个简短标题")
    assert _is_title_generation_query("为会话生成标题：xxx")

    # User questions about titles — interrogative present, not classified.
    assert not _is_title_generation_query("会话标题怎么提炼")
    assert not _is_title_generation_query("为什么这个会话要提炼标题？")
    assert not _is_title_generation_query("how do I generate a title for this chat?")


# ── LLM promotion plan ──────────────────────────────────────


def _make_planner_llm(payload: dict):
    llm = MagicMock()
    response = MagicMock()
    response.content = json.dumps(payload)
    llm.generate = AsyncMock(return_value=response)
    return llm


async def test_plan_promotion_returns_plan_on_valid_llm_output(mgr: MemoryManager):
    from box_agent.memory import _new_entry, write_context_file

    mgr.write_core("- user prefers Chinese\n- workspace: /tmp/x")
    a = _new_entry("- user likes diagrams")
    b = _new_entry("- weekly cadence Tuesday")
    write_context_file(mgr.context_file, [a, b])

    llm = _make_planner_llm(
        {
            "new_core": (
                "- user prefers Chinese\n- workspace: /tmp/x\n"
                "- user likes diagrams\n- weekly cadence Tuesday"
            ),
            "consumed_entry_ids": [a.id, b.id],
            "rationale": "fold both hot entries",
        }
    )

    plan = await mgr.plan_promotion([a, b], llm)
    assert plan is not None
    assert "user likes diagrams" in plan.new_core
    assert set(plan.consumed_entry_ids) == {a.id, b.id}
    assert llm.generate.await_count == 1


async def test_plan_promotion_returns_none_on_bad_json(mgr: MemoryManager):
    from box_agent.memory import _new_entry, write_context_file

    a = _new_entry("- candidate")
    write_context_file(mgr.context_file, [a])

    llm = MagicMock()
    response = MagicMock()
    response.content = "definitely not json"
    llm.generate = AsyncMock(return_value=response)

    assert await mgr.plan_promotion([a], llm) is None


async def test_plan_promotion_rejects_oversized_core_shrink(mgr: MemoryManager):
    from box_agent.memory import _new_entry, write_context_file

    mgr.write_core("- " + "lorem ipsum dolor sit amet " * 20)
    a = _new_entry("- candidate")
    write_context_file(mgr.context_file, [a])

    llm = _make_planner_llm(
        {
            "new_core": "- tiny",
            "consumed_entry_ids": [a.id],
            "rationale": "gutting core",
        }
    )

    assert await mgr.plan_promotion([a], llm) is None


async def test_plan_promotion_filters_non_candidate_ids(mgr: MemoryManager):
    from box_agent.memory import _new_entry, write_context_file

    a = _new_entry("- candidate")
    other = _new_entry("- unrelated")
    write_context_file(mgr.context_file, [a, other])

    llm = _make_planner_llm(
        {
            "new_core": "- merged content here that grows core",
            "consumed_entry_ids": [a.id, other.id, "ctx_fake_id"],
            "rationale": "ok",
        }
    )

    plan = await mgr.plan_promotion([a], llm)
    assert plan is not None
    # other.id and fake id must be filtered out — only candidate ids allowed
    assert plan.consumed_entry_ids == (a.id,)


def test_apply_promotion_plan_overwrites_core_and_consumes_entries(mgr: MemoryManager):
    from box_agent.events import MemoryPromotionPlan
    from box_agent.memory import _new_entry, write_context_file

    a = _new_entry("- A")
    b = _new_entry("- B")
    c = _new_entry("- C")
    write_context_file(mgr.context_file, [a, b, c])
    mgr.write_core("- old core")

    plan = MemoryPromotionPlan(
        current_core="- old core",
        new_core="- new core\n- A folded in",
        consumed_entry_ids=(a.id, b.id),
        rationale="test",
    )

    result = mgr.apply_promotion_plan(plan)
    assert result == {"applied": 1, "consumed": 2}
    assert mgr.read_core() == "- new core\n- A folded in"
    remaining = mgr._read_context_entries()
    assert [e.id for e in remaining] == [c.id]


def test_reject_promotion_plan_marks_candidates_rejected(mgr: MemoryManager):
    from box_agent.events import MemoryPromotionPlan
    from box_agent.memory import _new_entry, write_context_file

    a = _new_entry("- A")
    b = _new_entry("- B")
    write_context_file(mgr.context_file, [a, b])
    mgr.write_core("- core stays")

    plan = MemoryPromotionPlan(
        current_core="- core stays",
        new_core="- ignored",
        consumed_entry_ids=(a.id,),
        rationale="test",
    )

    result = mgr.reject_promotion_plan(plan)
    assert result == {"rejected": 1}
    # core untouched
    assert mgr.read_core() == "- core stays"
    entries = {e.id: e for e in mgr._read_context_entries()}
    assert entries[a.id].core_status == "rejected"
    assert entries[b.id].core_status != "rejected"
