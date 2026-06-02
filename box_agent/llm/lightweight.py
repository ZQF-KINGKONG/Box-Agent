"""Lightweight LLM completion service.

Single-shot prompts (titles, summaries, rewrites) that must
NOT spin up an Agent session, load tools/skills/MCP, touch memory, or write
to conversation history. Wraps :func:`LLMClient.generate` with a hard
timeout, no tools, no extended thinking, and a structured result.

The ACP ``llm/prompt`` extension method is a thin shell around this
service — see :meth:`box_agent.acp.BoxACPAgent.extMethod`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING

from ..schema import Message

if TYPE_CHECKING:  # pragma: no cover - type-only import
    from .llm_wrapper import LLMClient


@dataclass(frozen=True)
class LightweightResult:
    """Outcome of a single lightweight prompt call."""

    text: str
    input_tokens: int
    output_tokens: int
    finish_reason: str
    duration_ms: int


class LightweightPromptError(Exception):
    """Base error for lightweight prompt failures.

    Carries a stable ``code`` so the ACP layer can return it as structured
    JSON-RPC error data without leaking internals.
    """

    code: str = "lightweight_failed"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code


class LightweightTimeout(LightweightPromptError):
    code = "timeout"


class LightweightInvalidArgs(LightweightPromptError):
    code = "invalid_args"


async def run_lightweight_prompt(
    llm: "LLMClient",
    prompt: str,
    *,
    system_prompt: str | None = None,
    session_id: str = "",
    timeout: float = 30.0,
) -> LightweightResult:
    """Run a single tool-free LLM completion.

    Args:
        llm: Shared :class:`LLMClient` from the ACP server. Reused so
            provider/model/auth stay consistent with the main agent.
        prompt: The user prompt. Must be non-empty after stripping.
        system_prompt: Optional system message. Empty/whitespace strings are
            treated as absent.
        session_id: Optional caller-owned session id for upstream trace grouping.
        timeout: Hard wall-clock cap in seconds. Raised as
            :class:`LightweightTimeout` on expiry.

    Returns:
        :class:`LightweightResult` with the model text, token usage, finish
        reason and elapsed milliseconds.

    Raises:
        LightweightInvalidArgs: ``prompt`` is empty or ``timeout`` is non-positive.
        LightweightTimeout: The LLM call exceeded ``timeout`` seconds.
        LightweightPromptError: Any other LLM-side failure.
    """
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt:
        raise LightweightInvalidArgs("prompt must be a non-empty string")
    if timeout <= 0:
        raise LightweightInvalidArgs("timeout must be positive")

    messages: list[Message] = []
    if system_prompt and system_prompt.strip():
        messages.append(Message(role="system", content=system_prompt))
    messages.append(Message(role="user", content=cleaned_prompt))

    started = perf_counter()
    try:
        response = await asyncio.wait_for(
            llm.generate(
                messages=messages,
                tools=None,
                thinking_enabled=False,
                session_id=session_id,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError as exc:
        raise LightweightTimeout(
            f"lightweight prompt timed out after {timeout:.1f}s"
        ) from exc
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface as structured error
        raise LightweightPromptError(str(exc) or repr(exc)) from exc

    duration_ms = int((perf_counter() - started) * 1000)
    text = getattr(response, "content", "") or ""
    finish_reason = getattr(response, "finish_reason", "") or ""
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

    return LightweightResult(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        finish_reason=finish_reason,
        duration_ms=duration_ms,
    )
