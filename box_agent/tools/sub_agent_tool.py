"""Sub-agent tool for isolated context execution.

Spawns a child agent loop with its own message history so that
intermediate tool output (file reads, exploratory analysis, etc.)
stays out of the parent context.  Only the final summary is returned.

Multiple sub-agent calls are ``parallel_safe`` and will be executed
concurrently via ``asyncio.gather`` in the core loop.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from ..events import (
    ArtifactEvent,
    DoneEvent,
    ErrorEvent,
    StepStart,
    SubAgentEvent,
    ToolCallResult,
    ToolCallStart,
    WebSearchEvent,
)
from ..schema import Message
from .base import EventEmittingTool, Tool, ToolResult

_SUB_AGENT_SYSTEM_PROMPT = """\
You are a focused sub-agent executing a specific task delegated by the main agent.

Rules:
1. You inherit the parent agent's system instructions and must follow them unless the \
delegated task gives a narrower, non-conflicting scope.
2. Complete only the assigned isolated work unit. Respect any path, file, prefix, \
or output constraints in the delegated task.
3. Do not overwrite shared files or final deliverables unless the delegated task \
explicitly assigns that exact output to you.
4. If a Jupyter kernel session already exists, variables from previous executions \
are still in scope — reuse them directly.
5. When you are done, output a concise but complete summary of your findings or \
results.  Include key numbers, conclusions, and any file paths produced.
6. Do NOT ask follow-up questions — complete the task with what you have.
"""


class SubAgentTool(EventEmittingTool):
    """Run a task in an isolated agent context.

    The child agent shares the same LLM client and tool instances (so
    Jupyter kernel sessions, sandbox state, etc. are preserved), but has
    its own message history.  Only the final textual summary is returned
    to the parent agent, keeping the parent context clean.
    """

    parallel_safe = True

    def __init__(
        self,
        *,
        llm,
        parent_tools: dict[str, Tool],
        workspace_dir: str | None = None,
        max_steps: int = 20,
        token_limit: int = 40_000,
        parent_system_prompt: str | None = None,
    ):
        super().__init__()
        self._llm = llm
        # Exclude ourselves to prevent recursive sub-agent spawning.
        self._child_tools = {n: t for n, t in parent_tools.items() if n != self.name}
        self._workspace_dir = workspace_dir
        self._max_steps = max_steps
        self._token_limit = token_limit
        self._parent_system_prompt = parent_system_prompt

    def set_parent_system_prompt(self, system_prompt: str) -> None:
        """Attach the finalized parent prompt so child agents inherit constraints."""
        self._parent_system_prompt = system_prompt

    @property
    def name(self) -> str:
        return "sub_agent"

    @property
    def description(self) -> str:
        return (
            "Delegate one isolated, self-contained work unit to a sub-agent. "
            "Use sub_agent when the work can run independently and the parent only needs a concise "
            "summary, findings, or paths to draft artifacts. Good examples include reading many files "
            "to answer one question, deep codebase search, exploratory data analysis, reviewing one "
            "slice of outputs, processing one input file, or drafting one independent page/section/file.\n\n"
            "Mandatory trigger: when a task needs generating or reviewing more than 5 structurally "
            "similar units that can be isolated, launch 3-5 sub_agent calls first unless the user "
            "explicitly says not to parallelize or the units cannot be safely isolated. Each call "
            "must be scoped to a single small unit such as 1 page, 1 file, 1 data slice, or 1 QA dimension. Each sub-agent "
            "may create draft files or artifacts only in an explicitly assigned unique path, directory, "
            "or filename prefix. If the final deliverable is a single file, still split independent "
            "units into draft fragments or local partial files and let the parent merge them into the "
            "single final file. Do not assign two sub-agents to write the same file or shared output.\n\n"
            "The parent agent must own coordination: choose the split, merge results, resolve conflicts, "
            "write final deliverables, package/release outputs, update shared files, and run final "
            "validation. The sub-agent must report changed/created paths, findings, assumptions, and "
            "remaining risks."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "A clear, self-contained description of the task for the "
                        "sub-agent to execute. Include all necessary context — the "
                        "sub-agent cannot see prior conversation history."
                    ),
                },
            },
            "required": ["task"],
        }

    # Event types worth surfacing to the parent.
    _FORWARD_TYPES = (StepStart, ToolCallStart, ToolCallResult, WebSearchEvent, ArtifactEvent, ErrorEvent)

    async def execute(self, task: str) -> ToolResult:  # type: ignore[override]
        # Import here to avoid circular dependency (core → tools → core).
        from ..core import run_agent_loop

        system_prompt = _SUB_AGENT_SYSTEM_PROMPT
        if self._parent_system_prompt:
            system_prompt = (
                f"{system_prompt.rstrip()}\n\n"
                "## Inherited parent system prompt\n"
                "The following instructions are inherited from the parent agent. "
                "They define global behavior, safety, workspace, skill, output, and "
                "task-specific constraints that also apply inside this sub-agent.\n\n"
                f"{self._parent_system_prompt}"
            )

        messages: list[Message] = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=task),
        ]

        queue = self._event_queue
        # Single-line preview: collapse whitespace, truncate
        task_preview = " ".join(task.split())[:50]
        sub_agent_id = f"subagent-{uuid4().hex}"

        final_content = ""
        try:
            async for event in run_agent_loop(
                llm=self._llm,
                messages=messages,
                tools=self._child_tools,
                max_steps=self._max_steps,
                token_limit=self._token_limit,
                workspace_dir=self._workspace_dir,
            ):
                if isinstance(event, DoneEvent):
                    final_content = event.final_content
                elif queue is not None and isinstance(event, self._FORWARD_TYPES):
                    queue.put_nowait(
                        SubAgentEvent(
                            parent_tool_call_id=self._parent_tool_call_id,
                            task_preview=task_preview,
                            event=event,
                            sub_agent_id=sub_agent_id,
                        )
                    )
        except Exception as exc:
            return ToolResult(
                success=False,
                content="",
                error=f"Sub-agent execution failed: {type(exc).__name__}: {exc}",
            )

        if not final_content:
            return ToolResult(
                success=False,
                content="",
                error="Sub-agent finished without producing output.",
            )

        return ToolResult(success=True, content=final_content)
