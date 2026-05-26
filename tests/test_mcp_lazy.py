"""Tests for lazy MCP server loading driven by SkillSelector cumulative query."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from box_agent.tools.base import Tool, ToolResult
from box_agent.tools.mcp_loader import (
    _lazy_mcp_pending,
    cleanup_mcp_connections,
    ensure_lazy_mcp_loaded,
    get_pending_lazy_mcp_servers,
    load_mcp_tools_async,
)


class _StubMCPTool(Tool):
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"stub {self._name}"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, content="ok")


@pytest.fixture(autouse=True)
def _reset_lazy_state():
    """Make sure each test starts with an empty lazy pending registry."""
    _lazy_mcp_pending.clear()
    yield
    asyncio.run(cleanup_mcp_connections())
    _lazy_mcp_pending.clear()


def _write_config(servers: dict) -> Path:
    fd = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump({"mcpServers": servers}, fd)
    fd.flush()
    fd.close()
    return Path(fd.name)


async def test_lazy_server_deferred_at_startup(monkeypatch):
    """Lazy server is parked, not connected, when loader runs."""
    cfg = _write_config(
        {
            "browser": {
                "command": "noop",
                "args": [],
                "lazy": True,
                "keywords": ["browser", "浏览器"],
            }
        }
    )

    connect_calls: list[str] = []

    async def fake_connect(self):
        connect_calls.append(self.name)
        self.tools = [_StubMCPTool(f"{self.name}_tool")]
        return True

    monkeypatch.setattr(
        "box_agent.tools.mcp_loader.MCPServerConnection.connect",
        fake_connect,
    )

    tools = await load_mcp_tools_async(str(cfg))
    assert tools == []
    assert connect_calls == []
    pending = get_pending_lazy_mcp_servers()
    assert pending == {"browser": ["browser", "浏览器"]}


async def test_lazy_loaded_on_keyword_match(monkeypatch):
    cfg = _write_config(
        {
            "browser": {
                "command": "noop",
                "args": [],
                "lazy": True,
                "keywords": ["browser", "浏览器"],
            }
        }
    )

    async def fake_connect(self):
        self.tools = [_StubMCPTool("browser_open")]
        return True

    monkeypatch.setattr(
        "box_agent.tools.mcp_loader.MCPServerConnection.connect",
        fake_connect,
    )

    await load_mcp_tools_async(str(cfg))
    assert "browser" in get_pending_lazy_mcp_servers()

    new_tools = await ensure_lazy_mcp_loaded("帮我打开浏览器看一下")
    names = [t.name for t in new_tools]
    assert names == ["browser_open"]
    assert get_pending_lazy_mcp_servers() == {}

    # Second call is a no-op — server already promoted out of pending.
    again = await ensure_lazy_mcp_loaded("再打开浏览器一次")
    assert again == []


async def test_lazy_skipped_when_no_match(monkeypatch):
    cfg = _write_config(
        {
            "browser": {
                "command": "noop",
                "args": [],
                "lazy": True,
                "keywords": ["browser", "浏览器"],
            }
        }
    )

    connect_calls: list[str] = []

    async def fake_connect(self):
        connect_calls.append(self.name)
        self.tools = [_StubMCPTool("browser_open")]
        return True

    monkeypatch.setattr(
        "box_agent.tools.mcp_loader.MCPServerConnection.connect",
        fake_connect,
    )

    await load_mcp_tools_async(str(cfg))

    new_tools = await ensure_lazy_mcp_loaded("帮我写一段 python 函数")
    assert new_tools == []
    assert connect_calls == []
    assert "browser" in get_pending_lazy_mcp_servers()


async def test_empty_query_is_safe(monkeypatch):
    cfg = _write_config(
        {
            "browser": {
                "command": "noop",
                "args": [],
                "lazy": True,
                "keywords": ["browser"],
            }
        }
    )

    monkeypatch.setattr(
        "box_agent.tools.mcp_loader.MCPServerConnection.connect",
        lambda self: asyncio.sleep(0, result=True),
    )

    await load_mcp_tools_async(str(cfg))
    assert await ensure_lazy_mcp_loaded("") == []
    assert await ensure_lazy_mcp_loaded("   ") == []
    assert "browser" in get_pending_lazy_mcp_servers()


async def test_skillselector_cumulative_query_accumulates():
    from box_agent.tools.skill_loader import SKILL_SLOT_SENTINEL, SkillLoader, SkillSelector

    loader = SkillLoader.__new__(SkillLoader)
    loader._sources = []
    loader.loaded_skills = {}
    sel = SkillSelector(loader)
    sel.bind(f"dummy {SKILL_SLOT_SENTINEL} dummy")
    sel.update("做个 PPT")
    sel.update("再导出飞书")
    assert "PPT" in sel.cumulative_query
    assert "飞书" in sel.cumulative_query
