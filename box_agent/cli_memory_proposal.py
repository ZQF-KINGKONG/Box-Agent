"""CLI handler for MemoryProposalEvent.

Renders proposed CONTEXT.md → MEMORY.md (core) promotions in the
terminal and prompts the user per-candidate to pin / skip / reject.
Pinning promotes the entry to MEMORY.md permanently; rejecting marks
it ``core_status="rejected"`` so it is never proposed again; skipping
relies on the cooldown bumped at emit time.

Mirrors the termios pattern from ``cli_permissions.py`` to avoid
prompt_toolkit interference.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from .events import MemoryProposalEvent


class Colors:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    YELLOW = "\033[33m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    CYAN = "\033[36m"


_VALID_CHOICES = {"p", "pin", "1", "s", "skip", "2", "", "r", "reject", "3"}
_PIN_KEYS = {"p", "pin", "1"}
_REJECT_KEYS = {"r", "reject", "3"}
# anything else (including empty / skip / 2) is a skip


def _read_with_echo(prompt_text: str) -> str:
    try:
        import termios

        fd = sys.stdin.fileno()
        old_attrs = termios.tcgetattr(fd)
        try:
            new_attrs = termios.tcgetattr(fd)
            new_attrs[3] |= termios.ECHO | termios.ICANON
            termios.tcsetattr(fd, termios.TCSADRAIN, new_attrs)
            return input(prompt_text).strip().lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
    except (ImportError, OSError):
        return input(prompt_text).strip().lower()


async def _prompt(prompt_text: str) -> str:
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _read_with_echo, prompt_text)
    except (EOFError, KeyboardInterrupt):
        return ""


class CLIMemoryProposalNegotiator:
    """Run the per-candidate pin/skip/reject prompt and persist decisions."""

    def __init__(self, memory_manager: Any) -> None:
        self._mgr = memory_manager

    async def negotiate(self, event: MemoryProposalEvent) -> None:
        candidates = event.candidates
        if not candidates:
            return

        print()
        print(f"{Colors.BOLD}🧠 记忆升级提议 ({len(candidates)} 条){Colors.RESET}")
        print(f"{Colors.DIM}以下条目命中频次较高，是否要加入永久记忆 (MEMORY.md)?{Colors.RESET}")
        print(f"{Colors.DIM}  [1/p] pin — 加入核心 (永久)   [2/s/回车] skip — 暂不   [3/r] reject — 永不再提议{Colors.RESET}")
        print()

        decisions: dict[str, str] = {}
        for i, cand in enumerate(candidates, 1):
            preview = cand.content.strip().splitlines()[0]
            if len(preview) > 120:
                preview = preview[:117] + "…"
            print(f"{Colors.CYAN}[{i}/{len(candidates)}]{Colors.RESET} {preview}")
            print(f"  {Colors.DIM}hits={cand.hits}  confidence={cand.confidence:.2f}{Colors.RESET}")
            choice = await _prompt("  选择 [1/2/3]: ")
            if choice in _PIN_KEYS:
                decisions[cand.entry_id] = "pin"
                print(f"  {Colors.GREEN}✓ 已加入核心记忆{Colors.RESET}")
            elif choice in _REJECT_KEYS:
                decisions[cand.entry_id] = "reject"
                print(f"  {Colors.RED}✗ 已拒绝（永不再提议）{Colors.RESET}")
            else:
                decisions[cand.entry_id] = "skip"
                print(f"  {Colors.YELLOW}↷ 暂不{Colors.RESET}")
            print()

        try:
            counts = self._mgr.consume_core_proposal(decisions)
        except Exception as exc:
            print(f"{Colors.RED}记忆升级写入失败: {exc}{Colors.RESET}")
            return

        summary = (
            f"{Colors.DIM}小结: pinned={counts.get('pinned', 0)} "
            f"rejected={counts.get('rejected', 0)} skipped={counts.get('skipped', 0)}{Colors.RESET}"
        )
        print(summary)
