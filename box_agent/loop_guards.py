"""Loop guards & continuation nudges for the agent execution loop.

These are the *pure, stateless* building blocks behind the family of
opt-in circuit breakers that keep :func:`box_agent.core.run_agent_loop`
from flailing or stopping prematurely:

- tool-call budget messages (cap repeated web_search etc.),
- the completion gate (force continuation until verifiable evidence
  exists — borrowed in spirit from oh-my-codex's Stop gate, but
  evidence-based rather than prose-pattern-based),
- the near-limit and no-progress wrap-up nudges.

Everything here is side-effect-free (apart from read-only filesystem
stats for artifact checks) so it can be unit-tested in isolation. The
actual loop wiring — counters, one-shot flags, message injection — stays
in ``core`` where the loop state lives.

Where to put things when adding a new circuit breaker:

- Pure logic (decide *whether* to fire, build *what text* to inject,
  constants/thresholds) → here, as a function or dataclass that takes
  loop facts as plain arguments and returns a value. No ``yield``, no
  ``messages`` mutation, no reference to loop-local variables.
- Wiring (the counters/flags it reads, the ``messages.append`` +
  ``yield InjectedMessageEvent``, the ``continue``/``return``) → in
  ``core.run_agent_loop``, calling into the pure helper here.

This split keeps ``core`` focused on control flow and keeps every
breaker's decision logic independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

# ── Constants ────────────────────────────────────────────────────

WEB_SEARCH_TOOL_NAME: Final = "web_search"
WEB_SEARCH_BATCH_SIZE: Final = 6
WEB_SEARCH_TOTAL_LIMIT: Final = 24

# Per-turn call caps for tools the model tends to over-request.
TOOL_CALL_LIMITS: Final[dict[str, int]] = {
    WEB_SEARCH_TOOL_NAME: WEB_SEARCH_TOTAL_LIMIT,
}

# Reserve this many trailing steps for synthesis (near-limit wrap-up).
WRAPUP_REMAINING: Final[int] = 3

# Abort after this many consecutive all-empty-args tool_call turns.
EMPTY_ARGS_LIMIT: Final[int] = 2


# ── Tool-call budget messages ────────────────────────────────────


def tool_call_budget_message(tool_name: str, limit: int) -> str:
    """Synthetic tool-error text returned once a tool's per-turn budget is hit."""
    return (
        f"Tool call budget reached for {tool_name} ({limit} calls this turn). "
        f"Do not call {tool_name} again; synthesize the final answer from the "
        "evidence and tool results already collected. If anything is missing, "
        "briefly mark it as a gap instead of searching again."
    )


def tool_call_budget_wrapup_text(tool_name: str, limit: int) -> str:
    """One-shot wrap-up nudge injected when a tool's per-turn budget is hit."""
    return (
        f"⚠️ 本轮 {tool_name} 调用已达到预算上限（{limit} 次）。"
        f"现在请停止继续调用 {tool_name} 或继续联网搜索，"
        "仅基于已经获得的资料直接给出完整最终答案；缺口简要标注即可。"
    )


# ── Near-limit / no-progress wrap-up nudges ──────────────────────


def near_limit_wrapup_text(step: int, max_steps: int) -> str:
    """Reserve the final steps for synthesis: stop gathering, answer now.

    ``step`` is the 0-based loop index (as in ``run_agent_loop``).
    """
    remaining = max_steps - step
    return (
        f"⚠️ 步数预算即将用尽（已到第 {step + 1}/{max_steps} 步，约剩 {remaining} 步）。"
        "现在请停止调用任何工具、停止继续搜索或探索。"
        "仅基于你已经收集到的信息，在本轮直接给出完整、可独立阅读的最终答案/总结："
        "包含关键结论、数据、以及已产出的文件路径；若有未覆盖的缺口，简要标注即可，"
        "不要再去调查。"
    )


def no_progress_wrapup_text(no_progress_steps: int) -> str:
    """Force a synthesis after N consecutive steps with no useful tool result."""
    return (
        f"⚠️ 已连续 {no_progress_steps} 步没有取得有效进展"
        "（工具调用持续失败或无有用输出）。"
        "现在请立即停止调用任何工具、停止重试当前路径。"
        "仅基于你已经收集到的信息，在本轮直接给出完整、可独立阅读的"
        "最终答案/总结：包含关键结论、已知数据与已产出的文件路径；"
        "对未能获取的信息，简要标注为缺口即可，不要再继续调查。"
    )


# ── Mid-turn injection wrapper ───────────────────────────────────


def format_injected_message(text: str) -> str:
    """Wrap mid-stream user input so it steers the active task."""
    return (
        "The user sent the following message while the current task was already running.\n"
        "Treat it as mid-turn guidance, a constraint, or a clarification for the current task, "
        "not as a new standalone task.\n"
        "If it asks a question, answer it briefly if useful, then continue the original task. "
        "Do not stop or switch tasks unless the user explicitly asks you to stop, cancel, or change the task.\n\n"
        f"Mid-turn user message:\n{text}"
    )


# ── Completion gate ──────────────────────────────────────────────


@dataclass(frozen=True)
class CompletionGate:
    """Opt-in completion gate for the agent loop.

    Borrowed in spirit from oh-my-codex's Stop gate, but deliberately
    evidence-based rather than prose-pattern-based: the gate only ever
    inspects *verifiable facts* (which tools produced a usable result,
    which artifact files exist) — never the assistant's wording.

    When supplied to :func:`box_agent.core.run_agent_loop`, a natural
    END_TURN (the model emits no tool calls) is intercepted: if any
    requirement is unmet, a continuation nudge naming the gaps is injected
    and the loop keeps going. A bounded ``max_continuations`` count plus an
    optional ``deadline_seconds`` guarantee the gate can never trap the
    agent forever — on exhaustion it releases and the turn ends normally.

    Disabled by default (callers pass ``None``); behaviour is then
    byte-for-byte unchanged.
    """

    # Tools that must each have produced at least one successful, non-empty
    # result before END_TURN is allowed.
    required_tools: frozenset[str] = field(default_factory=frozenset)
    # Artifact files that must exist and be non-empty before END_TURN is
    # allowed. Resolved relative to ``workspace_dir`` (absolute paths kept).
    required_artifacts: tuple[str, ...] = ()
    # Safety valve: max number of continuation nudges the gate may inject.
    max_continuations: int = 3
    # Safety valve: release the gate once the run exceeds this many seconds.
    # ``None`` disables the time limit.
    deadline_seconds: float | None = None


def completion_gate_gaps(
    gate: CompletionGate,
    succeeded_tools: set[str],
    workspace_dir: str | None,
) -> list[str]:
    """Return human-readable descriptions of unmet gate requirements.

    Empty list means every requirement is satisfied. Pure function: no
    side effects beyond read-only filesystem stats for artifact checks.
    """
    gaps: list[str] = []
    for tool_name in sorted(gate.required_tools):
        if tool_name not in succeeded_tools:
            gaps.append(f"工具 `{tool_name}` 尚未成功调用并返回有效结果")
    base = Path(workspace_dir) if workspace_dir else None
    for artifact in gate.required_artifacts:
        path = Path(artifact)
        if not path.is_absolute() and base is not None:
            path = base / path
        try:
            exists_nonempty = path.is_file() and path.stat().st_size > 0
        except OSError:
            exists_nonempty = False
        if not exists_nonempty:
            gaps.append(f"产物文件 `{artifact}` 不存在或为空")
    return gaps


def completion_gate_text(gaps: list[str]) -> str:
    """Continuation nudge naming the unmet requirements (same tone as the
    near-limit / no-progress wrap-up nudges)."""
    bullet_lines = "\n".join(f"  - {gap}" for gap in gaps)
    return (
        "⚠️ 本轮任务尚未满足完成条件，请勿在此收尾。仍缺：\n"
        f"{bullet_lines}\n"
        "请补齐以上缺口（完成所需的工具调用、产出缺失的文件），完成后再给出最终答复。"
        "不要空转或仅口头声称已完成——以可验证的实际产出补齐为准。"
    )
