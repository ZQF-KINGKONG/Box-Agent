"""Periodic maintenance for CONTEXT.md: decay, archive cleanup, dedup.

The maintainer is invoked at CLI / ACP server startup. A timestamp guard
(``.maintainer_last_run`` inside the memory dir) caps the work to at most
one run per ``memory_maintainer_interval_hours`` window — repeated startups
are cheap no-ops.

Phases (all idempotent and safe to interrupt — each writes its file only
on change):

1. **decay**    — active entries with ``hits == 0`` and ``last_used``
   older than ``memory_decay_days`` move from CONTEXT.md to
   CONTEXT.archive.md (metadata preserved).
2. **cleanup**  — archive entries with ``last_used`` older than
   ``memory_decay_days + memory_archive_days`` move into
   ``<memory_dir>/trash/<YYYY-MM-DD>/`` as a dated archive snapshot.
3. **dedup**    — token-Jaccard similarity (default 0.85 threshold) on
   CONTEXT.md entries; near-duplicates merge into the entry with higher
   ``hits`` (ties broken by older ``created``). Merged metadata: hits
   summed, created = min, last_used = max, confidence = max.
4. **compact**  — LLM-driven topic-cluster merge when CONTEXT.md exceeds
   ``memory_context_max_entries`` or ``memory_context_max_tokens``.
   Schema-validated JSON output; failure keeps the original. Trash
   backup written before overwrite. Gated by ``memory_compaction_enabled``
   and the presence of an LLM client.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .memory import (
    ContextEntry,
    jaccard as _jaccard,
    parse_context_file,
    tokens as _tokens,
    write_context_file,
)

if TYPE_CHECKING:
    from .config import AgentConfig
    from .memory import MemoryManager

logger = logging.getLogger(__name__)


def _parse_iso_utc(stamp: str) -> datetime:
    """Parse a ``_now_iso`` string back to an aware UTC datetime.

    Tolerates absent timezone (treated as UTC) and falls back to ``now``
    on unparseable input so a corrupt entry doesn't block the whole run.
    """
    try:
        dt = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _now_iso_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class MemoryMaintainer:
    """Run periodic maintenance on CONTEXT.md / CONTEXT.archive.md.

    Construct once per process and call ``run_if_due()`` at startup.
    Internally all phases are sync I/O wrapped as async methods for
    uniformity with the rest of the codebase; they are fast for typical
    file sizes (≤ a few hundred entries).
    """

    def __init__(self, mgr: "MemoryManager", config: "AgentConfig", llm=None):
        self._mgr = mgr
        self._cfg = config
        self._llm = llm

    # ── Entry point ─────────────────────────────────────────────

    @property
    def _last_run_marker(self) -> Path:
        return self._mgr.memory_dir / ".maintainer_last_run"

    def _due(self, now: datetime) -> bool:
        if not self._cfg.memory_maintainer_enabled:
            return False
        marker = self._last_run_marker
        if not marker.exists():
            return True
        try:
            last = _parse_iso_utc(marker.read_text(encoding="utf-8").strip())
        except OSError:
            return True
        return (now - last) >= timedelta(hours=self._cfg.memory_maintainer_interval_hours)

    async def run_if_due(self) -> bool:
        """Run maintenance phases when the time guard allows it.

        Returns True if maintenance ran, False if skipped (disabled or
        marker too recent). All phases are best-effort: a failure in one
        phase is logged and the rest still execute.
        """
        now = datetime.now(timezone.utc)
        if not self._due(now):
            return False

        logger.info("MemoryMaintainer: starting run at %s", now.isoformat())
        for phase_name, phase in (
            ("decay", self._decay),
            ("cleanup_archive", self._cleanup_archive),
            ("dedup", self._dedup),
            ("compact", self._compact),
        ):
            try:
                await phase(now)
            except Exception:
                logger.exception("MemoryMaintainer: %s phase failed", phase_name)

        try:
            self._last_run_marker.write_text(_now_iso_stamp() + "\n", encoding="utf-8")
        except OSError:
            logger.exception("MemoryMaintainer: could not write last-run marker")

        return True

    # ── Phase 1: decay ──────────────────────────────────────────

    async def _decay(self, now: datetime) -> None:
        threshold = now - timedelta(days=self._cfg.memory_decay_days)
        entries = parse_context_file(self._mgr.context_file)
        if not entries:
            return

        active: list[ContextEntry] = []
        to_archive: list[ContextEntry] = []
        for e in entries:
            if e.hits == 0 and _parse_iso_utc(e.last_used) < threshold:
                to_archive.append(e)
            else:
                active.append(e)

        if not to_archive:
            return

        existing_archive = parse_context_file(self._mgr.archive_file)
        write_context_file(self._mgr.archive_file, existing_archive + to_archive)
        write_context_file(self._mgr.context_file, active)
        logger.info(
            "MemoryMaintainer: decayed %d entries to archive (active=%d)",
            len(to_archive), len(active),
        )

    # ── Phase 2: archive cleanup → trash ────────────────────────

    async def _cleanup_archive(self, now: datetime) -> None:
        cutoff_days = self._cfg.memory_decay_days + self._cfg.memory_archive_days
        threshold = now - timedelta(days=cutoff_days)
        entries = parse_context_file(self._mgr.archive_file)
        if not entries:
            return

        keep: list[ContextEntry] = []
        purge: list[ContextEntry] = []
        for e in entries:
            if _parse_iso_utc(e.last_used) < threshold:
                purge.append(e)
            else:
                keep.append(e)

        if not purge:
            return

        date_dir = self._mgr.trash_dir / now.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        trash_file = date_dir / f"context-archive-{now.strftime('%H%M%S')}.md"
        write_context_file(trash_file, purge)
        write_context_file(self._mgr.archive_file, keep)
        logger.info(
            "MemoryMaintainer: purged %d archive entries to %s",
            len(purge), trash_file,
        )

    # ── Phase 3: dedup ──────────────────────────────────────────

    async def _dedup(self, _now: datetime) -> None:
        threshold = self._cfg.memory_dedup_jaccard
        entries = parse_context_file(self._mgr.context_file)
        if len(entries) < 2:
            return

        # Greedy: pre-tokenize, then merge low-priority into high-priority.
        # Priority key: (hits desc, created asc) — most-used + oldest wins.
        token_cache: list[set[str]] = [_tokens(e.content) for e in entries]
        indices = sorted(
            range(len(entries)),
            key=lambda i: (-entries[i].hits, entries[i].created),
        )

        merged_into: dict[int, int] = {}  # loser_idx → winner_idx
        for pos, winner in enumerate(indices):
            if winner in merged_into:
                continue
            for loser in indices[pos + 1:]:
                if loser in merged_into:
                    continue
                if _jaccard(token_cache[winner], token_cache[loser]) >= threshold:
                    merged_into[loser] = winner

        if not merged_into:
            return

        # Apply merges: aggregate metadata into winners, drop losers.
        for loser_idx, winner_idx in merged_into.items():
            w = entries[winner_idx]
            l = entries[loser_idx]
            w.hits += l.hits
            if l.created < w.created:
                w.created = l.created
            if l.last_used > w.last_used:
                w.last_used = l.last_used
            if l.confidence > w.confidence:
                w.confidence = l.confidence

        kept = [e for i, e in enumerate(entries) if i not in merged_into]
        write_context_file(self._mgr.context_file, kept)
        logger.info(
            "MemoryMaintainer: deduped %d → %d entries (merged %d)",
            len(entries), len(kept), len(merged_into),
        )


# ── Phase 4: LLM-driven topic compaction ──────────────────────

_COMPACT_SYSTEM_PROMPT = """你是一个负责整理用户记忆的助手。

输入：N 条用户事实/偏好记录，每条带 id 和 hits（命中次数）。
任务：把主题相近的记录合并成更概括的一条，输出更少但信息密度更高的列表。

严格规则：
1. **必须保留所有具体偏好、规则、禁止项**（如"禁止 pip 直装"必须完整保留，不能被泛化稀释）
2. **绝对不允许引入原文中未出现的事实或推断**
3. 合并后的 hits = 来源条目 hits 之和
4. 不应合并的孤立事实保持原样（content 复用原文，hits 不变）
5. 输出**纯 JSON 数组**，无注释、无 markdown 围栏，每个元素形如：
   {"content": "<合并后的内容>", "hits": <int>, "sources": ["<原 id1>", "<原 id2>", ...]}

合并示例：
输入：
- id=a, hits=5: user generating brazil football intro ppt
- id=b, hits=3: user generating spain football intro ppt
- id=c, hits=2: user generating germany football ppt
输出（其中一条）：
{"content": "用户经常生成各国足球队介绍 PPT（巴西/西班牙/德国等）", "hits": 10, "sources": ["a", "b", "c"]}

不应合并的示例（强偏好独立保留）：
输入：
- id=d, hits=12: project uses uv for dependency management, never use pip directly
输出（原样保留）：
{"content": "project uses uv for dependency management, never use pip directly", "hits": 12, "sources": ["d"]}
"""


def _estimate_tokens(entries: list[ContextEntry]) -> int:
    """Cheap char-based token estimate. Avoids importing a real tokenizer."""
    return sum(len(e.content) for e in entries) // 3


def _parse_compact_output(text: str, valid_ids: set[str]) -> list[dict] | None:
    """Strip code fences, parse JSON, validate schema. Returns ``None`` on failure."""
    import json as _json

    cleaned = text.strip()
    if cleaned.startswith("```"):
        # drop fence
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        data = _json.loads(cleaned)
    except (_json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, list) or not data:
        return None

    seen_sources: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            return None
        content = item.get("content")
        hits = item.get("hits")
        sources = item.get("sources")
        if not isinstance(content, str) or not content.strip():
            return None
        if not isinstance(hits, int) or hits < 0:
            return None
        if not isinstance(sources, list) or not sources:
            return None
        for sid in sources:
            if not isinstance(sid, str) or sid not in valid_ids:
                return None
            seen_sources.add(sid)
    return data


class MemoryMaintainer_Compact:  # placeholder so the file parses; will be inlined.
    """Phase 4 helpers — methods are bound to ``MemoryMaintainer`` below."""

    async def _compact(self, now: datetime) -> None:
        if not self._cfg.memory_compaction_enabled or self._llm is None:
            return

        entries = parse_context_file(self._mgr.context_file)
        if len(entries) < 2:
            return

        # Trigger only when over capacity (entry count or token budget).
        max_entries = self._cfg.memory_context_max_entries
        max_tokens = self._cfg.memory_context_max_tokens
        if len(entries) <= max_entries and _estimate_tokens(entries) <= max_tokens:
            return

        from .schema import Message as Msg

        bullet_lines = [
            f"- id={e.id}, hits={e.hits}: {e.content.strip()}"
            for e in entries
        ]
        user_prompt = "请整理以下 {n} 条记忆：\n\n{body}".format(
            n=len(entries), body="\n".join(bullet_lines),
        )

        try:
            response = await self._llm.generate(
                messages=[
                    Msg(role="system", content=_COMPACT_SYSTEM_PROMPT),
                    Msg(role="user", content=user_prompt),
                ]
            )
        except Exception:
            logger.exception("MemoryMaintainer: compact LLM call failed; keeping original")
            return

        valid_ids = {e.id for e in entries}
        parsed = _parse_compact_output(response.content or "", valid_ids)
        if parsed is None:
            logger.warning("MemoryMaintainer: compact output invalid; keeping original")
            return

        # Backup before overwrite.
        from datetime import datetime as _dt
        trash_dir = self._mgr.trash_dir / _dt.now().strftime("%Y-%m-%d") / "compact"
        try:
            trash_dir.mkdir(parents=True, exist_ok=True)
            backup_path = trash_dir / f"CONTEXT.{_now_iso_stamp()}.md"
            backup_path.write_text(
                self._mgr.context_file.read_text(encoding="utf-8") if self._mgr.context_file.exists() else "",
                encoding="utf-8",
            )
        except OSError:
            logger.exception("MemoryMaintainer: compact backup failed; aborting")
            return

        # Build new entries — preserve oldest created + most-recent last_used + max confidence
        # from source entries; assign fresh ids.
        from .memory import _new_entry as _make_entry
        by_id = {e.id: e for e in entries}
        new_entries: list[ContextEntry] = []
        for item in parsed:
            sources = [by_id[sid] for sid in item["sources"]]
            new = _make_entry(item["content"], source="compact")
            new.hits = item["hits"]
            new.created = min(s.created for s in sources)
            new.last_used = max(s.last_used for s in sources)
            new.confidence = max(s.confidence for s in sources)
            # If any source was promoted-rejected, keep that flag so rejected
            # facts can't sneak back into core through compaction.
            if any(s.core_status == "rejected" for s in sources):
                new.core_status = "rejected"
            new_entries.append(new)

        write_context_file(self._mgr.context_file, new_entries)
        logger.info(
            "MemoryMaintainer: compacted %d → %d entries (backup=%s)",
            len(entries), len(new_entries), backup_path,
        )


# Bind _compact onto the real MemoryMaintainer class (defined above) so the
# phase loop at run_if_due can resolve self._compact uniformly.
MemoryMaintainer._compact = MemoryMaintainer_Compact._compact  # type: ignore[attr-defined]
