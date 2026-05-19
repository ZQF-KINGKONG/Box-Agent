"""Memory system for cross-session recall, search, and auto-extraction.

Directory layout::

    ~/.box-agent/memory/
    ├── MEMORY.md          # Core memory (always injected into system prompt)
    └── CONTEXT.md         # Searchable context (retrieved on demand)
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import Message

logger = logging.getLogger(__name__)


# ── Token / Jaccard helpers (shared with MemoryMaintainer) ──────

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokens(text: str) -> set[str]:
    """Lowercase word-character tokens for Jaccard similarity.

    Unicode-aware: handles CJK runs as single tokens, so 中文+英文
    混排 content lines remain comparable.
    """
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def jaccard(a: set[str], b: set[str]) -> float:
    """Symmetric set-overlap ratio. 0.0 when either side is empty."""
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


# ── Context entry: metadata-bearing record stored in CONTEXT.md ──

@dataclass
class ContextEntry:
    """One context-memory record with metadata.

    Stored in CONTEXT.md as an HTML comment header followed by a content
    block. ``hits``/``last_used`` mutate over time; everything else is set
    at creation.
    """
    id: str
    content: str
    created: str  # ISO-8601 UTC, second precision
    last_used: str
    hits: int = 0
    source: str = "tool"  # "tool" | "extractor" | "legacy" | "user"
    confidence: float = 1.0
    # Promotion-to-core tracking. ``core_status`` is "none" by default;
    # set to "rejected" after the user permanently declines promotion.
    # ``last_proposed`` is bumped each time the entry is offered for
    # core promotion so the cooldown skips noisy candidates.
    core_status: str = "none"  # "none" | "rejected"
    last_proposed: str = ""  # ISO-8601 UTC or empty if never proposed


_ENTRY_HEADER_RE = re.compile(r"^\s*<!--\s*ctx\s+(.+?)\s*-->\s*$")
_ENTRY_KV_RE = re.compile(r"(\w+)=(\S+)")


def _now_iso() -> str:
    """UTC ISO-8601 timestamp at second precision (no microseconds, no TZ suffix)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _new_entry_id() -> str:
    """Sortable, collision-resistant id: ``ctx_<utc>_<rand6>``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"ctx_{stamp}_{uuid.uuid4().hex[:6]}"


def _new_entry(content: str, *, source: str = "tool", confidence: float = 1.0) -> ContextEntry:
    now = _now_iso()
    return ContextEntry(
        id=_new_entry_id(),
        content=content.strip(),
        created=now,
        last_used=now,
        hits=0,
        source=source,
        confidence=confidence,
    )


def _format_entry_header(e: ContextEntry) -> str:
    parts = [
        f"id={e.id}",
        f"created={e.created}",
        f"last_used={e.last_used}",
        f"hits={e.hits}",
        f"source={e.source}",
        f"confidence={e.confidence:.2f}",
    ]
    if e.core_status and e.core_status != "none":
        parts.append(f"core_status={e.core_status}")
    if e.last_proposed:
        parts.append(f"last_proposed={e.last_proposed}")
    return "<!-- ctx " + " ".join(parts) + " -->"


def _parse_entry_header(line: str) -> dict[str, str] | None:
    m = _ENTRY_HEADER_RE.match(line)
    if not m:
        return None
    return dict(_ENTRY_KV_RE.findall(m.group(1)))


def parse_context_file(path: Path) -> list[ContextEntry]:
    """Parse CONTEXT.md into entries. Auto-detects legacy line-based format.

    Legacy format (no ``<!-- ctx ... -->`` headers): each non-empty line
    becomes a separate entry with default metadata and ``source="legacy"``.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return _parse_context_text(text)


def _parse_context_text(text: str) -> list[ContextEntry]:
    lines = text.splitlines()
    has_headers = any(_ENTRY_HEADER_RE.match(l) for l in lines)

    if not has_headers:
        return [
            _new_entry(line, source="legacy")
            for line in lines
            if line.strip()
        ]

    entries: list[ContextEntry] = []
    i = 0
    while i < len(lines):
        meta = _parse_entry_header(lines[i])
        if meta is None:
            i += 1
            continue
        i += 1
        content_lines: list[str] = []
        while i < len(lines) and _parse_entry_header(lines[i]) is None:
            content_lines.append(lines[i])
            i += 1
        while content_lines and not content_lines[-1].strip():
            content_lines.pop()
        while content_lines and not content_lines[0].strip():
            content_lines.pop(0)
        content = "\n".join(content_lines).strip()
        if not content:
            continue
        try:
            entries.append(ContextEntry(
                id=meta.get("id") or _new_entry_id(),
                content=content,
                created=meta.get("created") or _now_iso(),
                last_used=meta.get("last_used") or meta.get("created") or _now_iso(),
                hits=int(meta.get("hits", "0")),
                source=meta.get("source") or "legacy",
                confidence=float(meta.get("confidence", "1.0")),
                core_status=meta.get("core_status") or "none",
                last_proposed=meta.get("last_proposed") or "",
            ))
        except (ValueError, TypeError):
            logger.warning("Bad ContextEntry metadata, using defaults: %s", meta)
            entries.append(_new_entry(content, source="legacy"))
    return entries


def write_context_file(path: Path, entries: list[ContextEntry]) -> None:
    """Serialize entries to CONTEXT.md in the metadata-bearing format."""
    if not entries:
        path.write_text("", encoding="utf-8")
        return
    parts: list[str] = []
    for e in entries:
        parts.append(_format_entry_header(e))
        parts.append(e.content)
        parts.append("")  # blank line between entries
    text = "\n".join(parts).rstrip() + "\n"
    path.write_text(text, encoding="utf-8")


class MemoryManager:
    """Dual-file memory: MEMORY.md (core) + CONTEXT.md (searchable).

    - **MEMORY.md** — user identity, preferences, writing style.
      Always injected into the system prompt via ``recall()``.
      Written by LLM via ``memory_write(category="core")``.

    - **CONTEXT.md** — project context, task patterns, behavioral feedback.
      Retrieved on demand via ``memory_search`` tool.
      Written by ``memory_write(category="context")`` and ``MemoryExtractor``.
    """

    def __init__(
        self,
        memory_dir: str = "~/.box-agent/memory",
        *,
        dedup_jaccard_threshold: float = 0.85,
        **_kwargs,
    ):
        self.memory_dir = Path(memory_dir).expanduser()
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.dedup_jaccard_threshold = dedup_jaccard_threshold

    # ── File paths ──────────────────────────────────────────────

    @property
    def memory_file(self) -> Path:
        """MEMORY.md — core memory, always injected."""
        return self.memory_dir / "MEMORY.md"

    @property
    def context_file(self) -> Path:
        """CONTEXT.md — searchable context, retrieved on demand."""
        return self.memory_dir / "CONTEXT.md"

    @property
    def archive_file(self) -> Path:
        """CONTEXT.archive.md — cold storage for decayed entries (not injected, not searched)."""
        return self.memory_dir / "CONTEXT.archive.md"

    @property
    def trash_dir(self) -> Path:
        """Soft-delete root for purged entries. Lazy-created on first write."""
        return self.memory_dir / "trash"

    # ── Core memory (MEMORY.md) ─────────────────────────────────

    def read_core(self) -> str:
        """Read MEMORY.md content. Returns empty string if missing."""
        if not self.memory_file.exists():
            return ""
        return self.memory_file.read_text(encoding="utf-8").strip()

    def write_core(self, content: str) -> None:
        """Overwrite MEMORY.md with *content*."""
        self.memory_file.write_text(content.strip() + "\n", encoding="utf-8")

    def append_core(self, content: str) -> None:
        """Append to MEMORY.md."""
        existing = self.read_core()
        if existing:
            self.write_core(f"{existing}\n{content.strip()}")
        else:
            self.write_core(content)

    # Legacy aliases — backward compat for existing callers/tests
    read_all = read_core
    write_all = write_core
    read_manual_memory = read_core
    write_manual_memory = write_core

    # ── Context memory (CONTEXT.md) ─────────────────────────────

    def read_context(self) -> str:
        """Read CONTEXT.md as plain text (entries' content joined by newline)."""
        entries = self._read_context_entries()
        if not entries:
            return ""
        return "\n".join(e.content for e in entries).strip()

    def write_context(self, content: str) -> None:
        """Overwrite CONTEXT.md with *content* (creates fresh entries, one per line).

        Destructive — drops metadata of any existing entries. Used by callers
        that already hold the desired final text (tests, legacy paths). For
        non-destructive updates use ``append_context`` / ``apply_context_operations``.
        """
        entries = [
            _new_entry(line, source="tool")
            for line in content.splitlines()
            if line.strip()
        ]
        self._write_context_entries(entries)

    def append_context(self, content: str) -> None:
        """Append to CONTEXT.md, skipping lines already present in Core or Context.

        Two-tier dedup:

        1. Exact line-level (case-insensitive) — catches verbatim repeats.
        2. Token-Jaccard fuzzy match against existing entries — catches
           paraphrased restatements of the same fact. On match, the existing
           entry's ``hits`` is bumped and ``last_used`` refreshed instead of
           adding a new entry.

        Existing entries' metadata (hits, created, etc.) is preserved.
        """
        existing = self.read_context()
        filtered = self._dedupe_context_lines(content, existing_context=existing)

        if not filtered:
            return

        existing_entries = self._read_context_entries()
        threshold = self.dedup_jaccard_threshold
        entry_tokens = [tokens(e.content) for e in existing_entries]

        new_entries: list[ContextEntry] = []
        merged_any = False
        now = _now_iso()

        for line in filtered:
            line_tokens = tokens(line)
            best_idx = -1
            best_score = 0.0
            if line_tokens:
                for idx, et in enumerate(entry_tokens):
                    score = jaccard(line_tokens, et)
                    if score > best_score:
                        best_score = score
                        best_idx = idx

            if best_idx >= 0 and best_score >= threshold:
                existing_entries[best_idx].hits += 1
                existing_entries[best_idx].last_used = now
                merged_any = True
            else:
                entry = _new_entry(line, source="tool")
                new_entries.append(entry)
                existing_entries.append(entry)
                entry_tokens.append(line_tokens)

        if not new_entries and not merged_any:
            return

        self._write_context_entries(existing_entries)

    def _read_context_entries(self) -> list[ContextEntry]:
        """Parse CONTEXT.md into entries (or empty list if missing)."""
        return parse_context_file(self.context_file)

    def _write_context_entries(self, entries: list[ContextEntry]) -> None:
        """Serialize entries to CONTEXT.md."""
        write_context_file(self.context_file, entries)

    def _dedupe_context_lines(self, content: str, *, existing_context: str | None = None) -> list[str]:
        """Return non-empty context lines not already present in Core or Context.

        Deduplication is intentionally line-level and case-insensitive so exact
        saved facts are not repeated while still allowing a later LLM merge to
        refine or replace older context lines.
        """
        core = self.read_core()
        existing_context = self.read_context() if existing_context is None else existing_context

        seen = {
            line.strip().lower()
            for source in (core, existing_context)
            for line in source.splitlines()
            if line.strip()
        }

        filtered: list[str] = []
        for line in content.strip().splitlines():
            normalized = line.strip().lower()
            if normalized and normalized not in seen:
                filtered.append(line)
                seen.add(normalized)
        return filtered

    # ── Search ──────────────────────────────────────────────────

    def search(self, query: str) -> list[str]:
        """Keyword search across CONTEXT.md entries.

        Returns matched lines (case-insensitive). Side effect: increments
        ``hits`` and refreshes ``last_used`` on each matched entry, then
        persists the file. Persistence is synchronous (small file, infrequent).
        """
        if not query:
            return []
        entries = self._read_context_entries()
        if not entries:
            return []

        query_lower = query.lower()
        matched: list[str] = []
        changed = False
        now = _now_iso()

        for entry in entries:
            hit = False
            for line in entry.content.splitlines():
                stripped = line.strip()
                if stripped and query_lower in stripped.lower():
                    matched.append(line)
                    hit = True
            if hit:
                entry.hits += 1
                entry.last_used = now
                changed = True

        if changed:
            self._write_context_entries(entries)

        return matched

    def auto_match_context(self, query: str, *, limit: int = 3) -> list[dict[str, str]]:
        """Return high-confidence context-memory matches for a user prompt.

        This is intentionally conservative: it only returns context lines that
        share strong phrase/token overlap with the prompt.  The result is meant
        to provide *possibly relevant* context, never to force the model to
        treat a new request as a continuation of an old task.

        Side effect: increments ``hits`` and refreshes ``last_used`` on each
        entry whose content matched at least one returned line.
        """
        query = _sanitize_auto_match_query(query)
        entries = self._read_context_entries()
        if not query or not entries:
            return []

        query_lower = query.lower()
        query_terms = _extract_match_terms(query_lower)
        if not query_terms:
            return []

        # (score, line_no, text, entry_index) — line_no is globally indexed
        # across joined content so callers keep stable ids.
        scored: list[tuple[float, int, str, int]] = []
        line_no = 0
        for entry_idx, entry in enumerate(entries):
            for raw_line in entry.content.splitlines():
                line_no += 1
                text = raw_line.strip()
                if not text:
                    continue
                if _should_skip_auto_match_line(query_lower, text.lower()):
                    continue
                score = _score_memory_match(query_lower, query_terms, text.lower())
                if score >= 2.0:
                    scored.append((score, line_no, text, entry_idx))

        scored.sort(key=lambda item: (-item[0], item[1]))
        top = scored[:limit]

        if top:
            now = _now_iso()
            hit_entry_indices = {entry_idx for _, _, _, entry_idx in top}
            for idx in hit_entry_indices:
                entries[idx].hits += 1
                entries[idx].last_used = now
            self._write_context_entries(entries)

        return [
            {
                "id": f"context:{line_no}",
                "source": "context",
                "category": "context",
                "text": text,
            }
            for _, line_no, text, _ in top
        ]

    # ── Recall (system prompt injection) ────────────────────────

    def recall(self, **_kwargs) -> str:
        """Build a memory block for system-prompt injection.

        Only injects MEMORY.md (core).  CONTEXT.md is accessed on demand
        via ``memory_search`` tool.
        """
        core = self.read_core()
        if not core:
            return ""
        return self.build_memory_block(core)

    # ── OpenClaw import ─────────────────────────────────────────

    @property
    def _openclaw_imported_marker(self) -> Path:
        return self.memory_dir / ".openclaw_imported"

    def _read_openclaw_raw(self) -> str:
        """Read MEMORY.md and USER.md files from ~/.openclaw/. Returns empty if none."""
        openclaw_dir = Path.home() / ".openclaw"
        if not openclaw_dir.is_dir():
            return ""

        parts: list[str] = []

        # USER.md — user identity and preferences
        for user_file in sorted(openclaw_dir.rglob("USER.md")):
            try:
                content = user_file.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"[Source: {user_file.relative_to(openclaw_dir)}]\n{content}")
            except Exception:
                logger.debug("Failed to read OpenClaw file: %s", user_file)

        # MEMORY.md — session memories
        for memory_file in sorted(openclaw_dir.rglob("MEMORY.md")):
            try:
                content = memory_file.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"[Source: {memory_file.relative_to(openclaw_dir)}]\n{content}")
            except Exception:
                logger.debug("Failed to read OpenClaw file: %s", memory_file)

        return "\n\n".join(parts)

    async def import_openclaw(self, llm) -> str:
        """One-time LLM-filtered import of OpenClaw data into Core.

        Reads ``~/.openclaw/**/USER.md`` and ``**/MEMORY.md``, asks LLM
        to extract useful user info (identity, preferences, habits),
        appends to MEMORY.md, and marks as imported so it won't run again.

        Returns the imported content, or empty string if nothing to import.
        """
        if self._openclaw_imported_marker.exists():
            return ""

        raw = self._read_openclaw_raw()
        if not raw:
            self._openclaw_imported_marker.write_text("no-content\n", encoding="utf-8")
            return ""

        existing_core = self.read_core()

        from .schema import Message as Msg

        prompt = (
            "Extract ONLY the useful user information from the following content.\n\n"
            "Keep:\n"
            "- User identity (name, role, department, company)\n"
            "- Preferences (language, writing style, tools)\n"
            "- Work habits and behavioral patterns\n\n"
            "Discard:\n"
            "- Ephemeral task details, file paths, code snippets\n"
            "- Session logs, timestamps, debugging info\n"
            "- Anything already present in existing memory\n\n"
            f"Existing core memory:\n{existing_core or '(empty)'}\n\n"
            f"Content to filter:\n{raw[:8000]}\n\n"
            "Output ONLY the useful bullet points (markdown format), nothing else. "
            "If nothing is useful, output exactly: (empty)"
        )

        try:
            response = await llm.generate(
                messages=[
                    Msg(role="system", content="You extract structured user information from raw notes."),
                    Msg(role="user", content=prompt),
                ]
            )
            filtered = response.content.strip()
        except Exception:
            logger.exception("Failed to filter OpenClaw memory via LLM")
            return ""

        if filtered and filtered != "(empty)":
            self.append_core(filtered)
            logger.info("Imported OpenClaw memory into core: %d chars", len(filtered))

        self._openclaw_imported_marker.write_text("done\n", encoding="utf-8")
        return filtered

    @staticmethod
    def build_memory_block(core: str) -> str:
        """Format core memory into a prompt block."""
        if not core:
            return ""

        parts: list[str] = ["--- MEMORY START ---"]
        parts.append("")
        parts.append("[Core Memory]")
        parts.append(core)
        parts.append("")
        parts.append("--- MEMORY END ---")
        return "\n".join(parts)

    # ── Shared helpers ─────────────────────────────────────────

    @staticmethod
    def _build_transcript(messages: list[Message], *, max_chars_per_msg: int = 2000) -> str:
        """Build a condensed text transcript from messages, skipping system messages."""
        parts: list[str] = []
        for msg in messages:
            if msg.role == "system":
                continue
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            parts.append(f"{msg.role.capitalize()}: {text[:max_chars_per_msg]}")
        return "\n".join(parts)

    async def update_context_with_llm(self, content: str, llm) -> str:
        """Ask an LLM how to merge candidate context, then safely apply it.

        The model decides semantic add/replace/drop/noop operations, while this
        method enforces exact-match mutations and line-level duplicate guards.

        Returns:
            A short status label: ``"applied"``, ``"no_change"``, or
            ``"fallback_appended"``.
        """
        if not content.strip():
            return "no_change"

        from .schema import Message as Msg

        context = self.read_context()
        prompt = _CONTEXT_UPDATE_USER_PROMPT.format(
            core_memory=self.read_core() or "(empty)",
            context_memory=context or "(empty)",
            candidate=content.strip(),
        )

        try:
            response = await llm.generate(
                messages=[
                    Msg(role="system", content=_CONTEXT_UPDATE_SYSTEM_PROMPT),
                    Msg(role="user", content=prompt),
                ]
            )
            data = json.loads(_strip_json_fences(response.content))
        except Exception:
            logger.exception("Context memory update planning failed; falling back to append")
            before = self.read_context()
            self.append_context(content)
            return "fallback_appended" if self.read_context() != before else "no_change"

        changed = self.apply_context_operations(data.get("operations", []))
        return "applied" if changed else "no_change"

    def apply_context_operations(self, operations: list[dict]) -> bool:
        """Safely apply model-planned context memory operations.

        ``replace`` and ``drop`` require exactly one entry whose content matches
        the target string. ``add`` uses the same Core/Context dedupe guard as
        direct appends. Entry metadata (hits, created) is preserved across
        replace/drop; only ``last_used`` bumps on replace.
        """
        entries = self._read_context_entries()
        core_norm = {
            line.strip().lower()
            for line in self.read_core().splitlines()
            if line.strip()
        }
        changed = False

        for op in operations:
            action = str(op.get("action", "")).strip().lower()

            if action == "replace":
                old = str(op.get("old", "")).strip()
                new = str(op.get("new", "")).strip()
                if not old or not new:
                    continue
                indices = [i for i, e in enumerate(entries) if e.content.strip() == old]
                if len(indices) != 1:
                    if len(indices) > 1:
                        logger.warning("Ambiguous context memory replace skipped (%d matches): %s", len(indices), old[:80])
                    else:
                        logger.debug("Context memory replace target not found: %s", old[:80])
                    continue
                new_norm = new.lower()
                others_norm = {
                    e.content.strip().lower()
                    for i, e in enumerate(entries) if i != indices[0]
                }
                if new_norm in others_norm or new_norm in core_norm:
                    entries.pop(indices[0])
                else:
                    entries[indices[0]].content = new
                    entries[indices[0]].last_used = _now_iso()
                changed = True

            elif action == "drop":
                content = str(op.get("content", "")).strip()
                if not content:
                    continue
                indices = [i for i, e in enumerate(entries) if e.content.strip() == content]
                if len(indices) != 1:
                    if len(indices) > 1:
                        logger.warning("Ambiguous context memory drop skipped (%d matches): %s", len(indices), content[:80])
                    continue
                entries.pop(indices[0])
                changed = True

            elif action == "add":
                content = str(op.get("content", "")).strip()
                if not content:
                    continue
                existing_norm = {e.content.strip().lower() for e in entries}
                for line in content.splitlines():
                    norm = line.strip().lower()
                    if not norm or norm in existing_norm or norm in core_norm:
                        continue
                    existing_norm.add(norm)
                    entries.append(_new_entry(line, source="tool"))
                    changed = True

            elif action == "noop":
                continue

        if changed:
            self._write_context_entries(entries)
        return changed

    # ── Core-promotion candidates ───────────────────────────────

    def list_promotion_candidates(
        self,
        *,
        hit_threshold: int,
        cooldown_days: int,
    ) -> list[ContextEntry]:
        """Return CONTEXT.md entries eligible for promotion to MEMORY.md (core).

        Filters:
        - ``hits >= hit_threshold``
        - ``core_status != "rejected"`` (rejection is permanent)
        - ``last_proposed`` either empty or older than ``cooldown_days``
        - ``source != "core"`` (never re-propose core-originated material)
        """
        if hit_threshold <= 0:
            return []
        entries = self._read_context_entries()
        if not entries:
            return []
        now = datetime.now(timezone.utc)
        cooldown = timedelta(days=max(cooldown_days, 0))
        candidates: list[ContextEntry] = []
        for e in entries:
            if e.hits < hit_threshold:
                continue
            if e.core_status == "rejected":
                continue
            if e.source == "core":
                continue
            if e.last_proposed:
                try:
                    last = datetime.fromisoformat(e.last_proposed)
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    if now - last < cooldown:
                        continue
                except (TypeError, ValueError):
                    pass
            candidates.append(e)
        return candidates

    def mark_proposed(self, candidate_ids: list[str]) -> None:
        """Bump ``last_proposed`` on the given entries and persist."""
        if not candidate_ids:
            return
        entries = self._read_context_entries()
        wanted = set(candidate_ids)
        now = _now_iso()
        changed = False
        for e in entries:
            if e.id in wanted:
                e.last_proposed = now
                changed = True
        if changed:
            self._write_context_entries(entries)

    def consume_core_proposal(self, decisions: dict[str, str]) -> dict[str, int]:
        """Apply user decisions to promotion candidates.

        ``decisions`` maps entry id → ``"pin"``, ``"skip"``, or ``"reject"``.

        - ``pin``: remove entry from CONTEXT.md, append its content to
          MEMORY.md (skipping if the same line already exists in core).
        - ``reject``: keep entry in CONTEXT.md but flip
          ``core_status="rejected"`` so it is never proposed again.
        - ``skip``: no-op. ``last_proposed`` was already bumped at emit
          time, so the cooldown carries the user past this candidate.

        Returns counts for each action ({"pinned": int, "rejected": int,
        "skipped": int}).
        """
        if not decisions:
            return {"pinned": 0, "rejected": 0, "skipped": 0}

        entries = self._read_context_entries()
        if not entries:
            return {"pinned": 0, "rejected": 0, "skipped": 0}

        pinned_contents: list[str] = []
        keep: list[ContextEntry] = []
        counts = {"pinned": 0, "rejected": 0, "skipped": 0}

        for e in entries:
            decision = decisions.get(e.id)
            if decision == "pin":
                pinned_contents.append(e.content)
                counts["pinned"] += 1
                continue
            if decision == "reject":
                e.core_status = "rejected"
                counts["rejected"] += 1
            elif decision == "skip":
                counts["skipped"] += 1
            keep.append(e)

        if pinned_contents:
            core = self.read_core()
            core_lines_norm = {
                line.strip().lower()
                for line in core.splitlines()
                if line.strip()
            }
            to_append: list[str] = []
            for content in pinned_contents:
                for line in content.splitlines():
                    norm = line.strip().lower()
                    if not norm or norm in core_lines_norm:
                        continue
                    core_lines_norm.add(norm)
                    to_append.append(line)
            if to_append:
                if core:
                    self.write_core(core + "\n" + "\n".join(to_append))
                else:
                    self.write_core("\n".join(to_append))

        if counts["pinned"] or counts["rejected"]:
            self._write_context_entries(keep)
        return counts


# ── Auto Memory Extraction ────────────────────────────────────────

_EXTRACTION_SYSTEM_PROMPT = "You are a memory extraction assistant. You analyze conversations to identify information worth remembering across sessions."

_EXTRACTION_USER_PROMPT = """\
Analyze the recent conversation below. Extract information worth remembering across sessions.

Categories to look for:
- User info: name, role, team, expertise, background
- Preferences: language, communication style, tools, workflows
- Project context: goals, constraints, key decisions, deadlines
- Behavioral feedback: corrections the user made, approaches that worked

Existing core memory (MEMORY.md — do NOT duplicate):
{core_memory}

Existing context memory (CONTEXT.md — check for duplicates before adding):
{context_memory}

Recent conversation:
{transcript}

Rules:
1. Only extract cross-session-valuable information. Ignore ephemeral task details.
2. If new info updates or refines something in context memory, output a merge.
3. If info is genuinely new, output an addition.
4. Do NOT record code details, git operations, file paths, or anything derivable from the codebase.
5. If there is nothing worth remembering, return empty arrays.

Output ONLY valid JSON (no markdown fences):
{{"additions": ["- bullet point 1", "- bullet point 2"], "merges": [{{"old": "exact old line", "new": "replacement line"}}]}}"""

_CONTEXT_UPDATE_SYSTEM_PROMPT = (
    "You are a long-term memory curator. You update persistent context memory "
    "by preserving useful project/task context, merging semantic duplicates, "
    "and discarding ephemeral details."
)

_CONTEXT_UPDATE_USER_PROMPT = """\
Decide how to update CONTEXT.md using the candidate memory.

Existing core memory (MEMORY.md — do NOT duplicate into context):
{core_memory}

Existing context memory (CONTEXT.md):
{context_memory}

Candidate memory to save:
{candidate}

Rules:
1. Keep only cross-session-useful project context, task patterns, decisions, deadlines, or behavioral feedback.
2. If the candidate duplicates existing context semantically, do not add it.
3. If the candidate refines an existing line, replace that exact old line with one better line.
4. Do not duplicate core memory into context.
5. Do not rewrite the whole file. Prefer minimal add/replace/drop/noop operations.
6. For replace/drop, old/content MUST exactly match one full existing context line.

Output ONLY valid JSON (no markdown fences):
{{"operations": [
  {{"action": "add", "content": "- new memory line", "reason": "why it should be saved"}},
  {{"action": "replace", "old": "- exact old line", "new": "- improved line", "reason": "why it refines old memory"}},
  {{"action": "drop", "content": "- exact old line", "reason": "why existing line should be removed"}},
  {{"action": "noop", "content": "- candidate line", "reason": "why nothing should change"}}
]}}"""


def _strip_json_fences(text: str) -> str:
    """Strip optional markdown fences around model JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = "\n".join(text.split("\n")[:-1])
    return text.strip()


def _extract_match_terms(text: str) -> list[str]:
    """Extract conservative phrase-like terms from a prompt or memory line."""
    terms: set[str] = set()

    for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text):
        terms.add(token)

    for segment in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(segment) <= 6:
            terms.add(segment)
        else:
            for size in (6, 5, 4):
                for idx in range(0, len(segment) - size + 1):
                    terms.add(segment[idx:idx + size])

    return sorted(terms, key=lambda term: (-len(term), term))


def _sanitize_auto_match_query(query: str) -> str:
    """Remove host-appended operational instructions before auto matching."""
    text = query.strip()
    if not text:
        return ""

    markers = (
        "[文件输出规范]",
        "文件输出规范",
        "通用文件输出规范",
        "文件交付偏好",
        "通用文件交付规则",
    )
    cut = len(text)
    for marker in markers:
        idx = text.find(marker)
        if idx > 0:
            cut = min(cut, idx)
    return text[:cut].strip()


def _should_skip_auto_match_line(query_lower: str, memory_lower: str) -> bool:
    """Filter broad operational memories unless the user explicitly asks for them."""
    operational_markers = (
        "文件输出规范",
        "文件交付",
        "zip",
        "下载链接",
        "打包",
    )
    if any(marker in memory_lower for marker in operational_markers):
        user_asks_delivery = any(marker in query_lower for marker in operational_markers)
        if not user_asks_delivery:
            return True

    meta_markers = (
        "会话标题",
        "标题提炼",
        "第一条输入",
        "元指令前缀",
        "查询/记忆中查询",
    )
    if any(marker in memory_lower for marker in meta_markers):
        user_asks_title = any(marker in query_lower for marker in ("标题", "命名", "提炼"))
        if not user_asks_title:
            return True

    return False


def _score_memory_match(query_lower: str, query_terms: list[str], memory_lower: str) -> float:
    """Score prompt/context overlap with a high threshold for auto matching."""
    if query_lower and query_lower in memory_lower:
        return 10.0

    matched = [term for term in query_terms if term in memory_lower]
    if not matched:
        return 0.0

    score = 0.0
    long_matches = 0
    for term in matched:
        if re.search(r"[\u4e00-\u9fff]", term):
            if len(term) >= 6:
                score += 2.5
                long_matches += 1
            elif len(term) >= 4:
                score += 1.25
            else:
                score += 0.35
        else:
            score += 1.5
            long_matches += 1

    # One short Chinese overlap such as "培训" or "公司" is too weak.
    if score < 2.0 and long_matches == 0 and len(matched) < 2:
        return 0.0
    return score


class MemoryExtractor:
    """Lifecycle-triggered memory extraction from conversation.

    Called at key points in the agent loop to extract cross-session
    knowledge before information is lost (e.g. before context compression).
    Writes to CONTEXT.md.
    """

    def __init__(
        self,
        llm,
        memory_manager: MemoryManager,
        *,
        cooldown: int = 300,
        step_interval: int = 10,
    ):
        self._llm = llm
        self._mgr = memory_manager
        self._cooldown = cooldown
        self._step_interval = step_interval
        self._last_time: float = 0.0
        self._steps_since: int = 0

    async def maybe_extract(self, messages: list[Message], trigger: str) -> bool:
        """Check whether extraction should run, then run if needed.

        Args:
            messages: Current conversation messages.
            trigger: ``"pre_summarize"`` | ``"step_interval"`` | ``"loop_end"``

        Returns:
            True if extraction was actually performed.
        """
        now = monotonic()

        if trigger == "step_interval":
            self._steps_since += 1
            if self._steps_since < self._step_interval:
                return False
            if now - self._last_time < self._cooldown:
                return False
        elif trigger == "pre_summarize":
            if now - self._last_time < self._cooldown:
                return False
        # "loop_end" always runs — no cooldown check

        try:
            await self._extract(messages)
            self._last_time = monotonic()
            self._steps_since = 0
            return True
        except Exception:
            logger.exception("Memory extraction failed (trigger=%s)", trigger)
            return False

    async def _extract(self, messages: list[Message]) -> None:
        """Use LLM to analyze messages and update CONTEXT.md."""
        from .schema import Message as Msg

        transcript = MemoryManager._build_transcript(messages, max_chars_per_msg=1500)
        if not transcript:
            return

        transcript = transcript[-6000:]  # Keep last ~6k chars

        core_memory = self._mgr.read_core() or "(empty)"

        # Only send last ~100 lines of Context for dedup reference (not the whole file).
        # Code-level dedup in append_context() handles Core overlap regardless.
        context_raw = self._mgr.read_context()
        if context_raw:
            context_lines = context_raw.splitlines()
            context_memory = "\n".join(context_lines[-100:])
        else:
            context_memory = "(empty)"

        prompt = _EXTRACTION_USER_PROMPT.format(
            core_memory=core_memory,
            context_memory=context_memory,
            transcript=transcript,
        )

        response = await self._llm.generate(
            messages=[
                Msg(role="system", content=_EXTRACTION_SYSTEM_PROMPT),
                Msg(role="user", content=prompt),
            ]
        )

        self._apply_updates(response.content)

    def _apply_updates(self, llm_output: str) -> None:
        """Parse LLM JSON output and apply to CONTEXT.md.

        Routed through ``apply_context_operations`` so entry metadata
        (hits, created, last_used) survives merges.
        """
        text = _strip_json_fences(llm_output)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Memory extraction returned invalid JSON: %s", text[:200])
            return

        additions: list[str] = data.get("additions", [])
        merges: list[dict] = data.get("merges", [])

        if not additions and not merges:
            return

        operations: list[dict] = []
        for merge in merges:
            old = str(merge.get("old", "")).strip()
            new = str(merge.get("new", "")).strip()
            if old and new:
                operations.append({"action": "replace", "old": old, "new": new})

        if additions:
            joined = "\n".join(a for a in additions if isinstance(a, str) and a.strip())
            if joined:
                operations.append({"action": "add", "content": joined})

        if operations:
            self._mgr.apply_context_operations(operations)
