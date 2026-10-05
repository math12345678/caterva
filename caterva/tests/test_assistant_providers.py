"""The provider layer, over an injected fake transport.

THESE ARE MECHANISM TESTS. `FakeTransport` stands in for the network, so what
is proved is that requests are built and sent correctly, that retries and
errors behave, and that no key reaches a body, an error or a log. Nothing here
says what a real provider or model would answer.
"""
from __future__ import annotations

import json

import pytest
from assistant_support import TEST_KEY, FakeTransport, anthropic_reply, openai_reply

from caterva.assistant.providers import (
    PROVIDERS, AssistantError, Provider, TransportResponse, build_request, parse_reply, validate_local_url,
)


def _provider(name, transport, key=TEST_KEY, **kw):
    return Provider(name, kw.pop("model", "m-1"), transport=transport, key=key, sleep=lambda s: None, **kw)


def test_anthropic_request_shape_and_headers():
    req = build_request("anthropic", "claude-sonnet-5-5", "SYS", "USER", max_tokens=300)
    body = json.loads(req.body)
    assert req.url == "https://api.anthropic.com/v1/messages"
    assert body == {"model": "claude-sonnet-5-5", "max_tokens": 300, "system": "SYS",
                    "messages": [{"role": "user", "content": "USER"}]}
    assert "x-api-key" not in req.headers and req.headers["anthropic-version"]
    assert "tools" not in body and "tool_choice" not in body and "stream" not in body


def test_openai_compatible_request_shape_for_each_provider():
    for name in ("openai", "groq", "openrouter", "mistral", "local"):
        req = build_request(name, "model-x", "SYS", "USER", max_tokens=200)
        body = json.loads(req.body)
        assert body["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
        assert "tools" not in body and "functions" not in body and "stream" not in body
        assert req.url.endswith("/chat/completions")
        assert ("max_completion_tokens" in body) == (name == "openai")


def test_the_credential_is_added_only_at_send_time_and_never_to_the_body():
    ft = FakeTransport(anthropic_reply("hi"))
    request = build_request("anthropic", "m", "S", "U", max_tokens=100)
    assert TEST_KEY.encode() not in request.body
    _provider("anthropic", ft).send(request)
    assert ft.calls[0]["headers"]["x-api-key"] == TEST_KEY
    assert TEST_KEY.encode() not in ft.calls[0]["body"]
    ft2 = FakeTransport(openai_reply("hi"))
    _provider("groq", ft2).send(build_request("groq", "m", "S", "U", max_tokens=100))
    assert ft2.calls[0]["headers"]["authorization"] == f"Bearer {TEST_KEY}"


def test_a_local_model_sends_no_credential_and_needs_no_key():
    ft = FakeTransport(openai_reply("ready"))
    request = build_request("local", "llama", "S", "U", max_tokens=100)
    text, _, _ = _provider("local", ft, key=None).send(request)
    assert text == "ready"
    assert "authorization" not in ft.calls[0]["headers"] and "x-api-key" not in ft.calls[0]["headers"]


def test_a_missing_key_is_refused_before_anything_is_sent():
    ft = FakeTransport(anthropic_reply("hi"))
    with pytest.raises(AssistantError) as caught:
        _provider("anthropic", ft, key=None).send(build_request("anthropic", "m", "S", "U", max_tokens=100))
    assert caught.value.code == "no_key" and ft.calls == []


def test_max_tokens_is_clamped_and_a_model_is_required():
    assert json.loads(build_request("anthropic", "m", "S", "U", max_tokens=10 ** 6).body)["max_tokens"] == 4096
    assert json.loads(build_request("anthropic", "m", "S", "U", max_tokens=1).body)["max_tokens"] == 16
    with pytest.raises(AssistantError, match="model"):
        build_request("anthropic", "  ", "S", "U", max_tokens=100)
    with pytest.raises(AssistantError):
        build_request("nobody", "m", "S", "U", max_tokens=100)


def test_only_a_loopback_address_is_a_local_model():
    assert validate_local_url("http://127.0.0.1:11434/v1/chat/completions")
    assert validate_local_url("http://localhost:1234/v1/chat/completions")
    for bad in ("http://example.com/v1/chat/completions", "http://10.0.0.5:11434/x", "ftp://127.0.0.1/x",
                "http://127.0.0.1@evil.example/x", "http://user:pw@127.0.0.1/x", "file:///etc/passwd"):
        with pytest.raises(AssistantError):
            validate_local_url(bad)


def test_retries_on_429_and_5xx_and_connection_failures_then_succeeds():
    ft = FakeTransport(TransportResponse(429, b'{"error":{"message":"slow down"}}', {"retry-after": "1"}),
                       AssistantError("network", "boom"), TransportResponse(503, b"{}"), anthropic_reply("fine"))
    counted = []
    p = _provider("anthropic", ft, attempts=4, count_attempt=lambda: counted.append(1))
    text, _, attempts = p.send(build_request("anthropic", "m", "S", "U", max_tokens=100))
    assert (text, attempts, len(ft.calls), len(counted)) == ("fine", 4, 4, 4)


def test_gives_up_after_the_attempts_and_says_why_in_plain_words():
    ft = FakeTransport(TransportResponse(500, b'{"error":{"message":"overloaded"}}'))
    with pytest.raises(AssistantError) as caught:
        _provider("anthropic", ft, attempts=3).send(build_request("anthropic", "m", "S", "U", max_tokens=100))
    assert caught.value.code == "provider" and "500" in caught.value.message and len(ft.calls) == 3


def test_an_auth_failure_is_not_retried_and_never_echoes_the_key():
    echoed = json.dumps({"error": {"message": f"Invalid API key provided: {TEST_KEY}"}}).encode()
    ft = FakeTransport(TransportResponse(401, echoed))
    with pytest.raises(AssistantError) as caught:
        _provider("anthropic", ft).send(build_request("anthropic", "m", "S", "U", max_tokens=100))
    assert caught.value.code == "auth" and len(ft.calls) == 1
    assert TEST_KEY not in caught.value.message and TEST_KEY not in str(caught.value)
    assert "Settings" in caught.value.message


def test_an_exception_from_the_transport_cannot_leak_the_key_through_its_text():
    class Leaky(FakeTransport):
        def post(self, url, headers, body, timeout):
            raise RuntimeError(f"connection to host failed with header {headers.get('x-api-key')}")

    with pytest.raises(AssistantError) as caught:
        _provider("anthropic", Leaky(), attempts=1).send(build_request("anthropic", "m", "S", "U", max_tokens=100))
    assert TEST_KEY not in caught.value.message and "RuntimeError" in caught.value.message


def test_a_cancel_between_attempts_stops_retrying():
    ft = FakeTransport(TransportResponse(500, b"{}"))
    state = {"n": 0}

    def cancelled():
        state["n"] += 1
        return state["n"] > 1

    with pytest.raises(AssistantError) as caught:
        _provider("anthropic", ft, attempts=5).send(build_request("anthropic", "m", "S", "U", max_tokens=100), cancelled)
    assert caught.value.code == "cancelled" and len(ft.calls) == 1


def test_replies_are_read_in_each_wire_format_and_odd_replies_are_refused():
    assert parse_reply(PROVIDERS["anthropic"], anthropic_reply("a").body)[0] == "a"
    assert parse_reply(PROVIDERS["openai"], openai_reply("b").body)[0] == "b"
    for body in (b"not json", b"{}", b'{"content": []}', b'{"choices": []}', b'{"content":[{"type":"text","text":""}]}',
                 json.dumps({"content": [{"type": "tool_use", "name": "x", "input": {}}]}).encode()):
        with pytest.raises(AssistantError):
            parse_reply(PROVIDERS["anthropic"], body)
    with pytest.raises(AssistantError):
        parse_reply(PROVIDERS["openai"], b'{"choices":[{"message":{"content":null}}]}')


def test_a_tool_call_in_a_reply_is_never_acted_on_because_only_text_is_read():
    body = json.dumps({"content": [{"type": "text", "text": "ok"},
                                   {"type": "tool_use", "name": "delete_everything", "input": {"all": True}}]}).encode()
    text, _ = parse_reply(PROVIDERS["anthropic"], body)
    assert text == "ok"


def test_the_default_model_is_a_setting_not_a_constant_in_the_request_builder():
    from caterva.assistant.providers import DEFAULT_MODELS

    assert DEFAULT_MODELS == {"anthropic": "claude-sonnet-5-5"}   # the only default; the rest start empty
