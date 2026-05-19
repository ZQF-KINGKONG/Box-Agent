"""Tests for CONTEXT.md → MEMORY.md (core) promotion flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from box_agent.memory import (
    ContextEntry,
    MemoryManager,
    _new_entry,
    write_context_file,
)


@pytest.fixture
def memory_dir(tmp_path: Path) -> Path:
    d = tmp_path / "memory"
    d.mkdir()
    return d


@pytest.fixture
def mgr(memory_dir: Path) -> MemoryManager:
    return MemoryManager(memory_dir=str(memory_dir))


def _stamp(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")


def _entry(content: str, *, hits: int = 0, core_status: str = "none",
           last_proposed: str = "", source: str = "tool") -> ContextEntry:
    e = _new_entry(content, source=source)
    e.hits = hits
    e.core_status = core_status
    e.last_proposed = last_proposed
    return e


# ── list_promotion_candidates ──────────────────────────────


def test_list_candidates_filters_by_hit_threshold(mgr: MemoryManager):
    write_context_file(mgr.context_file, [
        _entry("- low hits", hits=2),
        _entry("- meets threshold", hits=5),
        _entry("- exceeds threshold", hits=10),
    ])
    cands = mgr.list_promotion_candidates(hit_threshold=5, cooldown_days=14)
    contents = {c.content for c in cands}
    assert contents == {"- meets threshold", "- exceeds threshold"}


def test_list_candidates_excludes_rejected(mgr: MemoryManager):
    write_context_file(mgr.context_file, [
        _entry("- good candidate", hits=10),
        _entry("- already rejected", hits=10, core_status="rejected"),
    ])
    cands = mgr.list_promotion_candidates(hit_threshold=5, cooldown_days=14)
    assert {c.content for c in cands} == {"- good candidate"}


def test_list_candidates_respects_cooldown(mgr: MemoryManager):
    # Recently proposed → still in cooldown → excluded
    recent = _stamp(days_ago=5)
    old = _stamp(days_ago=30)
    write_context_file(mgr.context_file, [
        _entry("- recently proposed", hits=10, last_proposed=recent),
        _entry("- proposed long ago", hits=10, last_proposed=old),
        _entry("- never proposed", hits=10, last_proposed=""),
    ])
    cands = mgr.list_promotion_candidates(hit_threshold=5, cooldown_days=14)
    contents = {c.content for c in cands}
    assert "- recently proposed" not in contents
    assert "- proposed long ago" in contents
    assert "- never proposed" in contents


def test_list_candidates_empty_when_no_entries(mgr: MemoryManager):
    cands = mgr.list_promotion_candidates(hit_threshold=5, cooldown_days=14)
    assert cands == []


def test_list_candidates_zero_threshold_returns_nothing(mgr: MemoryManager):
    """Defensive: a zero/negative threshold shouldn't propose everything."""
    write_context_file(mgr.context_file, [_entry("- anything", hits=1)])
    assert mgr.list_promotion_candidates(hit_threshold=0, cooldown_days=14) == []


# ── mark_proposed ───────────────────────────────────────────


def test_mark_proposed_bumps_last_proposed(mgr: MemoryManager):
    entry = _entry("- fact", hits=10)
    write_context_file(mgr.context_file, [entry])

    mgr.mark_proposed([entry.id])

    after = mgr._read_context_entries()
    assert after[0].last_proposed != ""
    # And the freshly-bumped entry should now be in cooldown
    cands = mgr.list_promotion_candidates(hit_threshold=5, cooldown_days=14)
    assert cands == []


def test_mark_proposed_ignores_unknown_ids(mgr: MemoryManager):
    entry = _entry("- fact", hits=10)
    write_context_file(mgr.context_file, [entry])
    mgr.mark_proposed(["ctx_does_not_exist"])
    after = mgr._read_context_entries()
    assert after[0].last_proposed == ""  # untouched


# ── consume_core_proposal ───────────────────────────────────


def test_consume_pin_moves_entry_to_core(mgr: MemoryManager):
    entry = _entry("- user prefers dark mode", hits=10)
    write_context_file(mgr.context_file, [entry])

    counts = mgr.consume_core_proposal({entry.id: "pin"})

    assert counts["pinned"] == 1
    assert mgr._read_context_entries() == []  # removed from CONTEXT
    assert "- user prefers dark mode" in mgr.read_core()


def test_consume_pin_dedupes_against_existing_core(mgr: MemoryManager):
    mgr.write_core("- user prefers dark mode")
    entry = _entry("- user prefers dark mode", hits=10)
    write_context_file(mgr.context_file, [entry])

    mgr.consume_core_proposal({entry.id: "pin"})

    # Core not duplicated
    core_lines = [l for l in mgr.read_core().splitlines() if l.strip()]
    assert core_lines.count("- user prefers dark mode") == 1


def test_consume_reject_marks_entry_permanently(mgr: MemoryManager):
    entry = _entry("- nope", hits=10)
    write_context_file(mgr.context_file, [entry])

    counts = mgr.consume_core_proposal({entry.id: "reject"})

    assert counts["rejected"] == 1
    after = mgr._read_context_entries()
    assert len(after) == 1
    assert after[0].core_status == "rejected"
    # And it never shows up as a candidate again
    cands = mgr.list_promotion_candidates(hit_threshold=5, cooldown_days=0)
    assert cands == []


def test_consume_skip_is_noop_on_state(mgr: MemoryManager):
    entry = _entry("- maybe later", hits=10)
    write_context_file(mgr.context_file, [entry])

    counts = mgr.consume_core_proposal({entry.id: "skip"})

    assert counts["skipped"] == 1
    after = mgr._read_context_entries()
    assert after[0].core_status == "none"
    assert mgr.read_core() == ""


def test_consume_mixed_decisions(mgr: MemoryManager):
    a = _entry("- pin me", hits=10)
    b = _entry("- reject me", hits=10)
    c = _entry("- skip me", hits=10)
    write_context_file(mgr.context_file, [a, b, c])

    counts = mgr.consume_core_proposal({a.id: "pin", b.id: "reject", c.id: "skip"})

    assert counts == {"pinned": 1, "rejected": 1, "skipped": 1}
    remaining = {e.content: e for e in mgr._read_context_entries()}
    assert set(remaining) == {"- reject me", "- skip me"}
    assert remaining["- reject me"].core_status == "rejected"
    assert remaining["- skip me"].core_status == "none"
    assert "- pin me" in mgr.read_core()


def test_consume_empty_decisions_is_noop(mgr: MemoryManager):
    entry = _entry("- fact", hits=10)
    write_context_file(mgr.context_file, [entry])
    counts = mgr.consume_core_proposal({})
    assert counts == {"pinned": 0, "rejected": 0, "skipped": 0}
    assert mgr._read_context_entries()[0].content == "- fact"


# ── Round-trip: core_status / last_proposed survive write+read ──


def test_metadata_round_trips_through_file(mgr: MemoryManager):
    proposed_at = _stamp(days_ago=2)
    entry = _entry("- rejected memory", hits=10,
                   core_status="rejected", last_proposed=proposed_at)
    write_context_file(mgr.context_file, [entry])

    re_read = mgr._read_context_entries()
    assert re_read[0].core_status == "rejected"
    assert re_read[0].last_proposed == proposed_at
