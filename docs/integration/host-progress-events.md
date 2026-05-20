# Host progress event integration

Box-Agent emits agent text, tool calls, and structured tool progress through ACP session updates. Host UIs should treat `rawOutput.type` as the discriminator for structured execution state. Do not infer sub-agent state from generic fields such as `rawInput.task`; tools like `todo_write` also have a `task` argument.

## Rendering model

Recommended host layout:

- Main conversation: assistant text, final answer, and user-visible fatal errors.
- Tool/activity cards: tool calls, sub-agent progress, todo snapshots, artifacts, and web search metadata.
- Default collapsed details: sub-agent internals should be grouped and collapsible, not appended one-by-one as chat messages.

## Sub-agent progress

A genuine sub-agent progress update arrives as a tool-call update whose `rawOutput.type` is `sub_agent_progress`.

Example:

```json
{
  "type": "sub_agent_progress",
  "parent_tool_call_id": "call_abc",
  "sub_agent_id": "subagent-...",
  "task_preview": "Inspect one file",
  "event": "tool_start",
  "tool_name": "read"
}
```

Grouping key:

1. Group all updates under `parent_tool_call_id` inside the parent `sub_agent` tool card.
2. Inside that card, group child rows by `sub_agent_id`.
3. Use `task_preview` only as a display label, not as an identifier.

Known `event` values:

- `step_start`: includes `step`, `max_steps`.
- `tool_start`: includes `tool_name`.
- `tool_result`: includes `tool_name`, `success`.
- `artifact`: includes artifact metadata such as `filename`, `path`, `mime_type`, `size_bytes`.
- `error`: includes `message`.
- Other values may appear for forward compatibility; render them as low-priority detail rows.

Final sub-agent summaries still arrive on the parent tool-call result (`tool_name = sub_agent`). Hosts may show the summary in the tool card, while the main conversation should wait for the parent agent's assistant message.

## Todo snapshots

Todo tools emit host-friendly snapshots through tool-call result `rawOutput`:

```json
{
  "type": "todo_snapshot",
  "action": "create",
  "item": {
    "id": "1",
    "task": "Plan host integration",
    "status": "pending",
    "priority": "medium",
    "created_at": "..."
  },
  "items": [
    {
      "id": "1",
      "task": "Plan host integration",
      "status": "pending",
      "priority": "medium",
      "created_at": "..."
    }
  ],
  "summary": {
    "total": 1,
    "completed": 0,
    "in_progress": 0,
    "pending": 1
  }
}
```

Host behavior:

- Render this as a checklist/task panel.
- Replace the current todo state with `items` for that session or message scope.
- Do not classify `todo_write` as sub-agent work just because `rawInput.task` exists.
- A `todo_read` result also includes `todo_snapshot`; it may omit `action` and `item`.

## Minimal TypeScript handling

```ts
function handleToolUpdate(update: ToolCallUpdate) {
  const raw = update.rawOutput;

  if (raw && typeof raw === 'object' && raw.type === 'sub_agent_progress') {
    upsertSubAgentProgress({
      parentToolCallId: raw.parent_tool_call_id ?? update.toolCallId,
      subAgentId: raw.sub_agent_id,
      taskPreview: raw.task_preview,
      event: raw,
    });
    return;
  }

  if (raw && typeof raw === 'object' && raw.type === 'todo_snapshot') {
    replaceTodoSnapshot(raw.items, raw.summary);
    return;
  }

  renderGenericToolUpdate(update);
}
```

## Compatibility notes

- Older runtimes may emit `sub_agent_progress` without `sub_agent_id`; hosts can fall back to `parent_tool_call_id + task_preview` with lower confidence.
- Older runtimes may return todo results as plain text only; hosts should keep the generic tool renderer as fallback.
- `rawOutput.type` is the stable discriminator. Avoid title/text heuristics such as `title.includes("sub_agent")` or `rawInput.task`.
