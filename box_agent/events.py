"""Structured event types emitted by the agent execution core.

All agent loop consumers (CLI, ACP, JSON-RPC) receive these events
instead of performing their own LLM call / tool execution logic.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union


class StopReason(str, Enum):
    """Why the agent loop terminated."""

    END_TURN = "end_turn"
    MAX_STEPS = "max_steps"
    MAX_TOKENS = "max_tokens"
    CANCELLED = "cancelled"
    ERROR = "error"


# ── Step lifecycle ──────────────────────────────────────────────


@dataclass(frozen=True)
class StepStart:
    """Beginning of an agent step (one LLM call + tool execution cycle)."""

    step: int
    max_steps: int


@dataclass(frozen=True)
class StepEnd:
    """Step completed."""

    step: int
    elapsed_seconds: float
    total_elapsed_seconds: float


# ── LLM output ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ThinkingEvent:
    """Extended thinking content from the LLM."""

    content: str
    _streaming: bool = False
    _header: bool = False


@dataclass(frozen=True)
class ContentEvent:
    """Text response content from the LLM."""

    content: str
    _streaming: bool = False
    _header: bool = False


@dataclass(frozen=True)
class TokenUsageEvent:
    """Token usage reported by the API after an LLM call."""

    total_tokens: int


@dataclass(frozen=True)
class LLMOutputEvent:
    """Complete model output for one LLM call, intended for host logging."""

    step: int
    content: str
    thinking: str | None = None
    tool_calls: list[Any] | None = None
    finish_reason: str = "stop"
    usage: dict[str, Any] | None = None
    provider_request_id: str | None = None


# ── Tool execution ──────────────────────────────────────────────


@dataclass(frozen=True)
class ToolCallStart:
    """LLM requested a tool call."""

    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolCallResult:
    """Tool execution completed."""

    tool_call_id: str
    tool_name: str
    success: bool
    content: str
    error: str | None = None
    raw_output: dict[str, Any] | None = None


@dataclass(frozen=True)
class WebSearchEvent:
    """Structured references returned by the web_search tool."""

    tool_call_id: str
    payload: dict[str, Any]


# ── Safety ──────────────────────────────────────────────────────


@dataclass
class ConfirmationRequired:
    """Safety layer requests user confirmation before proceeding.

    The consumer MUST call ``respond.set_result(True/False)`` so the
    core can continue.  If nobody responds within the timeout the core
    treats it as a rejection.

    TODO: Not yet yielded by ``core.run_agent_loop``.  Currently,
    safety confirmation still happens inside tool implementations via
    ``safety.ask_user_confirmation()`` (blocking ``input()``).  A future
    phase should intercept safety checks in the core and yield this
    event instead, so ACP and other non-terminal consumers can handle
    confirmation through their own protocol.
    """

    tool_call_id: str
    tool_name: str
    message: str
    respond: asyncio.Future = field(repr=False)


# ── Artifacts (structured file/image output) ────────────────────


@dataclass(frozen=True)
class ArtifactEvent:
    """A file produced by tool execution and landed under ``{workspace}/output/``.

    All artifact-producing pathways (sandbox plots, write_file, sub-agent
    drafts, PPT exports) emit this same structure so hosts have a single,
    stable display contract.

    Attributes:
        tool_call_id: The tool call that produced this artifact.
        kind: Coarse category derived from MIME — ``"image"``, ``"document"``,
            ``"spreadsheet"``, ``"presentation"``, ``"data"``, ``"code"``,
            ``"archive"``, or ``"file"`` (catch-all).
        filename: Bare filename (e.g. ``"chart.png"``).
        rel_path: Path relative to the workspace, forward-slash separated
            (e.g. ``"output/chart.png"``). Hosts should prefer this over abs_path.
        abs_path: Absolute filesystem path. Empty when the consumer cannot
            access the local filesystem.
        uri: ``file://`` URI for the artifact.
        mime: MIME type (e.g. ``"image/png"``); falls back to
            ``"application/octet-stream"`` when unknown.
        size: File size in bytes, or ``-1`` if unavailable.
        sha256: First 16 hex chars of the SHA-256 digest, used as a stable
            cache/dedup key. Empty if the file could not be hashed.
        produced_at: ISO 8601 timestamp of detection (with tz offset).
    """

    tool_call_id: str
    kind: str
    filename: str
    rel_path: str
    abs_path: str
    uri: str
    mime: str = "application/octet-stream"
    size: int = -1
    sha256: str = ""
    produced_at: str = ""


# ── Summarization ───────────────────────────────────────────────


@dataclass(frozen=True)
class SummarizationEvent:
    """Message history is being summarized to stay within token limits."""

    estimated_tokens: int
    api_tokens: int
    token_limit: int


# ── Errors & completion ─────────────────────────────────────────


@dataclass(frozen=True)
class ErrorEvent:
    """An error occurred during the agent loop."""

    message: str
    is_fatal: bool = False
    exception: Exception | None = field(default=None, repr=False)


@dataclass(frozen=True)
class LogFileEvent:
    """Log file path for this run."""

    path: str


@dataclass(frozen=True)
class DoneEvent:
    """Agent loop finished."""

    stop_reason: StopReason
    final_content: str


# ── Memory ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class MemoryEvent:
    """Memory operation event."""

    action: str  # "recall" | "update_manual" | "auto_extract"
    session_id: str = ""
    detail: str = ""


# ── Sub-agent progress ─────────────────────────────────────────


@dataclass(frozen=True)
class SubAgentEvent:
    """Progress event from a running sub-agent.

    Wraps a nested ``AgentEvent`` with metadata identifying which
    sub-agent produced it, so consumers can render indented progress.
    """

    parent_tool_call_id: str
    task_preview: str  # first ~80 chars of the task
    event: AgentEvent  # the nested event
    sub_agent_id: str = ""  # stable child-run id for host-side grouping


# ── PPT structured progress ───────────────────────────────────


@dataclass(frozen=True)
class PPTProgressEvent:
    """Structured progress event from a PPT tool.

    ``payload["type"]`` is the discriminator for officev3 dispatch
    (e.g. ``ppt_plan_json``, ``ppt_outline_delta``,
    ``ppt_editor_standard_html_result``).
    """

    parent_tool_call_id: str
    payload: dict  # {"type": "ppt_plan_json", ...} etc.


# ── Permission requests ──────────────────────────────────────


@dataclass(frozen=True)
class PermissionRequestEvent:
    """Capability permission request from a tool.

    Payload mirrors the canonical ``permission_request`` protocol
    defined in box-agent-permissions.md:

        {
            "type": "permission_request",
            "scope": "filesystem",
            "requested_scope": "user_home",
            "path": "/Users/.../file",   # filesystem only; empty for memory
            "reason": "...",
            "temporary_supported": true,
            "persistent_supported": true,
            "persistent_label": "始终允许此目录"  # filesystem only, optional UI hint
        }
    """

    tool_call_id: str
    scope: str            # capability namespace: "filesystem" | "memory"
    requested_scope: str  # e.g. "user_home" | "openclaw_import"
    reason: str
    path: str = ""        # absolute path; empty for non-filesystem capabilities
    temporary_supported: bool = True
    persistent_supported: bool = True
    persistent_label: str = ""  # optional UI label for the "always allow" option


# ── In-stream injection ────────────────────────────────────────


@dataclass(frozen=True)
class InjectedMessageEvent:
    """A user message was injected into the running agent loop."""

    content: str


# ── Union type ──────────────────────────────────────────────────

AgentEvent = Union[
    StepStart,
    StepEnd,
    ThinkingEvent,
    ContentEvent,
    TokenUsageEvent,
    LLMOutputEvent,
    ToolCallStart,
    ToolCallResult,
    WebSearchEvent,
    ArtifactEvent,
    ConfirmationRequired,
    SummarizationEvent,
    MemoryEvent,
    ErrorEvent,
    LogFileEvent,
    DoneEvent,
    SubAgentEvent,
    PPTProgressEvent,
    PermissionRequestEvent,
    InjectedMessageEvent,
]
