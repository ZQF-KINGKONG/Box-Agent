"""Base class for LLM clients."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from ..auth import request_auth_headers
from ..retry import RetryConfig
from ..schema import LLMResponse, Message, StreamEvent

HOSTED_AUTH_API_KEY_PLACEHOLDERS = {
    "",
    "box-agent-auth-json",
    "box-agent-no-auth",
    "YOUR_API_KEY_HERE",
}


class LLMClientBase(ABC):
    """Abstract base class for LLM clients.

    This class defines the interface that all LLM clients must implement,
    regardless of the underlying API protocol (Anthropic, OpenAI, etc.).
    """

    def __init__(
        self,
        api_key: str,
        api_base: str,
        model: str,
        retry_config: RetryConfig | None = None,
        auth_token: str = "",
        auth_file: str = "",
    ):
        """Initialize the LLM client.

        Args:
            api_key: API key for authentication
            api_base: Base URL for the API
            model: Model name to use
            retry_config: Optional retry configuration
            auth_token: Optional in-memory product login token.
            auth_file: Optional auth.json path read before every request.
        """
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.retry_config = retry_config or RetryConfig()
        self.auth_token = auth_token
        self.auth_file = auth_file

        # Callback for tracking retry count
        self.retry_callback = None

    def _auth_headers(self, existing: dict[str, str] | None = None) -> dict[str, str]:
        """Read current login auth and return request headers."""
        headers = dict(existing or {})
        if self.api_key.strip() not in HOSTED_AUTH_API_KEY_PLACEHOLDERS:
            return headers

        return request_auth_headers(
            auth_file=self.auth_file,
            explicit_token=self.auth_token,
            existing=headers,
            url=self.api_base,
        )

    @staticmethod
    def _session_header(session_id: str = "") -> dict[str, str]:
        """Return the per-request session header for upstream trace correlation.

        When ``session_id`` is a non-empty string, emit ``X-RACCOON-Session-ID``
        so the gateway can attach the request to a caller-owned Langfuse session.
        An empty value yields an empty dict, so the gateway falls back to its
        default session-creation rule. The value is forwarded verbatim — the
        client never generates or rewrites it.
        """
        sid = (session_id or "").strip()
        return {"X-RACCOON-Session-ID": sid} if sid else {}

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        *,
        thinking_enabled: bool = False,
        session_id: str = "",
    ) -> LLMResponse:
        """Generate response from LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of Tool objects or dicts
            thinking_enabled: When True, request extended thinking from the
                provider (Anthropic native, or Qwen-style ``enable_thinking``
                for OpenAI-compatible endpoints). Silent no-op for providers
                that don't support it.
            session_id: Optional caller-owned session id. When non-empty, sent
                as the ``X-RACCOON-Session-ID`` header so the gateway groups the
                request under that Langfuse session; empty falls back to the
                gateway default.

        Returns:
            LLMResponse containing the generated content, thinking, and tool calls
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        *,
        thinking_enabled: bool = False,
        session_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        """Generate streaming response from LLM.

        Yields StreamEvent chunks for thinking/text deltas as they arrive.
        The final event has type="finish" and carries tool_calls + usage.

        Args:
            messages: List of conversation messages
            tools: Optional list of Tool objects or dicts
            thinking_enabled: See ``generate()``.
            session_id: See ``generate()``.

        Yields:
            StreamEvent chunks
        """
        pass
        # Make it a valid async generator
        if False:  # pragma: no cover
            yield  # type: ignore[misc]

    @abstractmethod
    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare the request payload for the API.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            Dictionary containing the request payload
        """
        pass

    @abstractmethod
    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal message format to API-specific format.

        Args:
            messages: List of internal Message objects

        Returns:
            Tuple of (system_message, api_messages)
        """
        pass
