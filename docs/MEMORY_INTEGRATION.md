# Memory System Integration Guide

Box-Agent provides persistent cross-session memory with core memory plus topic-sharded context memory:

| Type | Purpose | Recall behavior | Storage |
|------|---------|-----------------|---------|
| **Core memory** | User identity, explicit preferences, local defaults, durable behavioral rules | Automatically injected into the system prompt at session start | `~/.box-agent/memory/MEMORY.md` |
| **Context memory** | Project context, task templates, historical notes, decisions, deadlines | Topic-routed search on demand via `memory_search`; not automatically injected | `~/.box-agent/memory/context/<topic>.md` |

This split keeps high-signal user facts always available while preventing project/history notes from bloating every prompt.

---

## 1. Configuration

Add these values to `config.yaml` if you need to override the defaults:

```yaml
enable_memory: true                    # Enable memory tools and startup core recall
memory_dir: "~/.box-agent/memory"      # Memory storage directory

enable_memory_extraction: true         # Auto-extract useful memory from agent lifecycle points
memory_extraction_cooldown: 300        # Seconds between extraction attempts
memory_extraction_step_interval: 10    # Extract every N agent steps
```

Set `enable_memory: false` to disable the memory manager and memory tools.

---

## 2. Tool interface

### `memory_write` — write persistent memory

```json
{
  "name": "memory_write",
  "arguments": {
    "content": "- 用户偏好中文回答\n- Q2 goal: launch data dashboard by 6/30",
    "category": "context",
    "mode": "append"
  }
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `content` | string | Yes | Markdown bullet-style memory content |
| `category` | `core` or `context` | No | `core` for explicit user identity/preferences/rules; `context` for project/task history. Default: `core` |
| `mode` | `append` or `overwrite` | No | `append` merges/appends; `overwrite` replaces the target file |
| `topic` | string | No | Context bucket when `category="context"`, for example `preferences`, `project`, `feedback`, or `general` |

#### Core writes

`category="core"` writes to `MEMORY.md`.

Use core only when the user explicitly states durable personal information or preferences, for example:

```text
- User prefers concise Chinese responses
- User is a product manager in the data platform team
- 用户用于本地查询的默认城市是北京
- Do not add emoji in final answers
```

#### Context writes

`category="context"` writes to topic-sharded context memory under `context/<topic>.md`.

When an LLM client is available, append-mode context writes are model-merged with existing memory:

1. Box-Agent sends the candidate memory plus current `MEMORY.md` and context memory to the LLM.
2. The LLM returns a structured operation plan: `add`, `replace`, `drop`, or `noop`.
3. Code applies the plan safely:
   - `replace` and `drop` require an exact full-line match.
   - `add` is line-deduped against both Core and Context.
   - Invalid model JSON falls back to append-with-dedup.

When no LLM is available, context writes use append-with-dedup directly.

### `memory_read` — read all persistent memory

```json
{
  "name": "memory_read",
  "arguments": {}
}
```

Returns both `MEMORY.md` and context memory when present.

### `memory_search` — search context memory

```json
{
  "name": "memory_search",
  "arguments": {
    "query": "weekly report"
  }
}
```

Search is a case-insensitive keyword search over context entries. When `topic` is omitted, Box-Agent first uses the topic sidecar index (`context/_index.json`) to route the query to likely topic files, then falls back to all topics if the routed search finds nothing. Core memory is already present in the prompt, so `memory_search` only searches context memory.

---

## 3. CLI integration

No additional integration code is needed. When `enable_memory: true`:

- **Startup**: `MEMORY.md` is recalled and injected into the system prompt if non-empty.
- **During a session**: the agent can call `memory_write`, `memory_read`, and `memory_search`.
- **Lifecycle extraction**: when `enable_memory_extraction: true`, the agent loop periodically asks the LLM to extract cross-session-useful memory. Explicit user profile/preferences/local defaults can go to core; project and task history go to topic-sharded context memory.

Manual editing is also possible:

```bash
vim ~/.box-agent/memory/MEMORY.md
vim ~/.box-agent/memory/context/preferences.md
```

---

## 4. ACP / Runtime integration

Memory tools are registered as normal tools and are available through standard ACP tool calls.

### 4.1 Writing memory

A host can prompt the agent to remember something:

```python
prompt_text = "请记住：用户偏好简洁的中文回答"
```

The agent may then call:

```text
memory_write(content="- 用户偏好简洁的中文回答", category="core", mode="append")
```

For project context:

```text
memory_write(content="- Weekly report format: progress/issues/next week", category="context", mode="append")
```

With an LLM-backed memory tool, context writes return a strategy label such as:

```text
Memory updated (context, applied). Current context memory: ...
Memory updated (context, no_change). Current context memory: ...
Memory updated (context, fallback_appended). Current context memory: ...
```

### 4.2 Automatic recall

On ACP `newSession`, Box-Agent:

1. Reads `MEMORY.md`.
2. Builds a memory block if core memory exists.
3. Appends the block to the session system prompt.

Format:

```text
--- MEMORY START ---

[Core Memory]
- 用户偏好中文回答
- 用户希望结果简洁

--- MEMORY END ---
```

Context memory is not injected automatically; use `memory_search` when the agent needs project/task context.

---

## 5. Storage layout

```text
~/.box-agent/memory/
├── MEMORY.md          # Core memory, always recalled at session start
├── context/           # Searchable context memory by topic
│   ├── _index.json    # Topic routing index
│   ├── general.md
│   ├── preferences.md
│   └── project.md
└── .openclaw_imported # Marker for one-time OpenClaw import, when applicable
```

`MEMORY.md` and topic files under `context/` are plain UTF-8 markdown files. Bullet points are recommended because model merge and line-level safety checks operate on full lines.

---

## 6. Automatic memory extraction

When `enable_memory_extraction` is enabled, `MemoryExtractor` analyzes recent conversation at lifecycle points:

- before context summarization (`pre_summarize`)
- every configured step interval (`step_interval`)
- at loop end (`loop_end`)

The extractor can write explicit user-stated profile facts, preferences, and local defaults to `MEMORY.md`. For example, if the user says they are in Beijing while asking for weather, the extractor should save a cautious default such as `- 用户用于本地查询的默认城市是北京`, not infer a permanent residence.

Project context, task patterns, historical notes, decisions, deadlines, and behavioral feedback still go to topic-sharded context memory. This keeps one-off task details out of core memory.

---

## 7. One-time OpenClaw import

At startup, if memory is enabled, Box-Agent attempts a one-time import from:

```text
~/.openclaw/**/USER.md
~/.openclaw/**/MEMORY.md
```

The LLM filters those files for durable user identity/preferences/habits and appends useful results to `MEMORY.md`. A `.openclaw_imported` marker prevents repeated imports.

---

## 8. Python API

```python
from box_agent.memory import MemoryManager

mgr = MemoryManager(memory_dir="~/.box-agent/memory")

# Core memory
mgr.append_core("- 用户偏好中文")
print(mgr.read_core())

# Context memory
mgr.append_context("- Weekly report format: progress/issues/next week", topic="preferences")
print(mgr.search("weekly report", topic="preferences"))

# Startup recall block for system prompt injection
block = mgr.recall()

# LLM-assisted context merge
await mgr.update_context_with_llm(
    "- Weekly report should include progress, issues, and next-week plan",
    llm_client,
)
```

Legacy aliases remain for compatibility:

```python
mgr.read_manual_memory()
mgr.write_manual_memory("- 用户偏好中文")
mgr.read_all()
mgr.write_all("- 用户偏好中文")
```
