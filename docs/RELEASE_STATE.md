# Release State

## v0.8.66 (2026-06-08)

- **Commit:** `0441b2e81be46f2bb2a668cc78d849e1d3937410` (main)
- **PyPI:** https://pypi.org/project/box-agent/0.8.66/
- **GitHub release:** https://github.com/Raccoon-Office/Box-Agent/releases/tag/v0.8.66
- **Compare:** https://github.com/Raccoon-Office/Box-Agent/compare/v0.8.65...v0.8.66

### Artifacts (SHA256)

| File | SHA256 |
|------|--------|
| `box_agent-0.8.66-py3-none-any.whl` | `571bfd72a822285dd8d485a3f3ec8ddb27b29c9ba0d3638993cd55157425d9ed` |
| `box_agent-0.8.66.tar.gz` | `fddfa0da35b526d41411ef61cfbf04de0677bb48888fe1b8b60e03a589fbeebd` |
| `box-agent-runtime-v0.8.66-darwin-arm64.tar.gz` | `97f9e2c8d8a2d017f61d820bf99b82617ddaa408e09e3b288ac74b9d288eb5fc` |

### What shipped

LLM error humanization:
- New `box_agent/llm/error_messages.py` — `classify_llm_error` / `humanize_llm_error` map opaque provider exceptions (content_filter, auth, permission, rate_limit, quota, context_length, model_not_found, server_error, timeout, connection) to short Chinese messages. Bulletproof by contract: runs inside the error path, never raises, unwraps `RetryExhaustedError`/`StreamInterrupted` to inspect the underlying provider error, SDK-agnostic attribute + substring detection.
- `core.py`: soft errors (content moderation) end the turn as a **normal assistant reply** (no `Error:` banner, no red), persisted to history; all other errors surfaced humanized.
- `lightweight.py`: new `LightweightContentFiltered` (`code=content_filter`) lets `_llm/prompt` callers (title/summary) fall back to a neutral default; provider raw JSON never leaks.
- `acp`: content_filter logged at info, returned as a stable error code.

pptx skill — content & outline gate:
- The outline gate (`references/outline.md` + `scripts/validate_outline.js`) was **orphaned** — SKILL.md's new-deck route jumped straight to image planning/HTML, so the gate never fired. Now wired in as route step 1 (§1.1), listed in §2 commands and §7 references.
- **Warm reject, not cold:** under-specified → ask 1-3 focused questions with a sensible default; under-sourced → route to `research-synthesis`, then build the slide plan from sourced findings; never fabricate. Hard `BLOCKED` stays reserved for `creative_image_mode` images; carve-out so creative short topics aren't pushed into research.
- Canvas-contract docs (html-first / html-editable): copy `references/starter/common.css` verbatim for the locked 1920×1080 `.slide`; `--canvas WxH` opt-in for nonstandard sizes.

### Follow-ups / known gaps

- **Runtime artifact:** only `darwin-arm64` built/uploaded. `darwin-x64` / Windows runtimes not built this release; the officev3 desktop app picks up these fixes only after the bundled runtime is rebuilt per platform.
- **Test hygiene:** full `pytest` still shows the same ~13 env-dependent permission/symlink-scoping failures documented since v0.8.64 — confirmed pre-existing (they fail identically on clean `v0.8.65` HEAD), unrelated to this release.
- **Upstream dependency:** the warm gate routes to `research-synthesis` for the deck's *content*; the officev3 expert layer still needs its "普通 PPT 设计师" role to add the research pre-step so the two layers interlock end-to-end.

## v0.8.65 (2026-06-07)

- **Commit:** `80908f81fd2e872e8db336a2aa79b65df597a909` (main)
- **PyPI:** https://pypi.org/project/box-agent/0.8.65/
- **GitHub release:** https://github.com/Raccoon-Office/Box-Agent/releases/tag/v0.8.65
- **Compare:** https://github.com/Raccoon-Office/Box-Agent/compare/v0.8.64...v0.8.65

### Artifacts (SHA256)

| File | SHA256 |
|------|--------|
| `box_agent-0.8.65-py3-none-any.whl` | `f6867fd22817c4fba3ae8b305baa361a0eb61e273f75879d3864c4582989cf0b` |
| `box_agent-0.8.65.tar.gz` | `f670ec1fa9efbe7ed3db4d7d3c0540675837a2c89c9ed4561aa435f0e3fc7963` |

### What shipped

ACP startup reliability:
- **Fix:** the one-time OpenClaw memory import ran a blocking `await llm.generate()` *before* the ACP stdio transport was established, so a slow/stalled first-launch LLM call tripped the host's 15 s `initialize` timeout and the process was killed before becoming ready. The import marker is written only after the call, so every restart re-hit the same stall — symptom: perpetual `box-agent ACP 初始化超时（15s）`.
- Moved OpenClaw import off the critical path, merged with the already-backgrounded memory maintainer into one fire-and-forget `memory-bootstrap` task (import → maintain kept sequential to avoid racing on `MEMORY.md`). Startup now reaches stdio readiness with only local work on the critical path.

### Follow-ups / known gaps

- **Runtime artifacts not built this release.** PyPI wheel/sdist only. The fix reaches the officev3 desktop app **only** after the bundled `box-agent-runtime` is rebuilt and repackaged — in particular the **Windows** runtime (`scripts/build_win_runtime.py`), which cannot be built from macOS. The failing office-raccoon install will not pick up this fix until that runtime ships.
- Host-side mitigations from the incident (raising the 15 s ACP timeout; pinning `BOX_AGENT_ACP_COMMAND`) are now unnecessary for this root cause and can be reverted.

## v0.8.64 (2026-06-05)

- **Commit:** `f5882f315b09668d8385cc674431300d272a436f` (main)
- **PyPI:** https://pypi.org/project/box-agent/0.8.64/
- **GitHub release:** https://github.com/Raccoon-Office/Box-Agent/releases/tag/v0.8.64
- **Compare:** https://github.com/Raccoon-Office/Box-Agent/compare/v0.8.63...v0.8.64

### Artifacts (SHA256)

| File | SHA256 |
|------|--------|
| `box_agent-0.8.64-py3-none-any.whl` | `5df9ce1523fea9779b1889e09d9547bca8b91487bbdfc8ebf9c08e2d9b4bc38c` |
| `box_agent-0.8.64.tar.gz` | `d4db2124fada877c928e46266d59a50c72d35d533e78c95c8fc14829cb3be266` |
| `box-agent-runtime-v0.8.64-darwin-arm64.tar.gz` | `bc98ce8e08d08acf9e43f93a9c73e96e05b5bd66b2160dedbe24f16376d94a52` |

### What shipped

Sub-agent reliability & safety:
- Sub-agents inherit the parent's **live** tool map (late-loaded MCP `web_search` included), not a construction-time snapshot.
- Sub-agent `max_steps` 60 → 40; new no-progress circuit breaker (`run_agent_loop(no_progress_limit=...)`, default 6 for sub-agents, off for top-level agent).
- Hard concurrency cap `AgentConfig.max_parallel_tools` (default 8) on `parallel_safe` tool calls; parallel guidance 3-5 → 3-7.

UX / orchestration:
- `sub_agent` short `title` surfaced in ACP labels + progress (`SubAgentEvent.title`).
- Orchestrated expert teams emit a visible "专家动作 / Expert actions" section.
- `skill_loader` desktop disabled-skills settings scoped to the officev3 user-skill source only (no leak into tests/standalone loaders).

### Follow-ups / known gaps

- **P0 (ops, not code):** the incident that triggered this work had MCP `web_search` unavailable for the whole session (401 `authorization_verify_error` + fallback to lite model `raccoon-chat-ml-5-5`). Investigate officev3 MCP config/auth so `web_search` actually loads. The code fix only guarantees parity with whatever the parent has.
- **Runtime artifact:** only `darwin-arm64` built/uploaded. `darwin-x64` / Windows runtimes not built this release.
- **No-progress breaker limitation:** detects failing/empty tool results; a tool that "succeeds" with useless content (e.g. anti-scraping HTML) is not caught — bounded by `max_steps=40`.
- **Test hygiene:** full `pytest` shows ~14 env-dependent failures (filesystem permission/symlink scoping + a skill_loader test-pollution case); all pass in isolation and are unrelated to this release. Worth de-flaking later.
