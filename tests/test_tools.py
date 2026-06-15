"""Test cases for tools."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from box_agent.tools import BashTool, EditTool, ReadTool, WriteTool


@pytest.mark.asyncio
async def test_read_tool():
    """Test read file tool."""
    print("\n=== Testing ReadTool ===")

    # Create a temp file
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Hello, World!")
        temp_path = f.name

    try:
        tool = ReadTool()
        result = await tool.execute(path=temp_path)

        assert result.success, f"Read failed: {result.error}"
        # ReadTool now returns content with line numbers in format: "LINE_NUMBER|LINE_CONTENT"
        assert "Hello, World!" in result.content, f"Content mismatch: {result.content}"
        assert "|Hello, World!" in result.content, f"Expected line number format: {result.content}"
        print("✅ ReadTool test passed")
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_write_tool():
    """Test write file tool."""
    print("\n=== Testing WriteTool ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.txt"

        tool = WriteTool()
        result = await tool.execute(path=str(file_path), content="Test content")

        assert result.success, f"Write failed: {result.error}"
        assert file_path.exists(), "File was not created"
        assert file_path.read_text() == "Test content", "Content mismatch"
        print("✅ WriteTool test passed")


@pytest.mark.asyncio
async def test_write_tool_blocks_pptx_skipcheck_exporter():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "export_skipcheck.js"
        tool = WriteTool()
        result = await tool.execute(
            path=str(file_path),
            content='await window.domToPptx.exportToPptx([]); require("./dom-to-pptx.bundle.js");',
        )

        assert not result.success
        assert "PPTX HTML self-check bypass blocked" in result.error
        assert not file_path.exists()


@pytest.mark.asyncio
async def test_write_tool_rejects_model_history_placeholder():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "deck.html"
        tool = WriteTool()
        result = await tool.execute(
            path=str(file_path),
            content=(
                "[Full tool-call argument omitted from model history]\n"
                "Tool: write_file\n"
                "Argument: content\n"
                "Path: output/deck.html"
            ),
        )

        assert not result.success
        assert "model-history placeholder" in result.error
        assert not file_path.exists()


@pytest.mark.asyncio
async def test_edit_tool():
    """Test edit file tool."""
    print("\n=== Testing EditTool ===")

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Hello, World!")
        temp_path = f.name

    try:
        tool = EditTool()
        result = await tool.execute(
            path=temp_path, old_str="World", new_str="Agent"
        )

        assert result.success, f"Edit failed: {result.error}"
        content = Path(temp_path).read_text()
        assert content == "Hello, Agent!", f"Content mismatch: {content}"
        print("✅ EditTool test passed")
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_edit_tool_rejects_model_history_placeholder():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".html") as f:
        f.write("<html><body>real</body></html>")
        temp_path = f.name

    try:
        tool = EditTool()
        result = await tool.execute(
            path=temp_path,
            old_str="real",
            new_str=(
                "[Full tool-call argument omitted from model history]\n"
                "Tool: edit_file\n"
                "Argument: new_str\n"
                f"Path: {temp_path}"
            ),
        )

        assert not result.success
        assert "model-history placeholder" in result.error
        assert Path(temp_path).read_text() == "<html><body>real</body></html>"
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_edit_tool_blocks_removing_pptx_self_check():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".js") as f:
        f.write('runSelfCheck(htmlPath, width, height, reportPath); require("./html_to_editable_pptx.js");')
        temp_path = f.name

    try:
        tool = EditTool()
        result = await tool.execute(
            path=temp_path,
            old_str="runSelfCheck(htmlPath, width, height, reportPath);",
            new_str="// removed to skip self-check",
        )

        assert not result.success
        assert "PPTX HTML self-check bypass blocked" in result.error
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_bash_tool():
    """Test bash command tool."""
    print("\n=== Testing BashTool ===")

    tool = BashTool()

    # Test successful command
    result = await tool.execute(command="echo 'Hello from bash'")
    assert result.success, f"Bash failed: {result.error}"
    assert "Hello from bash" in result.content, f"Output mismatch: {result.content}"
    print("✅ BashTool test passed")

    # Test failed command
    result = await tool.execute(command="exit 1")
    assert not result.success, "Command should have failed"
    print("✅ BashTool error handling test passed")


@pytest.mark.asyncio
async def test_bash_tool_blocks_lark_bot_identity_commands():
    tool = BashTool()

    for command in [
        'lark-cli config bind --identity bot-only',
        '$BOX_AGENT_LARK_CLI config bind --identity bot-only',
        'lark-cli config strict-mode bot',
        'lark-cli base +table-list --base-token abc --as bot',
    ]:
        result = await tool.execute(command=command)
        assert not result.success
        assert "Blocked:" in (result.error or "")


@pytest.mark.asyncio
async def test_bash_tool_requires_lark_business_commands_to_use_user_identity():
    tool = BashTool()

    result = await tool.execute(command='lark-cli base +table-list --base-token abc --format json')

    assert not result.success
    assert "must pass `--as user`" in (result.error or "")


@pytest.mark.asyncio
async def test_bash_tool_allows_setting_lark_cli_env_without_invoking_cli():
    tool = BashTool()

    result = await tool.execute(command='export BOX_AGENT_LARK_CLI=/tmp/lark-cli')

    assert result.success


async def main():
    """Run all tool tests."""
    print("=" * 80)
    print("Running Tool Tests")
    print("=" * 80)

    await test_read_tool()
    await test_write_tool()
    await test_edit_tool()
    await test_bash_tool()

    print("\n" + "=" * 80)
    print("All tool tests passed! ✅")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
