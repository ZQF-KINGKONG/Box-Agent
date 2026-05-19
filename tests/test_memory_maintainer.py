"""Tests for box_agent.memory_maintainer — decay, archive cleanup, dedup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from box_agent.config import AgentConfig
from box_agent.memory import (
    ContextEntry,
    MemoryManager,
    _new_entry,
    parse_context_file,
    write_context_file,
)
from box_agent.memory_maintainer import (
    MemoryMaintainer,
    _jaccard,
    _tokens,
)


@pytest.fixture
def memory_dir(tmp_path: Path) -> Path:
    d = tmp_path / "memory"
    d.mkdir()
    return d


@pytest.fixture
def mgr(memory_dir: Path) -> MemoryManager:
    return MemoryManager(memory_dir=str(memory_dir))


@pytest.fixture
def config() -> AgentConfig:
    return AgentConfig(
        memory_maintainer_enabled=True,
        memory_maintainer_interval_hours=24,
        memory_decay_days=30,
        memory_archive_days=90,
        memory_dedup_jaccard=0.85,
    )


def _stamp(days_ago: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _entry(content: str, *, hits: int = 0, last_used_days_ago: int = 0,
           created_days_ago: int | None = None, source: str = "tool",
           confidence: float = 1.0) -> ContextEntry:
    created = _stamp(created_days_ago if created_days_ago is not None else last_used_days_ago)
    return ContextEntry(
        id=f"ctx_test_{id(content) & 0xfffffff:x}",
        content=content,
        created=created,
        last_used=_stamp(last_used_days_ago),
        hits=hits,
        source=source,
        confidence=confidence,
    )


# ── Decay ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_decay_moves_stale_zero_hits_to_archive(mgr: MemoryManager, config: AgentConfig):
    entries = [
        _entry("- recent unused", hits=0, last_used_days_ago=10),
        _entry("- stale unused", hits=0, last_used_days_ago=60),
        _entry("- stale but used", hits=3, last_used_days_ago=60),
    ]
    write_context_file(mgr.context_file, entries)

    await MemoryMaintainer(mgr, config).run_if_due()

    active = parse_context_file(mgr.context_file)
    archived = parse_context_file(mgr.archive_file)
    assert {e.content for e in active} == {"- recent unused", "- stale but used"}
    assert {e.content for e in archived} == {"- stale unused"}


@pytest.mark.asyncio
async def test_decay_preserves_metadata_through_archive(mgr: MemoryManager, config: AgentConfig):
    original = _entry("- stale unused", hits=0, last_used_days_ago=60, source="extractor", confidence=0.7)
    write_context_file(mgr.context_file, [original])

    await MemoryMaintainer(mgr, config).run_if_due()

    archived = parse_context_file(mgr.archive_file)
    assert len(archived) == 1
    assert archived[0].id == original.id
    assert archived[0].source == "extractor"
    assert archived[0].confidence == 0.7


@pytest.mark.asyncio
async def test_decay_appends_to_existing_archive(mgr: MemoryManager, config: AgentConfig):
    existing_archive = [_entry("- old archived", last_used_days_ago=40)]
    write_context_file(mgr.archive_file, existing_archive)

    write_context_file(mgr.context_file, [
        _entry("- newly stale", hits=0, last_used_days_ago=60),
    ])

    await MemoryMaintainer(mgr, config).run_if_due()

    archived = parse_context_file(mgr.archive_file)
    contents = {e.content for e in archived}
    assert contents == {"- old archived", "- newly stale"}


# ── Archive cleanup → trash ─────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_archive_moves_very_old_to_trash(mgr: MemoryManager, config: AgentConfig):
    # cutoff = decay (30) + archive (90) = 120 days
    write_context_file(mgr.archive_file, [
        _entry("- recently archived", last_used_days_ago=60),
        _entry("- ancient", last_used_days_ago=200),
    ])

    await MemoryMaintainer(mgr, config).run_if_due()

    archived = parse_context_file(mgr.archive_file)
    assert {e.content for e in archived} == {"- recently archived"}

    # trash file should exist and contain the ancient entry
    trash_dirs = list(mgr.trash_dir.iterdir())
    assert len(trash_dirs) == 1
    trash_files = list(trash_dirs[0].iterdir())
    assert len(trash_files) == 1
    purged = parse_context_file(trash_files[0])
    assert {e.content for e in purged} == {"- ancient"}


@pytest.mark.asyncio
async def test_cleanup_archive_noop_when_empty(mgr: MemoryManager, config: AgentConfig):
    await MemoryMaintainer(mgr, config).run_if_due()
    assert not mgr.trash_dir.exists() or not any(mgr.trash_dir.iterdir())


# ── Dedup ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dedup_merges_near_duplicates(mgr: MemoryManager):
    # Use a relaxed Jaccard threshold so a realistic near-duplicate pair merges.
    # Default 0.85 is intentionally strict to avoid false merges.
    config = AgentConfig(memory_dedup_jaccard=0.7)
    write_context_file(mgr.context_file, [
        _entry("- user prefers dark mode", hits=2, last_used_days_ago=1),
        _entry("- user prefers dark mode interface", hits=1, last_used_days_ago=2),
        _entry("- entirely different fact about apples", hits=0, last_used_days_ago=1),
    ])

    await MemoryMaintainer(mgr, config).run_if_due()

    entries = parse_context_file(mgr.context_file)
    # Two near-duplicates merge into one (winner has more hits); third stays.
    assert len(entries) == 2
    contents = {e.content for e in entries}
    assert "- entirely different fact about apples" in contents
    # Winner is the higher-hits entry
    winner = next(e for e in entries if "dark mode" in e.content)
    assert winner.content == "- user prefers dark mode"
    assert winner.hits == 3  # 2 + 1 merged


@pytest.mark.asyncio
async def test_dedup_identical_content_always_merges(mgr: MemoryManager, config: AgentConfig):
    # Identical content → Jaccard 1.0, merges even at default 0.85 threshold.
    write_context_file(mgr.context_file, [
        _entry("- duplicate fact about widgets", hits=2, last_used_days_ago=1),
        _entry("- duplicate fact about widgets", hits=3, last_used_days_ago=2),
    ])

    await MemoryMaintainer(mgr, config).run_if_due()

    entries = parse_context_file(mgr.context_file)
    assert len(entries) == 1
    assert entries[0].hits == 5  # 2 + 3


@pytest.mark.asyncio
async def test_dedup_does_not_merge_unrelated_entries(mgr: MemoryManager, config: AgentConfig):
    write_context_file(mgr.context_file, [
        _entry("- apples are red", hits=1, last_used_days_ago=1),
        _entry("- bananas are yellow", hits=1, last_used_days_ago=1),
    ])

    await MemoryMaintainer(mgr, config).run_if_due()

    entries = parse_context_file(mgr.context_file)
    assert len(entries) == 2


# ── Timestamp guard ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_if_due_respects_recent_marker(mgr: MemoryManager, config: AgentConfig):
    # First run executes maintenance
    write_context_file(mgr.context_file, [_entry("- stale", hits=0, last_used_days_ago=60)])
    ran_first = await MemoryMaintainer(mgr, config).run_if_due()
    assert ran_first is True

    # Second run within the interval skips
    write_context_file(mgr.context_file, [_entry("- another stale", hits=0, last_used_days_ago=60)])
    ran_second = await MemoryMaintainer(mgr, config).run_if_due()
    assert ran_second is False

    # The second batch was untouched (still in active context)
    active = parse_context_file(mgr.context_file)
    assert any(e.content == "- another stale" for e in active)


@pytest.mark.asyncio
async def test_run_if_due_disabled_via_config(mgr: MemoryManager):
    config = AgentConfig(memory_maintainer_enabled=False)
    write_context_file(mgr.context_file, [_entry("- stale", hits=0, last_used_days_ago=60)])

    ran = await MemoryMaintainer(mgr, config).run_if_due()
    assert ran is False
    # nothing moved
    assert not mgr.archive_file.exists() or not parse_context_file(mgr.archive_file)


@pytest.mark.asyncio
async def test_marker_written_after_successful_run(mgr: MemoryManager, config: AgentConfig):
    await MemoryMaintainer(mgr, config).run_if_due()
    marker = mgr.memory_dir / ".maintainer_last_run"
    assert marker.exists()
    assert marker.read_text(encoding="utf-8").strip()


# ── Idempotency ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_maintainer_is_idempotent_after_first_run(mgr: MemoryManager, config: AgentConfig):
    write_context_file(mgr.context_file, [
        _entry("- stale", hits=0, last_used_days_ago=60),
        _entry("- keep me", hits=5, last_used_days_ago=1),
    ])

    await MemoryMaintainer(mgr, config).run_if_due()
    state_after_first = mgr.context_file.read_text(encoding="utf-8")

    # Force-rerun by removing the marker
    (mgr.memory_dir / ".maintainer_last_run").unlink()

    await MemoryMaintainer(mgr, config).run_if_due()
    state_after_second = mgr.context_file.read_text(encoding="utf-8")

    assert state_after_first == state_after_second


# ── Helpers ─────────────────────────────────────────────────


def test_jaccard_identical():
    assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0


def test_jaccard_disjoint():
    assert _jaccard({"a"}, {"b"}) == 0.0


def test_jaccard_partial():
    # {a,b,c} vs {b,c,d}: intersection=2, union=4 → 0.5
    assert _jaccard({"a", "b", "c"}, {"b", "c", "d"}) == 0.5


def test_tokens_lowercase_and_strips_punctuation():
    assert _tokens("Hello, World!") == {"hello", "world"}


# ── _compact (Phase 4: LLM topic compaction) ─────────────────


class FakeLLMResponse:
    def __init__(self, content: str):
        self.content = content


class FakeCompactLLM:
    """Returns a pre-canned JSON-string response."""

    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = 0
        self.last_messages = None

    async def generate(self, messages, **_):
        self.calls += 1
        self.last_messages = messages
        return FakeLLMResponse(self.response_text)


def _maint_cfg(**overrides) -> AgentConfig:
    base = dict(
        memory_maintainer_enabled=True,
        memory_compaction_enabled=True,
        memory_context_max_entries=2,
        memory_context_max_tokens=10_000_000,
        memory_decay_days=30,
        memory_archive_days=90,
        memory_dedup_jaccard=0.999,  # don't accidentally trigger Jaccard merge
        memory_maintainer_interval_hours=24,
    )
    base.update(overrides)
    return AgentConfig(**base)


@pytest.mark.asyncio
async def test_compact_below_threshold_is_noop(memory_dir):
    mgr = MemoryManager(memory_dir=str(memory_dir))
    a = _new_entry("- only a few entries")
    b = _new_entry("- another fact")
    write_context_file(mgr.context_file, [a, b])

    cfg = _maint_cfg(memory_context_max_entries=10)  # over capacity not hit
    llm = FakeCompactLLM("[]")
    m = MemoryMaintainer(mgr, cfg, llm=llm)

    await m._compact(datetime.now(timezone.utc))

    assert llm.calls == 0, "LLM should not be called when under capacity"
    after = parse_context_file(mgr.context_file)
    assert {e.content for e in after} == {"- only a few entries", "- another fact"}


@pytest.mark.asyncio
async def test_compact_disabled_flag_skips(memory_dir):
    mgr = MemoryManager(memory_dir=str(memory_dir))
    write_context_file(mgr.context_file, [
        _new_entry("- a"), _new_entry("- b"), _new_entry("- c"),
    ])
    cfg = _maint_cfg(memory_compaction_enabled=False)
    llm = FakeCompactLLM("[]")
    m = MemoryMaintainer(mgr, cfg, llm=llm)

    await m._compact(datetime.now(timezone.utc))

    assert llm.calls == 0
    assert len(parse_context_file(mgr.context_file)) == 3


@pytest.mark.asyncio
async def test_compact_no_llm_skips(memory_dir):
    mgr = MemoryManager(memory_dir=str(memory_dir))
    write_context_file(mgr.context_file, [
        _new_entry("- a"), _new_entry("- b"), _new_entry("- c"),
    ])
    m = MemoryMaintainer(mgr, _maint_cfg(), llm=None)
    await m._compact(datetime.now(timezone.utc))
    assert len(parse_context_file(mgr.context_file)) == 3


@pytest.mark.asyncio
async def test_compact_merges_topics_and_preserves_metadata(memory_dir):
    import json as _json

    mgr = MemoryManager(memory_dir=str(memory_dir))
    brazil = _new_entry("- user generating brazil football intro ppt")
    brazil.hits = 5
    brazil.created = "2026-01-01T00:00:00"
    brazil.last_used = "2026-04-01T00:00:00"
    spain = _new_entry("- user generating spain football intro ppt")
    spain.hits = 3
    spain.created = "2026-02-01T00:00:00"
    spain.last_used = "2026-05-01T00:00:00"
    germany = _new_entry("- user generating germany football ppt")
    germany.hits = 2
    germany.created = "2026-03-01T00:00:00"
    germany.last_used = "2026-04-15T00:00:00"
    pkg = _new_entry("- project uses uv, never use pip")
    pkg.hits = 12

    write_context_file(mgr.context_file, [brazil, spain, germany, pkg])

    canned = _json.dumps([
        {
            "content": "用户经常生成各国足球队介绍 PPT（巴西/西班牙/德国等）",
            "hits": 10,
            "sources": [brazil.id, spain.id, germany.id],
        },
        {
            "content": "- project uses uv, never use pip",
            "hits": 12,
            "sources": [pkg.id],
        },
    ])
    llm = FakeCompactLLM(canned)
    cfg = _maint_cfg(memory_context_max_entries=2)
    m = MemoryMaintainer(mgr, cfg, llm=llm)

    await m._compact(datetime.now(timezone.utc))

    after = {e.content: e for e in parse_context_file(mgr.context_file)}
    assert len(after) == 2
    merged = after["用户经常生成各国足球队介绍 PPT（巴西/西班牙/德国等）"]
    assert merged.hits == 10
    assert merged.created == "2026-01-01T00:00:00"  # min
    assert merged.last_used == "2026-05-01T00:00:00"  # max
    assert merged.source == "compact"
    # Strong-preference entry untouched in spirit (content + hits preserved).
    assert after["- project uses uv, never use pip"].hits == 12


@pytest.mark.asyncio
async def test_compact_rejected_flag_propagates(memory_dir):
    """Rejected entries must remain rejected after compaction so they can't
    sneak back into the core via merging with a non-rejected sibling."""
    import json as _json

    mgr = MemoryManager(memory_dir=str(memory_dir))
    a = _new_entry("- fact a")
    a.hits = 3
    a.core_status = "rejected"
    b = _new_entry("- fact a but worded differently")
    b.hits = 2
    write_context_file(mgr.context_file, [a, b])

    canned = _json.dumps([
        {"content": "- fact a unified", "hits": 5, "sources": [a.id, b.id]},
    ])
    m = MemoryMaintainer(mgr, _maint_cfg(memory_context_max_entries=1), llm=FakeCompactLLM(canned))

    await m._compact(datetime.now(timezone.utc))

    after = parse_context_file(mgr.context_file)
    assert len(after) == 1
    assert after[0].core_status == "rejected"


@pytest.mark.asyncio
async def test_compact_invalid_json_keeps_original(memory_dir):
    mgr = MemoryManager(memory_dir=str(memory_dir))
    entries = [_new_entry(f"- entry {i}") for i in range(5)]
    write_context_file(mgr.context_file, entries)
    original = {e.content for e in entries}

    llm = FakeCompactLLM("not valid json at all")
    m = MemoryMaintainer(mgr, _maint_cfg(memory_context_max_entries=2), llm=llm)

    await m._compact(datetime.now(timezone.utc))

    after = {e.content for e in parse_context_file(mgr.context_file)}
    assert after == original


@pytest.mark.asyncio
async def test_compact_unknown_source_id_rejects_output(memory_dir):
    import json as _json

    mgr = MemoryManager(memory_dir=str(memory_dir))
    real = _new_entry("- real entry")
    write_context_file(mgr.context_file, [real, _new_entry("- another"), _new_entry("- third")])

    # LLM hallucinates an id not present in the input.
    canned = _json.dumps([
        {"content": "- merged", "hits": 1, "sources": ["ghost-id-not-real"]},
    ])
    m = MemoryMaintainer(mgr, _maint_cfg(memory_context_max_entries=1), llm=FakeCompactLLM(canned))

    await m._compact(datetime.now(timezone.utc))

    contents = {e.content for e in parse_context_file(mgr.context_file)}
    assert "- merged" not in contents
    assert "- real entry" in contents


@pytest.mark.asyncio
async def test_compact_creates_backup_before_overwrite(memory_dir):
    import json as _json

    mgr = MemoryManager(memory_dir=str(memory_dir))
    a = _new_entry("- a")
    b = _new_entry("- b")
    write_context_file(mgr.context_file, [a, b, _new_entry("- c")])
    original_text = mgr.context_file.read_text(encoding="utf-8")

    canned = _json.dumps([
        {"content": "merged", "hits": 0, "sources": [a.id, b.id]},
    ])
    m = MemoryMaintainer(mgr, _maint_cfg(memory_context_max_entries=1), llm=FakeCompactLLM(canned))

    await m._compact(datetime.now(timezone.utc))

    # Trash dir should contain at least one backup file matching today's date.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    backup_dir = mgr.trash_dir / today / "compact"
    assert backup_dir.exists()
    backups = list(backup_dir.glob("CONTEXT.*.md"))
    assert backups, "expected a CONTEXT.<timestamp>.md backup"
    assert backups[0].read_text(encoding="utf-8") == original_text
