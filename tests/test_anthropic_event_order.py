"""Test Anthropic client event order error handling."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from box_agent.llm.anthropic_client import AnthropicClient
from box_agent.schema import Message


@pytest.mark.asyncio
async def test_event_order_error_on_stream_creation():
    """Test that event order errors during stream creation get a helpful error message."""
    client = AnthropicClient(
        api_key="test-key",
        model="claude-3-5-sonnet-20241022",
    )

    messages = [Message(role="user", content="test")]

    # Mock the stream() method to raise the SDK's event order error immediately
    with patch.object(
        client.client.messages,
        'stream',
        side_effect=RuntimeError('Unexpected event order, got content_block_start before "message_start"')
    ):
        with pytest.raises(RuntimeError) as exc_info:
            async for _ in client.generate_stream(messages):
                pass

    # Verify the error message is helpful and mentions the compatibility issue
    error_msg = str(exc_info.value)
    assert "API 返回的事件顺序不符合 Anthropic 协议规范" in error_msg
    assert "第三方 API 的兼容性问题" in error_msg
    assert "OpenAI 兼容模式" in error_msg


@pytest.mark.asyncio
async def test_event_order_error_during_stream_context():
    """Test event order error that occurs when entering stream context."""
    client = AnthropicClient(
        api_key="test-key",
        model="claude-3-5-sonnet-20241022",
    )

    messages = [Message(role="user", content="test")]

    # Mock stream context manager that raises on __aenter__
    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(
        side_effect=RuntimeError('Unexpected event order, got content_block_start before "message_start"')
    )
    mock_stream.__aexit__ = AsyncMock()

    with patch.object(client.client.messages, 'stream', return_value=mock_stream):
        with pytest.raises(RuntimeError) as exc_info:
            async for _ in client.generate_stream(messages):
                pass

    error_msg = str(exc_info.value)
    assert "API 返回的事件顺序不符合 Anthropic 协议规范" in error_msg

