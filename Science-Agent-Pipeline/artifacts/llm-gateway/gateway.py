"""One call through the waterfall, and the two ways to make it.

WHAT THIS FILE IS
-----------------
`quota.py` decides WHO to ask. This decides how the asking happens, and it is
deliberately thin: a loop that takes the next provider from the ledger, sends
one request, records what came back, and only THEN asks the ledger again.

The order of those last two steps is the entire mechanism. Recording after the
hop is chosen would pick the next provider from a ledger that had not yet heard
about the 429 -- so the 429'd provider could be chosen again, and the reset time
the provider just handed us would be written into state nobody consulted. That
is not a subtle bug; it is the waterfall not working. So `complete()` records
first and re-derives the order from the ledger on every hop, rather than
iterating a list computed once at the top.

TWO TRANSPORTS, ONE LOOP
------------------------
The loop is transport-agnostic, and that is the design:

    urllib_transport    stdlib only. POSTs an OpenAI-compatible
                        /chat/completions and hands back (status, headers,
                        body). No third-party package at all.

    litellm_transport   the same shape, through litellm.completion(), for
                        installations that already have it.

litellm is a large dependency and the gateway should not be the only way to get
fallback across five accounts, so the DEFAULT is the stdlib one. A test can
pass any callable with the same shape, which is why the loop is tested exactly
and neither transport has to be mocked at the socket level.

Note what `complete()` deliberately does NOT do: hand the whole waterfall to
`litellm.Router` and let it fall back internally. Router's fallback swallows the
intermediate responses, and those responses are where the rate-limit headers
are. The ledger would learn nothing from a chain that fired three deep, which
means the NEXT call would start from the same stale order. One provider per
transport call, recorded, is what keeps the ledger honest. `build_router()`
exists for callers who want litellm to own the chain anyway, and it says what
that costs.

WHERE ENDPOINTS COME FROM, AND WHY NOT FROM HERE
------------------------------------------------
The direct path needs a base URL per provider. This file contains none.

Not out of pedantry. A base URL written from memory is a host that a
researcher's unpublished query gets POSTed to, with a live API key in the
Authorization header, on the strength of an author's recollection. Wrong URLs
mostly 404, but the failure mode that matters is the one that does not: a
plausible-looking host that is not the provider's. So endpoints are DECLARED,
in exactly two places the operator controls:

    1. `<PROVIDER>_API_BASE` in the environment -- GROQ_API_BASE,
       OPENROUTER_API_BASE, MISTRAL_API_BASE, SILICONFLOW_API_BASE,
       TOKENROUTER_API_BASE.
    2. `litellm_params.api_base` in config.yaml, when the caller passes a
       loaded config. config.yaml already declares two of the five.

A provider with neither is SKIPPED by the direct path, with its variable name
in the message -- never guessed at. The third way to get a call through is to
install litellm, which carries its own table of provider base URLs; the refusal
says so. This is the same judgement `quota.py` makes about header names: where
the documentation was not read, the honest state is "not known", and a
confident guess is worse than an explicit gap.

WHAT THIS GATEWAY IS ALLOWED TO DECIDE
--------------------------------------
Entity extraction and domain classification. Nothing else.

ADR 0011 ("An LLM-supplied parameter is its own origin, not a `default`",
amended 2026-08-06) hard-blocks parameters whose origin is a language model:
`unverifiedOriginKeys()` treats them like a missing value and the resolver
throws before the engine sees one. A Km that came out of a prompt is not a
measurement, and this file does not become a way around that. There is no
number-extraction helper here, no parameter origin minted here, and adding a
provider does not widen what a model is allowed to decide. Text comes back;
what a caller may do with it is ADR 0011's business, not this module's.

WHAT IS TESTED AND WHAT IS NOT
------------------------------
`test_gateway.py` drives the loop with an injected transport: the ordering, the
recording, the persistence, the refusal and the redaction are all exercised
without a network and without litellm. Neither real transport has ever
completed a request from the sandbox this was written in -- litellm is not
installed there and PyPI is unreachable -- so `litellm_transport` in particular
is unexercised adapter code and is marked as such at its definition. Treat the
first real run as the test it has not had.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple,
)

from quota import (
    AVAILABLE, PROVIDERS, UNKNOWN, Ledger, Provider, Standing,
)

# ---------------------------------------------------------------------------
# Where things live
# ---------------------------------------------------------------------------

#: The proxy config this gateway reads when asked to read one. Same file the
#: proxy itself is started with, so the two cannot describe different
#: deployments.
DEFAULT_CONFIG_PATH = Path(__file__).resolve().with_name("config.yaml")

#: Overrides the ledger location. The ledger is a runtime cache, so it does
#: NOT default into this directory: a generated file in a tracked tree becomes
#: a committed file, and `.gitignore` in this repository is mostly a record of
#: that happening.
LEDGER_PATH_ENV_VAR = "CATERVA_LLM_QUOTA_LEDGER"

#: The standard OpenAI-compatible path, appended to whatever base the operator
#: declared. This is the one piece of a URL this file states, and it is the
#: same for every provider in `config.yaml` because they are all
#: OpenAI-compatible -- that is why the proxy can front them at all.
CHAT_COMPLETIONS_PATH = "/chat/completions"

#: Read from `litellm_settings.request_timeout` when a config is supplied; this
#: is the fallback when one is not.
#:
#: A STATED CHOICE, and the only number in this file that is one. UNKNOWN is
#: not available here: `urlopen` with no timeout blocks forever, and a hung
#: extraction is worse than a slow one. 30s matches what config.yaml declares
#: at the time of writing, and a config that says otherwise wins.
FALLBACK_TIMEOUT_SECONDS = 30.0

#: What a redacted secret is replaced with.
REDACTED = "<redacted>"

#: Below this length a value is not distinctive enough to substitute out of a
#: message -- replacing every occurrence of a 3-character string would mangle
#: ordinary prose -- and a key that short is not a key. Values shorter than
#: this are not treated as secrets, which is stated here rather than hidden so
#: that nobody assumes redaction is unconditional.
MIN_REDACTABLE_SECRET = 8


class GatewayError(RuntimeError):
    """The gateway could not make the call. Never carries a key value."""


class LiteLLMUnavailable(GatewayError):
    """litellm was asked for and is not installed."""


class ConfigUnavailable(GatewayError):
    """config.yaml could not be read. Not fatal: endpoints can be declared in
    the environment instead, and `complete()` reads no file unless asked."""


class EveryProviderExhausted(GatewayError):
    """Nothing in the waterfall could serve the call.

    Carries `Ledger.summary()` so the operator sees which provider comes back
    first rather than being told only that something failed.
    """

    def __init__(self, message: str, *, summary: str, attempts: Sequence["Attempt"] = ()) -> None:
        super().__init__(message)
        self.summary = summary
        self.attempts = tuple(attempts)


# ---------------------------------------------------------------------------
# Redaction: the safeguard, not a formality
# ---------------------------------------------------------------------------


def redact_secrets(text: Any, secrets: Iterable[str]) -> str:
    """`text` with every secret value substituted out.

    WHY THIS IS NOT PARANOIA. Providers put keys in places that end up in
    error text. A urllib `URLError` repr can carry the request it failed on; a
    provider that accepts its key as a query parameter puts the key in the URL;
    an upstream client library is free to include whatever it likes in an
    exception message. This module re-raises none of that verbatim -- every
    string built from outside text goes through here first, so the invariant is
    "a key never appears in an exception this module raises" rather than "no
    code path I thought of puts one there".

    Longest first, so a key that contains another key's value as a prefix does
    not leave a fragment behind.
    """
    result = str(text)
    candidates = {
        stripped for stripped in (str(value).strip() for value in secrets)
        if len(stripped) >= MIN_REDACTABLE_SECRET
    }
    for secret in sorted(candidates, key=len, reverse=True):
        result = result.replace(secret, REDACTED)
    return result


def _secret_values(environ: Mapping[str, str], *extra: Optional[str]) -> Tuple[str, ...]:
    """Every value that must never be printed.

    Every provider key in the environment, plus the proxy's own master key,
    plus anything the caller handed in directly. Collected from the
    environment rather than from a list of names written here, so a key set
    for a provider this module does not know about is still redacted.
    """
    values: List[str] = [str(value) for value in extra if value]
    for provider in PROVIDERS:
        values.append(str(environ.get(provider.key_env_var, "")))
    values.append(str(environ.get("LITELLM_MASTER_KEY", "")))
    return tuple(value for value in values if value.strip())


# ---------------------------------------------------------------------------
# config.yaml
# ---------------------------------------------------------------------------


def load_config(path: Optional[Any] = None) -> Dict[str, Any]:
    """The proxy config, as a dict.

    PyYAML is imported here rather than at module scope because it is a DEV
    dependency in this repository (requirements-dev.txt), not a runtime one.
    The direct path does not need this file at all -- endpoints can be declared
    in the environment -- so a missing parser must not cost the gateway its
    ability to make a call.
    """
    target = DEFAULT_CONFIG_PATH if path is None else Path(str(path))
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover -- PyYAML is installed here
        raise ConfigUnavailable(
            "reading config.yaml needs PyYAML, which is not installed.\n"
            "  pip install 'PyYAML==6.0.3'   (already in requirements-dev.txt)\n"
            "Or skip the file: declare each endpoint in <PROVIDER>_API_BASE "
            "and the direct path needs no parser."
        ) from exc
    if not target.exists():
        raise ConfigUnavailable(f"no config file at {target}")
    try:
        # safe_load, never load: this file is tracked and reviewed, but a
        # loader that can construct arbitrary Python objects from YAML is not
        # something to point at a path a caller supplies.
        blob = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigUnavailable(f"{target} could not be parsed: {exc}") from exc
    if not isinstance(blob, Mapping):
        raise ConfigUnavailable(
            f"{target} does not contain a YAML mapping, so it has no model_list"
        )
    return dict(blob)


def try_load_config(path: Optional[Any] = None) -> Tuple[Optional[Dict[str, Any]], str]:
    """`(config, note)`. The note explains an absent config instead of raising.

    `complete()` reads NO file unless a caller passes one, so this exists for
    callers that want the file when it is there and want to carry on when it is
    not. The note is not discarded: it travels on the `Completion` and into the
    refusal, because "siliconflow was skipped" and "siliconflow was skipped
    because config.yaml could not be read" are different problems.
    """
    try:
        return load_config(path), ""
    except ConfigUnavailable as exc:
        return None, f"config not loaded ({exc})"


def deployments(config: Mapping[str, Any]) -> List[Dict[str, Any]]:
    entries = config.get("model_list")
    if not isinstance(entries, (list, tuple)):
        return []
    return [dict(entry) for entry in entries if isinstance(entry, Mapping)]


def provider_for_deployment(deployment: Mapping[str, Any]) -> Optional[str]:
    """Which of our providers a config deployment is, or None.

    Matched on the API-KEY ENVIRONMENT VARIABLE first, because that is
    unambiguous: each provider in `quota.py` owns exactly one variable name,
    and `config.yaml` is required elsewhere to reference keys as
    `os.environ/NAME`. The model id is the fallback, and it is a weaker signal
    -- two deployments can share `openai/...` and be different hosts.
    """
    params = deployment.get("litellm_params")
    if not isinstance(params, Mapping):
        return None

    reference = str(params.get("api_key", "")).strip()
    prefix = "os.environ/"
    if reference.startswith(prefix):
        variable = reference[len(prefix):].strip()
        for provider in PROVIDERS:
            if provider.key_env_var == variable:
                return provider.name

    model = str(params.get("model", "")).strip()
    if model:
        for provider in PROVIDERS:
            if provider.model == model:
                return provider.name
    return None


# ---------------------------------------------------------------------------
# Endpoints and model ids: declared by the operator, never invented here
# ---------------------------------------------------------------------------


def api_base_env_var(provider: Provider) -> str:
    return f"{provider.name.upper()}_API_BASE"


def model_env_var(provider: Provider) -> str:
    return f"{provider.name.upper()}_MODEL"


def endpoint_for(
    provider: Provider,
    *,
    config: Optional[Mapping[str, Any]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """The chat-completions URL for one provider, or None if nobody declared one.

    None is a real answer and the caller must treat it as one. Returning a
    guessed default here would be the single worst line in this file: it would
    send a key and a prompt to a host chosen by this module's author.
    """
    env = os.environ if environ is None else environ

    declared = str(env.get(api_base_env_var(provider), "")).strip()
    if not declared and config is not None:
        for deployment in deployments(config):
            if provider_for_deployment(deployment) != provider.name:
                continue
            params = deployment.get("litellm_params")
            if isinstance(params, Mapping):
                declared = str(params.get("api_base", "")).strip()
            if declared:
                break

    if not declared:
        return None
    base = declared.rstrip("/")
    if base.endswith(CHAT_COMPLETIONS_PATH):
        # An operator who declared the full endpoint rather than the base meant
        # the endpoint. Appending the path again would produce a 404 and a
        # confusing one.
        return base
    return base + CHAT_COMPLETIONS_PATH


def model_id_for(
    provider: Provider, *, environ: Optional[Mapping[str, str]] = None
) -> str:
    """The model id to put in the request body on the direct path.

    `Provider.model` is litellm-flavoured ("groq/llama-3.3-70b-versatile"); a
    provider's own OpenAI-compatible API wants the part after the routing
    prefix. Stripping the first segment is right for all five deployments in
    config.yaml and is not a universal rule, so `<PROVIDER>_MODEL` overrides it
    -- the operator can state the id rather than rely on a transformation.
    """
    env = os.environ if environ is None else environ
    declared = str(env.get(model_env_var(provider), "")).strip()
    if declared:
        return declared
    model = provider.model
    return model.split("/", 1)[1] if "/" in model else model


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------

#: What a transport is.
#:
#: Called with keywords only -- `provider`, `url`, `api_key`, `payload`,
#: `timeout` -- and returns `(status, headers, body)`. Accept `**_` so the loop
#: can pass something a given transport ignores.
#:
#: HEADERS ARE THE POINT. They go straight into the ledger, and the ordering is
#: only as good as what the transport preserved. A transport that drops them
#: leaves every provider UNKNOWN: honest, and visibly worse than one that keeps
#: them.
Transport = Callable[..., Tuple[int, Mapping[str, Any], Any]]


def urllib_transport(
    *,
    provider: Provider,
    url: str,
    api_key: str,
    payload: Mapping[str, Any],
    timeout: float,
    **_: Any,
) -> Tuple[int, Mapping[str, Any], Any]:
    """One POST, stdlib only.

    Small on purpose. It does not stream, does not retry, does not pool
    connections and does not know about any provider's extensions -- the loop
    above it handles failure, and a feature-complete client here would be a
    second HTTP library to maintain badly. What it does do is preserve the
    response headers on ERROR responses, which is the whole reason it exists:
    `HTTPError` is where a 429's `retry-after` and `x-ratelimit-*` live, and a
    transport that let it propagate would throw away exactly the numbers the
    ledger runs on.
    """
    from urllib import error, request

    body = json.dumps(dict(payload)).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        # Bearer, because every deployment in config.yaml is an
        # OpenAI-compatible endpoint and that is the scheme they document. A
        # provider needing something else is not supported here rather than
        # guessed at.
        "Authorization": f"Bearer {api_key}",
    }
    post = request.Request(url, data=body, method="POST", headers=headers)

    def parse(raw: bytes) -> Any:
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            # Not an answer, but the status and headers still are. Returning
            # them lets the ledger record the reset a 429 came with even when
            # the body is an HTML error page.
            return {}

    try:
        with request.urlopen(post, timeout=timeout) as response:
            status = int(getattr(response, "status", 0) or 0)
            return status, dict(response.headers.items()), parse(response.read())
    except error.HTTPError as exc:
        raw = b""
        try:
            raw = exc.read()
        except Exception:  # pragma: no cover -- a body we cannot read is fine
            pass
        return int(exc.code), dict(exc.headers.items() if exc.headers else {}), parse(raw)


def litellm_transport(
    *,
    provider: Provider,
    url: Optional[str] = None,
    api_key: str = "",
    payload: Mapping[str, Any],
    timeout: float,
    **_: Any,
) -> Tuple[int, Mapping[str, Any], Any]:
    """The same shape, through litellm, for ONE provider at a time.

    One provider at a time deliberately: litellm's own fallback would hide the
    intermediate responses, and those carry the rate-limit headers the ledger
    needs. The waterfall stays in `complete()`; litellm is only the wire.

    UNEXERCISED. litellm is not installed in the sandbox this was written in
    and PyPI is unreachable there, so no call has ever gone through this
    function. Header extraction probes several attribute names because
    litellm's placement has moved between versions; when none is present the
    ledger gets an empty mapping and the provider stays UNKNOWN -- which is the
    honest outcome, not a silent AVAILABLE.
    """
    litellm = _import_litellm()

    messages = list(payload.get("messages") or [])
    extras = {
        key: value for key, value in payload.items()
        if key not in ("messages", "model")
    }
    try:
        response = litellm.completion(
            model=provider.model,
            messages=messages,
            api_key=api_key or None,
            api_base=url or None,
            timeout=timeout,
            **extras,
        )
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        headers = _litellm_headers(getattr(exc, "response", None)) or _litellm_headers(exc)
        if status is None:
            raise
        return int(status), headers, {}

    body = response
    for method in ("model_dump", "dict", "json"):
        converter = getattr(response, method, None)
        if callable(converter):
            try:
                body = converter()
                break
            except Exception:  # pragma: no cover -- fall through to the object
                continue
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:  # pragma: no cover
            body = {}
    return 200, _litellm_headers(response), body


def _litellm_headers(source: Any) -> Dict[str, Any]:
    """Response headers out of whatever litellm handed back, or {}."""
    if source is None:
        return {}
    for attribute in ("_response_headers", "response_headers", "headers"):
        candidate = getattr(source, attribute, None)
        if isinstance(candidate, Mapping) and candidate:
            return dict(candidate)
    hidden = getattr(source, "_hidden_params", None)
    if isinstance(hidden, Mapping):
        for key in ("additional_headers", "response_headers", "headers"):
            candidate = hidden.get(key)
            if isinstance(candidate, Mapping) and candidate:
                return dict(candidate)
    return {}


def _import_litellm() -> Any:
    try:
        import litellm
    except ImportError as exc:
        raise LiteLLMUnavailable(
            "litellm is not installed, so this path is unavailable:\n"
            "  pip install 'litellm[proxy]'\n"
            "litellm is deliberately absent from requirements.txt -- nothing "
            "else in this repository needs it and the gateway is an optional "
            "deployment, not a dependency of the engine.\n"
            "The direct path needs no install: gateway.complete() defaults to "
            "a stdlib transport and only needs each provider's endpoint "
            "declared in <PROVIDER>_API_BASE."
        ) from exc
    return litellm


# ---------------------------------------------------------------------------
# One call
# ---------------------------------------------------------------------------

OK = "ok"
RATE_LIMITED = "rate_limited"
FAILED = "failed"
SKIPPED = "skipped"


@dataclass(frozen=True)
class Attempt:
    """One hop. `detail` has already been through `redact_secrets`."""

    provider: str
    outcome: str
    status: Optional[int] = None
    detail: str = ""

    def describe(self) -> str:
        text = f"{self.provider}: {self.outcome}"
        if self.status is not None:
            text += f" (HTTP {self.status})"
        return f"{text} -- {self.detail}" if self.detail else text


@dataclass(frozen=True)
class Completion:
    """What came back, and what it took to get it.

    Holds no key: the request headers are built inside the transport and are
    not carried out of it, so neither this object nor its repr can leak one.

    `text` is model output. It is for entity extraction and domain
    classification, and ADR 0011 hard-blocks a parameter value taken from it --
    see the module docstring. There is no helper here that turns this into a
    number, which is not an oversight.
    """

    provider: str
    model: str
    text: str
    status: int
    attempts: Tuple[Attempt, ...] = ()
    response: Any = None
    notes: Tuple[str, ...] = ()

    def describe(self) -> str:
        lines = [f"answered by {self.provider} ({self.model}), HTTP {self.status}"]
        lines += [f"  - {attempt.describe()}" for attempt in self.attempts]
        lines += [f"  note: {note}" for note in self.notes]
        return "\n".join(lines)


def default_ledger_path(environ: Optional[Mapping[str, str]] = None) -> Path:
    """Where the quota ledger lives when the caller does not say.

    Outside the repository, under the user cache directory. A daily cap has to
    survive a restart -- a provider that ran out at noon is still out at one --
    so in-memory is not good enough; and a runtime file written into a tracked
    directory eventually gets committed, which this repository has a history of
    and a .gitignore full of lessons about.
    """
    env = os.environ if environ is None else environ
    declared = str(env.get(LEDGER_PATH_ENV_VAR, "")).strip()
    if declared:
        return Path(declared).expanduser()
    cache = str(env.get("XDG_CACHE_HOME", "")).strip()
    root = Path(cache).expanduser() if cache else Path.home() / ".cache"
    return root / "caterva" / "llm-quota-ledger.json"


def response_text(body: Any) -> Optional[str]:
    """The assistant's text out of an OpenAI-compatible body, or None.

    None means "this was not an answer", and the caller treats it as a failure
    rather than returning an empty extraction: a 200 carrying no content is a
    provider that did not do the work, and passing "" up would surface later as
    a JSON parse error in the caller with no hint of where it came from.
    """
    if not isinstance(body, Mapping):
        return None
    choices = body.get("choices")
    if not isinstance(choices, (list, tuple)) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, Mapping):
        return None
    message = first.get("message")
    if isinstance(message, Mapping):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
    text = first.get("text")
    if isinstance(text, str) and text.strip():
        return text
    return None


def _timeout_from(config: Optional[Mapping[str, Any]]) -> float:
    if isinstance(config, Mapping):
        settings = config.get("litellm_settings")
        if isinstance(settings, Mapping):
            try:
                declared = float(settings["request_timeout"])
            except (KeyError, TypeError, ValueError):
                declared = 0.0
            if declared > 0:
                return declared
    return FALLBACK_TIMEOUT_SECONDS


def _validate_messages(messages: Any) -> List[Dict[str, Any]]:
    if not isinstance(messages, (list, tuple)) or not messages:
        raise GatewayError(
            "messages must be a non-empty sequence of "
            "{'role': ..., 'content': ...} mappings"
        )
    prepared: List[Dict[str, Any]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, Mapping) or "role" not in message:
            raise GatewayError(
                f"messages[{index}] is not a mapping with a 'role' key"
            )
        prepared.append(dict(message))
    return prepared


def _next_untried(
    ledger: Ledger, tried: Iterable[str], *, now: Optional[float]
) -> Optional[Standing]:
    """The best provider the ledger will still offer that we have not tried.

    Re-derived from the ledger on EVERY hop rather than iterated from a list
    computed once, so a reading recorded a moment ago is already in force. The
    `tried` set is what bounds the loop: a plain failure does not block a
    provider in the ledger (nor should it -- one bad response is not a dead
    provider), so without it a 500 could be retried forever.
    """
    already = set(tried)
    for standing in ledger.order(now=now):
        if standing.availability in (AVAILABLE, UNKNOWN) and standing.provider.name not in already:
            return standing
    return None


def _save(ledger: Ledger, notes: List[str], secrets: Sequence[str]) -> None:
    """Persist, and treat a write failure as degradation rather than as an error.

    A ledger we cannot write costs one wasted 429 per provider after a restart.
    Failing the call because a cache file could not be written would cost the
    call. `quota.py` makes the same judgement about a corrupt ledger, for the
    same reason.
    """
    try:
        ledger.save()
    except OSError as exc:
        note = redact_secrets(
            f"ledger not persisted ({type(exc).__name__}: {exc}); a restart "
            f"will relearn quota from response headers",
            secrets,
        )
        if note not in notes:
            notes.append(note)


def _exhausted(
    ledger: Ledger,
    *,
    attempts: Sequence[Attempt],
    notes: Sequence[str],
    now: Optional[float],
    secrets: Sequence[str],
) -> EveryProviderExhausted:
    """The refusal, with `Ledger.summary()` in it.

    The summary is the actionable part: it names every provider, its state, the
    reason, and how many seconds until the blocked ones come back. "The call
    failed" tells an operator to guess; this tells them whether to wait 40
    seconds or to go add a key.
    """
    summary = ledger.summary(now=now)
    skipped = [a for a in attempts if a.outcome == SKIPPED]

    if attempts and len(skipped) == len(attempts):
        headline = (
            "no provider in the waterfall has a declared endpoint, so no call "
            "was made. This module states no provider hostnames -- a base URL "
            "written from memory is a host your prompt and your key would be "
            "sent to on somebody's recollection."
        )
    elif attempts:
        headline = (
            f"the waterfall ran out: {len(attempts)} provider(s) were tried "
            f"and none answered."
        )
    else:
        headline = (
            "no provider in the waterfall is available, so the call was not "
            "attempted."
        )

    lines = [headline, "", summary]

    if attempts:
        lines += ["", "This call tried, in order:"]
        lines += [f"  - {attempt.describe()}" for attempt in attempts]

    soonest = _soonest_back(ledger, now=now)
    if soonest is not None:
        name, seconds = soonest
        lines.append(
            f"Soonest back: {name}, in about {seconds:.0f}s, per the reset "
            f"that provider itself reported."
        )

    lines += [
        "",
        "How to get a call through:",
        "  - wait for the soonest reset above, or add another provider's key;",
        f"  - declare the endpoint the direct path is missing: "
        f"{', '.join(api_base_env_var(p) for p in PROVIDERS)} -- or pass "
        f"config=load_config() to use the api_base values config.yaml already "
        f"declares;",
        "  - or install litellm, which carries its own table of provider base "
        "URLs, and pass transport=litellm_transport:\n"
        "      pip install 'litellm[proxy]'",
    ]
    lines += [f"  note: {note}" for note in notes]

    message = redact_secrets("\n".join(lines), secrets)
    return EveryProviderExhausted(
        message, summary=redact_secrets(summary, secrets), attempts=attempts
    )


def _soonest_back(
    ledger: Ledger, *, now: Optional[float]
) -> Optional[Tuple[str, float]]:
    moment = time.time() if now is None else now
    soonest: Optional[Tuple[str, float]] = None
    for standing in ledger.order(now=now):
        until = standing.blocked_until
        if until is None:
            continue
        seconds = max(until - moment, 0.0)
        if soonest is None or seconds < soonest[1]:
            soonest = (standing.provider.name, seconds)
    return soonest


def complete(
    messages: Sequence[Mapping[str, Any]],
    *,
    ledger: Optional[Ledger] = None,
    transport: Optional[Transport] = None,
    config: Optional[Mapping[str, Any]] = None,
    environ: Optional[Mapping[str, str]] = None,
    timeout: Optional[float] = None,
    extra_body: Optional[Mapping[str, Any]] = None,
    model_overrides: Optional[Mapping[str, str]] = None,
    now: Optional[float] = None,
) -> Completion:
    """One completion through the waterfall. The loop that makes it work.

    Per hop, in this order and no other:

        1. ask the ledger for the best provider not yet tried on this call;
        2. send one request to it;
        3. RECORD the outcome from the response headers, and persist;
        4. go back to 1, which now sees what step 3 wrote.

    Step 3 before step 4 is the point. A loop that chose the next provider from
    an order computed at the top would re-offer the provider that just returned
    429, and would leave the reset time that provider handed us in a reading
    nobody consulted. The ledger is re-read every hop for that reason.

    No sampling parameters are set here. `temperature`, `max_tokens` and the
    rest are the caller's to send through `extra_body`; a default written here
    would change every caller's results silently.

    Reads no file. `config` is used when a caller passes one -- for the
    `api_base` values config.yaml declares -- and is not loaded behind the
    caller's back, because an implicit file read deciding where a researcher's
    query gets POSTed is not a surprise this module should have.
    """
    env = os.environ if environ is None else environ
    prepared = _validate_messages(messages)
    book = (
        Ledger(path=default_ledger_path(env), environ=env)
        if ledger is None else ledger
    )
    send: Transport = urllib_transport if transport is None else transport
    seconds = _timeout_from(config) if timeout is None else float(timeout)

    attempts: List[Attempt] = []
    notes: List[str] = []
    tried: List[str] = []
    base_secrets = _secret_values(env)

    while True:
        moment = time.time() if now is None else now
        standing = _next_untried(book, tried, now=moment)
        if standing is None:
            raise _exhausted(
                book, attempts=attempts, notes=notes, now=moment,
                secrets=base_secrets,
            )

        provider = standing.provider
        tried.append(provider.name)

        url = endpoint_for(provider, config=config, environ=env)
        if url is None:
            # NOT recorded in the ledger. Nothing was asked, so nothing was
            # learned about this provider's quota -- writing a failure here
            # would block a provider for a reason that has nothing to do with
            # it. Same distinction quota.py draws with ABSENT.
            attempts.append(Attempt(
                provider.name, SKIPPED,
                detail=(
                    f"no endpoint declared; set {api_base_env_var(provider)} "
                    f"or pass a config whose deployment for {provider.name} "
                    f"has an api_base"
                ),
            ))
            continue

        api_key = str(env.get(provider.key_env_var, "")).strip()
        secrets = (*base_secrets, api_key)
        model = (model_overrides or {}).get(provider.name) or model_id_for(
            provider, environ=env
        )
        payload: Dict[str, Any] = {
            "model": model,
            "messages": prepared,
            **dict(extra_body or {}),
        }

        try:
            status, headers, body = send(
                provider=provider,
                url=url,
                api_key=api_key,
                payload=payload,
                timeout=seconds,
            )
        except Exception as exc:
            # RECORD FIRST, before the next provider is chosen -- and record it
            # with no status, because a transport that raised did not come back
            # with one. `ok=False` sends it down quota.py's failure path rather
            # than its rate-limit path, which is right: a connection that never
            # landed said nothing about quota.
            book.record(provider.name, headers={}, status=None, ok=False, now=moment)
            _save(book, notes, secrets)
            attempts.append(Attempt(
                provider.name, FAILED,
                detail=redact_secrets(f"{type(exc).__name__}: {exc}", secrets),
            ))
            continue

        status = int(status)
        text = response_text(body)
        answered = status < 400 and text is not None

        # One record per hop, with the outcome already decided, so `calls` is
        # not double-counted and a 200 that carried no answer is recorded as
        # the failure it is rather than as a success.
        reading = book.record(
            provider.name,
            headers=headers or {},
            status=status,
            ok=answered,
            now=moment,
        )
        _save(book, notes, secrets)

        if answered:
            attempts.append(Attempt(provider.name, OK, status=status))
            return Completion(
                provider=provider.name,
                model=model,
                text=text or "",
                status=status,
                attempts=tuple(attempts),
                response=body,
                notes=tuple(notes),
            )

        if status == 429 or reading.rate_limited:
            until = reading.available_again_at()
            detail = (
                f"rate limited; provider reports it is back in "
                f"{max(until - moment, 0):.0f}s"
                if until is not None else
                "rate limited and reported no reset time"
            )
            attempts.append(Attempt(provider.name, RATE_LIMITED, status=status, detail=detail))
            continue

        attempts.append(Attempt(
            provider.name, FAILED, status=status,
            detail=(
                "HTTP error" if status >= 400 else
                "answered with no message content, which is not an extraction"
            ),
        ))


# ---------------------------------------------------------------------------
# The litellm router
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouterPlan:
    """What a Router should be built out of, computed WITHOUT litellm.

    Split out so the interesting half is testable: which deployments, in which
    order, under which names, and which were dropped and why. Constructing the
    Router from this is four lines and needs the package; deciding it is pure
    Python and does not.
    """

    primary_model_name: str
    chain: Tuple[str, ...]
    model_list: Tuple[Dict[str, Any], ...]
    fallbacks: Tuple[Dict[str, List[str]], ...]
    dropped: Tuple[str, ...]
    notes: Tuple[str, ...]
    router_kwargs: Dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        lines = [
            f"primary model_name: {self.primary_model_name}",
            "measured order: " + " -> ".join(self.chain),
        ]
        lines += [f"  dropped: {reason}" for reason in self.dropped]
        lines += [f"  note: {note}" for note in self.notes]
        return "\n".join(lines)


def alias_for(primary: str, provider_name: str) -> str:
    return f"{primary}-via-{provider_name}"


def plan_router(
    config: Mapping[str, Any],
    *,
    ledger: Optional[Ledger] = None,
    environ: Optional[Mapping[str, str]] = None,
    model_name: Optional[str] = None,
    now: Optional[float] = None,
) -> RouterPlan:
    """Order config.yaml's deployments by the live order `quota.py` computes.

    HOW THE ORDER IS MADE TO STICK. litellm picks among the deployments sharing
    a `model_name` by its routing strategy, and config.yaml sets
    `simple-shuffle` -- which is the right default for the proxy and would
    shuffle away any order this function put in `model_list`. So each provider
    gets its OWN model_name here (`caterva-extract-via-groq`, ...), the head of
    the measured chain keeps the name the application asks for, and an explicit
    `fallbacks` list chains them in measured order. Every group then holds one
    deployment, there is nothing left to shuffle, and the order is the measured
    one rather than the file's.

    Exhausted and unconfigured providers are dropped, with the reason kept in
    `dropped`. That follows `quota.py.chain()`: litellm would try them, and a
    call already known to 429 costs a round trip and a retry budget.
    """
    entries = deployments(config)
    if not entries:
        raise ConfigUnavailable("config has an empty model_list; nothing to route")

    env = os.environ if environ is None else environ
    book = (
        Ledger(path=default_ledger_path(env), environ=env)
        if ledger is None else ledger
    )
    standings = {s.provider.name: s for s in book.order(now=now)}
    chain = tuple(book.chain(now=now))

    primary = model_name or str(entries[0].get("model_name", "")).strip()
    if not primary:
        raise ConfigUnavailable(
            "the first deployment in model_list has no model_name, so there is "
            "no name for the application to ask for"
        )

    by_provider: Dict[str, List[Dict[str, Any]]] = {}
    unmatched: List[Dict[str, Any]] = []
    for entry in entries:
        name = provider_for_deployment(entry)
        if name is None:
            unmatched.append(entry)
        else:
            by_provider.setdefault(name, []).append(entry)

    notes: List[str] = []
    dropped: List[str] = []
    for name, standing in standings.items():
        if name in chain:
            continue
        if name in by_provider:
            dropped.append(f"{name} ({standing.availability}): {standing.reason}")

    if not chain:
        raise _exhausted(
            book, attempts=(), notes=notes, now=now,
            secrets=_secret_values(env),
        )

    ordered: List[Dict[str, Any]] = []
    names: List[str] = []
    for position, provider_name in enumerate(chain):
        for index, entry in enumerate(by_provider.get(provider_name, [])):
            deployment = dict(entry)
            if position == 0 and index == 0:
                deployment["model_name"] = primary
            else:
                candidate = alias_for(primary, provider_name)
                if index:
                    candidate = f"{candidate}-{index + 1}"
                deployment["model_name"] = candidate
            ordered.append(deployment)
            names.append(deployment["model_name"])

    if not ordered:
        raise ConfigUnavailable(
            "no deployment in model_list matches a provider the ledger knows, "
            "so the measured order cannot be applied. Deployments are matched "
            "on their os.environ/NAME api_key reference; check that each one "
            "names the variable quota.py expects."
        )

    for index, entry in enumerate(unmatched):
        deployment = dict(entry)
        deployment["model_name"] = f"{primary}-unmeasured-{index + 1}"
        ordered.append(deployment)
        names.append(deployment["model_name"])
        notes.append(
            f"model_list entry {entry.get('model_name', '?')!r} matches no "
            f"provider in quota.py, so its headroom is not measured and it is "
            f"chained last as {deployment['model_name']}. It is kept rather "
            f"than dropped: an operator's deployment is not this function's to "
            f"delete."
        )

    fallbacks: Tuple[Dict[str, List[str]], ...] = ()
    if len(names) > 1:
        fallbacks = ({primary: list(names[1:])},)

    settings = config.get("litellm_settings")
    settings = dict(settings) if isinstance(settings, Mapping) else {}
    router_settings = config.get("router_settings")
    router_settings = dict(router_settings) if isinstance(router_settings, Mapping) else {}

    kwargs: Dict[str, Any] = {}
    for source, key, target in (
        (settings, "num_retries", "num_retries"),
        (settings, "allowed_fails", "allowed_fails"),
        (settings, "cooldown_time", "cooldown_time"),
        (settings, "request_timeout", "timeout"),
        (router_settings, "routing_strategy", "routing_strategy"),
        (router_settings, "enable_pre_call_checks", "enable_pre_call_checks"),
    ):
        if key in source and source[key] is not None:
            kwargs[target] = source[key]

    if "retry_policy" in settings:
        notes.append(
            "config.yaml's retry_policy is NOT applied to this Router: litellm "
            "wants a RetryPolicy object there, not the mapping the file holds, "
            "and constructing one from an uninstalled package is not something "
            "to do speculatively. The proxy reading config.yaml directly does "
            "honour it. Said here rather than dropped silently."
        )

    return RouterPlan(
        primary_model_name=primary,
        chain=chain,
        model_list=tuple(ordered),
        fallbacks=fallbacks,
        dropped=tuple(dropped),
        notes=tuple(notes),
        router_kwargs=kwargs,
    )


def build_router(
    *,
    config: Optional[Mapping[str, Any]] = None,
    config_path: Optional[Any] = None,
    ledger: Optional[Ledger] = None,
    environ: Optional[Mapping[str, str]] = None,
    model_name: Optional[str] = None,
    now: Optional[float] = None,
    litellm_module: Optional[Any] = None,
) -> Any:
    """A `litellm.Router` over config.yaml's deployments in the MEASURED order.

    litellm first, before the config is even opened: an operator without the
    package should meet an install instruction, not a YAML error from a step
    that was never going to matter.

    The returned Router is a SNAPSHOT. It was ordered by what the providers had
    reported when it was built, and quota moves -- a Router held for an hour is
    ordered by an hour-old measurement. Rebuild it, or use `complete()`, which
    re-derives the order every hop. The plan is attached as `caterva_plan` so a
    caller can see what was decided and what was dropped.
    """
    litellm = _import_litellm() if litellm_module is None else litellm_module
    resolved = dict(config) if config is not None else load_config(config_path)
    plan = plan_router(
        resolved, ledger=ledger, environ=environ, model_name=model_name, now=now
    )

    kwargs: Dict[str, Any] = {
        "model_list": [dict(entry) for entry in plan.model_list],
    }
    if plan.fallbacks:
        kwargs["fallbacks"] = [dict(entry) for entry in plan.fallbacks]
    kwargs.update(plan.router_kwargs)

    router = litellm.Router(**kwargs)
    try:
        router.caterva_plan = plan
    except Exception:  # pragma: no cover -- a Router that refuses attributes
        pass
    return router


__all__ = [
    "CHAT_COMPLETIONS_PATH", "DEFAULT_CONFIG_PATH", "FALLBACK_TIMEOUT_SECONDS",
    "LEDGER_PATH_ENV_VAR", "MIN_REDACTABLE_SECRET", "REDACTED",
    "OK", "RATE_LIMITED", "FAILED", "SKIPPED",
    "Attempt", "Completion", "RouterPlan", "Transport",
    "GatewayError", "LiteLLMUnavailable", "ConfigUnavailable",
    "EveryProviderExhausted",
    "alias_for", "api_base_env_var", "build_router", "complete",
    "default_ledger_path", "deployments", "endpoint_for", "litellm_transport",
    "load_config", "model_env_var", "model_id_for", "plan_router",
    "provider_for_deployment", "redact_secrets", "response_text",
    "try_load_config", "urllib_transport",
]
