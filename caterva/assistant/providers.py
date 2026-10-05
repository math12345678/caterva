"""Provider layer: Anthropic's Messages API and OpenAI-compatible chat completions, in process.

Two wire formats cover every provider the studio offers: Anthropic's
`/v1/messages`, and OpenAI-style `/chat/completions`, which OpenAI, Groq,
OpenRouter, Mistral and every local server (Ollama, LM Studio, llama.cpp) speak.

WHAT THIS MODULE DOES NOT DO
----------------------------
It holds no key. `build_request` returns the URL, the headers WITHOUT the
credential and the exact body bytes; `Provider.send` adds the credential at
the last moment and sends those same bytes. The consent preview shows the
body that is sent, byte for byte (`service.py`). The model has no tools, no
function calling and no side effects: the request carries text and the
response is read as text. It never streams (one request, one response).

THE TRANSPORT IS INJECTED
-------------------------
`Transport` is a one-method interface. The default sends with httpx over a
verifying TLS context (`caterva.tls.client_context`), a timeout, no redirects
and no proxy surprises. Tests inject a fake transport: that is a MECHANISM
test (retry, errors, headers, body) and says nothing about what a real model
would answer; every test docstring that uses one says so.

ERRORS
------
Every failure is an `AssistantError` with a short code and a plain sentence,
in the same style as Studio's network failures. Messages are scrubbed of key
shapes and of the key itself before they are created, because a provider's
error body sometimes echoes the credential it rejected.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple
from urllib.parse import urlsplit

from caterva.assistant.redact import scrub

LOOPBACK = ("127.0.0.1", "::1", "localhost", "[::1]")
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_TIMEOUT_S = 45.0
MAX_RESPONSE_BYTES = 256 * 1024
MAX_ATTEMPTS = 3
HARD_MAX_TOKENS = 4096

#: A sensible default per provider. Model ids change; the person edits them in
#: Settings, and where there is no safe default the field starts empty and the
#: assistant says it needs one rather than guessing an id that may be retired.
DEFAULT_MODELS: Mapping[str, str] = {"anthropic": "claude-sonnet-5-5"}


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    label: str
    wire: str                  # "anthropic" | "openai"
    base_url: str
    local: bool = False
    needs_key: bool = True
    max_tokens_field: str = "max_tokens"


PROVIDERS: Mapping[str, ProviderSpec] = {
    "anthropic": ProviderSpec("anthropic", "Anthropic", "anthropic", "https://api.anthropic.com/v1/messages"),
    "openai": ProviderSpec("openai", "OpenAI", "openai", "https://api.openai.com/v1/chat/completions",
                           max_tokens_field="max_completion_tokens"),
    "groq": ProviderSpec("groq", "Groq", "openai", "https://api.groq.com/openai/v1/chat/completions"),
    "openrouter": ProviderSpec("openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1/chat/completions"),
    "mistral": ProviderSpec("mistral", "Mistral", "openai", "https://api.mistral.ai/v1/chat/completions"),
    "local": ProviderSpec("local", "A model on this computer", "openai",
                          "http://127.0.0.1:11434/v1/chat/completions", local=True, needs_key=False),
}


class AssistantError(Exception):
    """A failure the studio reports in plain words. `code` is stable; `message` is safe to show."""

    def __init__(self, code: str, message: str, *, status: int = 503, retry_after_s: Optional[int] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retry_after_s = retry_after_s


@dataclass
class TransportResponse:
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


class Transport(Protocol):
    def post(self, url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> TransportResponse: ...


class HttpxTransport:
    """The real transport. Verifying TLS, no redirects, a hard timeout, a capped response."""

    def post(self, url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> TransportResponse:
        import httpx

        from caterva.tls import client_context

        local = urlsplit(url).hostname in LOOPBACK
        try:
            with httpx.Client(verify=client_context(), timeout=timeout, follow_redirects=False,
                              trust_env=not local) as client:
                response = client.post(url, headers=dict(headers), content=body)
        except httpx.TimeoutException as exc:
            raise AssistantError("timeout", f"the assistant's provider did not answer within {int(timeout)} seconds"
                                 ) from exc
        except httpx.HTTPError as exc:
            raise AssistantError("network", f"the assistant's provider could not be reached ({type(exc).__name__})"
                                 ) from exc
        data = response.content[:MAX_RESPONSE_BYTES]
        return TransportResponse(response.status_code, data, {k.lower(): v for k, v in response.headers.items()})


@dataclass(frozen=True)
class BuiltRequest:
    url: str
    headers: Dict[str, str]            # never holds the credential
    body: bytes
    provider: str
    model: str

    @property
    def host(self) -> str:
        return urlsplit(self.url).hostname or ""


def validate_local_url(url: str) -> str:
    """A loopback http(s) chat-completions URL, or AssistantError."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.hostname not in LOOPBACK or parts.username or parts.password:
        raise AssistantError("config", "a model on this computer must be at a loopback address such as "
                                       "http://127.0.0.1:11434/v1/chat/completions", status=400)
    return url


def build_request(provider: str, model: str, system: str, user: str, *, max_tokens: int,
                  local_url: Optional[str] = None) -> BuiltRequest:
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise AssistantError("config", f"{provider!r} is not a provider the studio offers", status=400)
    if not model or not model.strip():
        raise AssistantError("config", "choose a model name in Settings first", status=400)
    max_tokens = max(16, min(int(max_tokens), HARD_MAX_TOKENS))
    url = validate_local_url(local_url) if (spec.local and local_url) else spec.base_url
    if spec.wire == "anthropic":
        payload: Dict[str, Any] = {"model": model, "max_tokens": max_tokens, "system": system,
                                   "messages": [{"role": "user", "content": user}]}
        headers = {"content-type": "application/json", "anthropic-version": ANTHROPIC_VERSION}
    else:
        payload = {"model": model, spec.max_tokens_field: max_tokens,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        headers = {"content-type": "application/json"}
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return BuiltRequest(url, headers, body, provider, model)


def _credential_headers(spec: ProviderSpec, key: Optional[str]) -> Dict[str, str]:
    if not spec.needs_key or not key:
        return {}
    return {"x-api-key": key} if spec.wire == "anthropic" else {"authorization": f"Bearer {key}"}


def parse_reply(spec: ProviderSpec, body: bytes) -> Tuple[str, Dict[str, Any]]:
    """(text, usage) from a provider's JSON reply, or AssistantError."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise AssistantError("bad_response", "the assistant's provider sent something that is not JSON") from None
    try:
        if spec.wire == "anthropic":
            blocks = data["content"]
            text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
            usage = data.get("usage") or {}
        else:
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
    except (KeyError, IndexError, TypeError, AttributeError):
        raise AssistantError("bad_response", "the assistant's provider answered in a shape the studio does not read"
                             ) from None
    if not isinstance(text, str) or not text.strip():
        raise AssistantError("bad_response", "the assistant's provider sent an empty answer")
    return text, {k: v for k, v in usage.items() if isinstance(v, int)}


def _error_for(status: int, body: bytes, secrets: Sequence[str], headers: Mapping[str, str]) -> AssistantError:
    detail = ""
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
        err = data.get("error") if isinstance(data, dict) else None
        detail = err.get("message") if isinstance(err, dict) else (err if isinstance(err, str) else "")
    except ValueError:
        detail = ""
    detail = scrub(str(detail or ""), secrets)[:200]
    suffix = f": {detail}" if detail else ""
    if status in (401, 403):
        return AssistantError("auth", "the provider did not accept the key (check it in Settings)" + suffix, status=502)
    if status == 404:
        return AssistantError("model", "the provider has no such model or address; check the model name" + suffix,
                              status=502)
    if status == 429:
        retry = headers.get("retry-after", "")
        return AssistantError("rate_limit", "the provider is rate limiting this key; try again shortly" + suffix,
                              status=503, retry_after_s=int(retry) if retry.isdigit() else 30)
    if status >= 500:
        return AssistantError("provider", f"the provider had a problem on its side (HTTP {status})" + suffix)
    return AssistantError("rejected", f"the provider refused the request (HTTP {status})" + suffix, status=502)


class Provider:
    """One configured provider: builds, sends with retries, and reads the reply."""

    def __init__(self, provider: str, model: str, *, transport: Transport, key: Optional[str] = None,
                 local_url: Optional[str] = None, timeout_s: float = DEFAULT_TIMEOUT_S,
                 sleep: Callable[[float], None] = time.sleep, attempts: int = MAX_ATTEMPTS,
                 count_attempt: Optional[Callable[[], None]] = None) -> None:
        self.spec = PROVIDERS[provider]
        self.model = model
        self.transport = transport
        self._key = key
        self.local_url = local_url
        self.timeout_s = timeout_s
        self.sleep = sleep
        self.attempts = attempts
        self.count_attempt = count_attempt

    def _secrets(self) -> List[str]:
        return [self._key] if self._key else []

    def send(self, request: BuiltRequest, cancelled: Callable[[], bool] = lambda: False) -> Tuple[str, Dict[str, Any], int]:
        """(text, usage, attempts made). Retries 429, 5xx and connection failures with backoff."""
        if self.spec.needs_key and not self._key:
            raise AssistantError("no_key", "no key is set for this provider", status=409)
        headers = {**request.headers, **_credential_headers(self.spec, self._key)}
        last: Optional[AssistantError] = None
        for attempt in range(1, self.attempts + 1):
            if cancelled():
                raise AssistantError("cancelled", "cancelled", status=409)
            if self.count_attempt:
                self.count_attempt()
            try:
                response = self.transport.post(request.url, headers, request.body, self.timeout_s)
            except AssistantError as exc:
                last = AssistantError(exc.code, scrub(exc.message, self._secrets()), status=exc.status)
            except Exception as exc:  # noqa: BLE001 - a transport bug must not leak a key through str(exc)
                last = AssistantError("network", scrub(f"the assistant's provider could not be reached "
                                                       f"({type(exc).__name__})", self._secrets()))
            else:
                if 200 <= response.status < 300:
                    text, usage = parse_reply(self.spec, response.body)
                    return text, usage, attempt
                last = _error_for(response.status, response.body, self._secrets(), response.headers)
                if response.status not in (408, 429) and response.status < 500:
                    raise last
            if attempt < self.attempts and last.code in ("network", "timeout", "rate_limit", "provider"):
                self.sleep(min(8.0, 0.5 * (2 ** (attempt - 1))))
                continue
            break
        assert last is not None
        raise last


__all__ = ["AssistantError", "BuiltRequest", "DEFAULT_MODELS", "HttpxTransport", "PROVIDERS", "Provider",
           "ProviderSpec", "Transport", "TransportResponse", "build_request", "parse_reply", "validate_local_url"]
