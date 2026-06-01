"""Offline regression tests for X-RACCOON-Session-ID header propagation.

The caller (e.g. officev3) passes its own session id via ACP ``_meta.session_id``.
Box-Agent forwards it verbatim to the gateway as the ``X-RACCOON-Session-ID``
request header so LLM calls are grouped under that Langfuse session. An empty
session id must NOT emit the header, so the gateway falls back to its default
session-creation rule.

These tests stub the underlying SDK client so they run without network access
or a real config, asserting purely on the outbound request params.
"""

import pytest

from box_agent.llm import AnthropicClient, OpenAIClient
from box_agent.llm.base import LLMClientBase
from box_agent.llm.llm_wrapper import LLMClient, LLMProvider
from box_agent.retry import RetryConfig
from box_agent.schema import Message

_HEADER = "X-RACCOON-Session-ID"
# A normal (non-hosted-placeholder) key so _auth_headers passes the session
# header through untouched instead of swapping in bearer-token logic.
_API_KEY = "sk-test-not-a-placeholder"


class _FakeParsed:
    """Stand-in for a parsed SDK response; only ``content`` is read downstream."""

    content = "ok"
    thinking = None
    finish_reason = "stop"
    tool_calls: list = []
    usage = None


class _FakeRawResponse:
    request_id = "req-test"
    headers: dict = {}

    def parse(self):
        return _FakeParsed()


class _CapturingCreate:
    """Captures the kwargs of the last ``create(**params)`` call."""

    def __init__(self):
        self.last_params: dict | None = None

    def __call__(self, **params):
        self.last_params = params
        return _FakeRawResponse()


def _install_anthropic_fake(client: AnthropicClient) -> _CapturingCreate:
    cap = _CapturingCreate()

    class _WRR:
        create = staticmethod(cap)

    class _Messages:
        with_raw_response = _WRR()

    class _FakeSDK:
        messages = _Messages()

    client.client = _FakeSDK()
    return cap


def _install_openai_fake(client: OpenAIClient) -> _CapturingCreate:
    cap = _CapturingCreate()

    class _WRR:
        create = staticmethod(cap)

    class _Completions:
        with_raw_response = _WRR()

    class _Chat:
        completions = _Completions()

    class _FakeSDK:
        chat = _Chat()

    client.client = _FakeSDK()
    return cap


async def _capture_generate(client, **kwargs) -> _CapturingCreate | None:
    """Call ``client.generate`` and capture outbound params.

    The header is injected into the request params *before* the SDK
    ``create()`` call, which is where ``_CapturingCreate`` records them. We
    don't feed a provider-correct fake response, so ``_parse_response`` may
    raise afterwards — that's irrelevant here, since the outbound request has
    already been captured. Swallow any post-capture error and assert on params.
    """
    try:
        await client.generate(**kwargs)
    except Exception:
        pass



# ── _session_header unit behavior ────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("sess-7-abc", {_HEADER: "sess-7-abc"}),
        ("  sess-trim  ", {_HEADER: "sess-trim"}),
        ("", {}),
        (None, {}),
    ],
)
def test_session_header_helper(value, expected):
    if value is None:
        assert LLMClientBase._session_header() == expected
    else:
        assert LLMClientBase._session_header(value) == expected


# ── Anthropic client ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_generate_emits_session_header():
    client = AnthropicClient(
        api_key=_API_KEY, api_base="https://api.anthropic.com", model="m",
        retry_config=RetryConfig(enabled=False),
    )
    cap = _install_anthropic_fake(client)

    await _capture_generate(client, messages=[Message(role="user", content="hi")], session_id="sess-77")

    assert cap.last_params is not None
    assert cap.last_params.get("extra_headers", {}).get(_HEADER) == "sess-77"


@pytest.mark.asyncio
async def test_anthropic_generate_omits_header_when_empty():
    client = AnthropicClient(
        api_key=_API_KEY, api_base="https://api.anthropic.com", model="m",
        retry_config=RetryConfig(enabled=False),
    )
    cap = _install_anthropic_fake(client)

    await _capture_generate(client, messages=[Message(role="user", content="hi")])

    assert cap.last_params is not None
    assert _HEADER not in cap.last_params.get("extra_headers", {})


# ── OpenAI client ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_openai_generate_emits_session_header():
    client = OpenAIClient(
        api_key=_API_KEY, api_base="https://api.example.com/v1", model="m",
        retry_config=RetryConfig(enabled=False),
    )
    cap = _install_openai_fake(client)

    await _capture_generate(client, messages=[Message(role="user", content="hi")], session_id="sess-88")

    assert cap.last_params is not None
    assert cap.last_params.get("extra_headers", {}).get(_HEADER) == "sess-88"


@pytest.mark.asyncio
async def test_openai_generate_omits_header_when_empty():
    client = OpenAIClient(
        api_key=_API_KEY, api_base="https://api.example.com/v1", model="m",
        retry_config=RetryConfig(enabled=False),
    )
    cap = _install_openai_fake(client)

    await _capture_generate(client, messages=[Message(role="user", content="hi")])

    assert cap.last_params is not None
    assert _HEADER not in cap.last_params.get("extra_headers", {})


# ── Wrapper threads session_id through ───────────────────────────────────────


@pytest.mark.asyncio
async def test_wrapper_threads_session_id_to_client():
    wrapper = LLMClient(
        api_key=_API_KEY, provider=LLMProvider.ANTHROPIC,
        api_base="https://api.anthropic.com", model="m",
        retry_config=RetryConfig(enabled=False),
    )
    cap = _install_anthropic_fake(wrapper._client)

    await _capture_generate(wrapper, messages=[Message(role="user", content="hi")], session_id="sess-wrap")

    assert cap.last_params is not None
    assert cap.last_params.get("extra_headers", {}).get(_HEADER) == "sess-wrap"
