"""Core Agent implementation.

The heavy lifting now lives in ``box_agent.core.run_agent_loop``.
This module keeps the public ``Agent`` API backward-compatible while
delegating to the shared execution core.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Optional

from .core import run_agent_loop
from .events import (
    AgentEvent,
    ArtifactEvent,
    ContentEvent,
    DoneEvent,
    ErrorEvent,
    InjectedMessageEvent,
    LogFileEvent,
    MemoryProposalEvent,
    PPTProgressEvent,
    PermissionRequestEvent,
    StepEnd,
    StepStart,
    StopReason,
    SubAgentEvent,
    SummarizationEvent,
    ThinkingEvent,
    TokenUsageEvent,
    ToolCallResult,
    ToolCallStart,
)
from .llm import LLMClient
from .logger import AgentLogger
from .schema import Message
from .tools.base import Tool
from .utils import calculate_display_width


# ANSI color codes
class Colors:
    """Terminal color definitions"""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


def _format_size(n: int) -> str:
    """Render a byte count as a short human label (``12.4KB``)."""
    if n < 0:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024  # type: ignore[assignment]
    return f"{n}B"


class Agent:
    """Single agent with basic tools and MCP support."""

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str,
        tools: list[Tool],
        max_steps: int = 200,
        workspace_dir: str = "./workspace",
        token_limit: int = 113400,
        hooks: list | None = None,
        thinking_enabled: bool = False,
        memory_promotion_enabled: bool = False,
        memory_promotion_hit_threshold: int = 5,
        memory_promotion_cooldown_days: int = 14,
    ):
        self.llm = llm_client
        self.tools = {tool.name: tool for tool in tools}
        self.max_steps = max_steps
        self.token_limit = token_limit
        self.workspace_dir = Path(workspace_dir)
        self.cancel_event: Optional[asyncio.Event] = None
        self.inject_queue: asyncio.Queue[str] = asyncio.Queue()
        self._permission_negotiator = None  # set by CLI/ACP when permission engine is active
        self._proposal_negotiator = None  # set by CLI/ACP to handle MemoryProposalEvent
        self._hooks = hooks
        self._memory_extractor = None  # set by CLI/ACP when memory extraction is enabled
        self.thinking_enabled = thinking_enabled
        self.memory_promotion_enabled = memory_promotion_enabled
        self.memory_promotion_hit_threshold = memory_promotion_hit_threshold
        self.memory_promotion_cooldown_days = memory_promotion_cooldown_days

        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        if "Current Workspace" not in system_prompt:
            workspace_info = (
                f"\n\n## Current Workspace\n"
                f"You are currently working in: `{self.workspace_dir.absolute()}`\n"
                f"All relative paths will be resolved relative to this directory."
            )
            system_prompt = system_prompt + workspace_info

        self.system_prompt = system_prompt
        for tool in self.tools.values():
            if hasattr(tool, "set_parent_system_prompt"):
                tool.set_parent_system_prompt(system_prompt)
        self.messages: list[Message] = [Message(role="system", content=system_prompt)]
        self.logger = AgentLogger()
        self.api_total_tokens: int = 0
        self._streaming_active: bool = False  # Track if streaming output needs trailing newline

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.messages.append(Message(role="user", content=content))

    def inject(self, content: str) -> None:
        """Inject a user message into the running agent loop.

        The message is queued and will be appended to the conversation
        at the next step boundary.  Safe to call from any thread.
        """
        self.inject_queue.put_nowait(content)

    def _check_cancelled(self) -> bool:
        if self.cancel_event is not None and self.cancel_event.is_set():
            return True
        return False

    # ── Event-stream API (new) ──────────────────────────────

    async def run_events(
        self, cancel_event: Optional[asyncio.Event] = None
    ) -> AsyncIterator[AgentEvent]:
        """Execute the agent loop, yielding structured events.

        This is the preferred API for consumers that want fine-grained
        control over rendering (e.g. ACP, JSON-RPC, custom UIs).
        """
        if cancel_event is not None:
            self.cancel_event = cancel_event

        async for event in run_agent_loop(
            llm=self.llm,
            messages=self.messages,
            tools=self.tools,
            max_steps=self.max_steps,
            token_limit=self.token_limit,
            is_cancelled=self._check_cancelled,
            logger=self.logger,
            workspace_dir=str(self.workspace_dir),
            permission_negotiator=self._permission_negotiator,
            hooks=self._hooks,
            memory_manager=getattr(self._memory_extractor, "_mgr", None),
            memory_extractor=self._memory_extractor,
            memory_promotion_enabled=self.memory_promotion_enabled,
            memory_promotion_hit_threshold=self.memory_promotion_hit_threshold,
            memory_promotion_cooldown_days=self.memory_promotion_cooldown_days,
            inject_queue=self.inject_queue,
            thinking_enabled=self.thinking_enabled,
        ):
            # Track token usage on Agent instance for backward compat
            if isinstance(event, TokenUsageEvent):
                self.api_total_tokens = event.total_tokens
            yield event

    # ── Backward-compatible run() ───────────────────────────

    async def run(self, cancel_event: Optional[asyncio.Event] = None) -> str:
        """Execute agent loop with terminal rendering.

        Signature and return value are unchanged from before the refactor.
        Internally it now consumes ``run_events()``.
        """
        final_content = ""
        async for event in self.run_events(cancel_event):
            self._render_event(event)
            if isinstance(event, MemoryProposalEvent) and self._proposal_negotiator is not None:
                try:
                    await self._proposal_negotiator.negotiate(event)
                except Exception:
                    pass
            if isinstance(event, DoneEvent):
                final_content = event.final_content
        return final_content

    # ── Terminal renderer ───────────────────────────────────

    def _render_event(self, event: AgentEvent) -> None:  # noqa: C901 — intentionally flat
        """Translate an ``AgentEvent`` into terminal output."""

        # End streaming line before non-streaming events
        is_streaming = (
            isinstance(event, (ThinkingEvent, ContentEvent))
            and getattr(event, "_streaming", False)
        )
        if not is_streaming and self._streaming_active:
            print()  # newline to end the streaming line
            self._streaming_active = False

        match event:
            case LogFileEvent(path=p):
                print(f"{Colors.DIM}📝 Log file: {p}{Colors.RESET}")

            case SummarizationEvent(estimated_tokens=est, api_tokens=api, token_limit=limit):
                print(
                    f"\n{Colors.BRIGHT_YELLOW}📊 Token usage - Local estimate: {est}, "
                    f"API reported: {api}, Limit: {limit}{Colors.RESET}"
                )
                print(f"{Colors.BRIGHT_YELLOW}🔄 Triggering message history summarization...{Colors.RESET}")

            case StepStart(step=s, max_steps=mx):
                BOX_WIDTH = 58
                step_text = f"{Colors.BOLD}{Colors.BRIGHT_CYAN}💭 Step {s}/{mx}{Colors.RESET}"
                step_display_width = calculate_display_width(step_text)
                padding = max(0, BOX_WIDTH - 1 - step_display_width)
                print(f"\n{Colors.DIM}╭{'─' * BOX_WIDTH}╮{Colors.RESET}")
                print(f"{Colors.DIM}│{Colors.RESET} {step_text}{' ' * padding}{Colors.DIM}│{Colors.RESET}")
                print(f"{Colors.DIM}╰{'─' * BOX_WIDTH}╯{Colors.RESET}")

            case ThinkingEvent() if event._streaming:
                if event._header:
                    print(f"\n{Colors.BOLD}{Colors.MAGENTA}🧠 Thinking:{Colors.RESET}")
                else:
                    print(f"{Colors.DIM}{event.content}{Colors.RESET}", end="", flush=True)
                    self._streaming_active = True

            case ThinkingEvent(content=text):
                print(f"\n{Colors.BOLD}{Colors.MAGENTA}🧠 Thinking:{Colors.RESET}")
                print(f"{Colors.DIM}{text}{Colors.RESET}")

            case ContentEvent() if event._streaming:
                if event._header:
                    print(f"\n{Colors.BOLD}{Colors.BRIGHT_BLUE}🤖 Assistant:{Colors.RESET}")
                else:
                    print(f"{event.content}", end="", flush=True)
                    self._streaming_active = True

            case ContentEvent(content=text):
                print(f"\n{Colors.BOLD}{Colors.BRIGHT_BLUE}🤖 Assistant:{Colors.RESET}")
                print(f"{text}")

            case ToolCallStart(tool_name=name, arguments=args):
                print(f"\n{Colors.BRIGHT_YELLOW}🔧 Tool Call:{Colors.RESET} {Colors.BOLD}{Colors.CYAN}{name}{Colors.RESET}")
                print(f"{Colors.DIM}   Arguments:{Colors.RESET}")
                truncated = {}
                for k, v in args.items():
                    vs = str(v)
                    truncated[k] = vs[:200] + "..." if len(vs) > 200 else v
                for line in json.dumps(truncated, indent=2, ensure_ascii=False).split("\n"):
                    print(f"   {Colors.DIM}{line}{Colors.RESET}")

            case ToolCallResult(success=ok, content=text, error=err, raw_output=raw_output):
                if ok:
                    display = text[:300] + f"{Colors.DIM}...{Colors.RESET}" if len(text) > 300 else text
                    print(f"{Colors.BRIGHT_GREEN}✓ Result:{Colors.RESET} {display}")
                    if raw_output and raw_output.get("type") == "memory_search":
                        self._render_memory_search(raw_output)
                else:
                    print(f"{Colors.BRIGHT_RED}✗ Error:{Colors.RESET} {Colors.RED}{err}{Colors.RESET}")

            case ArtifactEvent(kind=kind, filename=fname, rel_path=rel, size=sz):
                size_label = _format_size(sz)
                print(f"{Colors.BRIGHT_CYAN}📎 {kind}{Colors.RESET} {fname} · {size_label} · {Colors.DIM}{rel}{Colors.RESET}")

            case SubAgentEvent(task_preview=preview, event=inner, sub_agent_id=_):
                label = preview[:40] + "..." if len(preview) > 40 else preview
                prefix = f"{Colors.DIM}  ┊ [{label}]{Colors.RESET}"
                match inner:
                    case StepStart(step=s, max_steps=mx):
                        print(f"{prefix}{Colors.DIM} Step {s}/{mx}{Colors.RESET}")
                    case ToolCallStart(tool_name=name):
                        print(f"{prefix}{Colors.DIM} 🔧 {name}{Colors.RESET}")
                    case ToolCallResult(tool_name=name, success=ok):
                        mark = "✓" if ok else "✗"
                        print(f"{prefix}{Colors.DIM} {mark} {name}{Colors.RESET}")
                    case ArtifactEvent(filename=fname):
                        print(f"{prefix}{Colors.DIM} 📎 {fname}{Colors.RESET}")
                    case ErrorEvent(message=msg):
                        print(f"{prefix}{Colors.DIM} ❌ {msg}{Colors.RESET}")

            case ErrorEvent(message=msg):
                print(f"\n{Colors.BRIGHT_RED}❌ Error:{Colors.RESET} {msg}")

            case PPTProgressEvent(payload=p):
                ptype = p.get("type", "unknown")
                print(f"{Colors.DIM}  📊 PPT: {ptype}{Colors.RESET}")

            case PermissionRequestEvent(scope=scope, requested_scope=req_scope, path=path, reason=reason):
                print(f"\n{Colors.BRIGHT_YELLOW}🔒 Permission required: {scope} → {req_scope}{Colors.RESET}")
                if path:
                    print(f"   Path: {path}")
                print(f"   Reason: {reason}")

            case InjectedMessageEvent(content=text):
                preview = text[:80] + "..." if len(text) > 80 else text
                print(f"\n{Colors.DIM}💉 Injected:{Colors.RESET} {Colors.BRIGHT_WHITE}{preview}{Colors.RESET}")

            case StepEnd(step=s, elapsed_seconds=el, total_elapsed_seconds=tot):
                print(f"\n{Colors.DIM}⏱️  Step {s} completed in {el:.2f}s (total: {tot:.2f}s){Colors.RESET}")

            case DoneEvent(stop_reason=reason, final_content=_):
                if reason == StopReason.CANCELLED:
                    print(f"\n{Colors.BRIGHT_YELLOW}⚠️  Task cancelled by user.{Colors.RESET}")
                elif reason == StopReason.MAX_STEPS:
                    print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {event.final_content}{Colors.RESET}")

            case _:
                pass  # TokenUsageEvent etc. — no terminal output needed

    def _render_memory_search(self, raw_output: dict) -> None:
        """Render structured memory_search matches in the terminal."""
        matches = raw_output.get("matched_memories")
        if not isinstance(matches, list):
            return

        query = raw_output.get("query", "")
        if matches:
            print(f"{Colors.BRIGHT_CYAN}🧠 Matched memories:{Colors.RESET} {query}")
            for item in matches:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text", "")).strip()
                if text:
                    print(f"  {Colors.DIM}{text}{Colors.RESET}")
        else:
            print(f"{Colors.DIM}🧠 Matched memories: none for {query}{Colors.RESET}")

    def get_history(self) -> list[Message]:
        """Get message history."""
        return self.messages.copy()
