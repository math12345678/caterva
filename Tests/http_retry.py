"""
http_retry.py

Lightweight exponential-backoff retry wrapper for the httpx calls the
literature layer makes against public APIs (NCBI PubMed/Taxonomy, UniProt,
KEGG, BRENDA). These services throttle at different rates:

  - NCBI E-utilities:  3 req/s without an API key, 10 req/s with one.
    A 429 (Retry-After) is routine during a batch test run.
  - UniProt REST:      generous but not unlimited; bursts from parallel
    tests occasionally trigger 429s.
  - KEGG REST:         no published rate limit, but intermittent 502/503
    from their load balancer, especially from CI runners.
  - BRENDA:            no documented rate limit; 503 during maintenance
    windows, 429 very rarely.

Every caller that needs retries can import ``retry_get`` and use it as a
drop-in replacement for ``httpx.get``. The rest of the httpx API (params,
timeout, headers, follow_redirects, etc.) is passed through unchanged.

Usage:
    from http_retry import retry_get

    r = retry_get("https://eutils.ncbi.nlm.nih.gov/...", params={...}, timeout=15)
    r.raise_for_status()

Do NOT wrap calls in tests that supply a fixture-HTML provider --
``retry_get`` is meant for live network calls only, and the defaults
(3 retries, 1-4s backoff) assume a ~10-15s total window, which is fine
for a live API call but wasteful inside a unit test.

Two test-only environment variables change where an answer comes from
(see "Recorded answers" below and Tests/fixtures/recorded/README.md):
``CATERVA_HTTP_RECORDED`` replays recorded real responses, and
``CATERVA_HTTP_RECORD`` writes live ones down. The product sets neither;
Tests/test_recorded_env_is_test_only.py fails if anything outside test
configuration does.
"""

from __future__ import annotations

import base64
import datetime
import gzip
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

# Tuned for public free-tier APIs without API keys.
#  - max_retries=3 means at most 4 total attempts (original + 3 retries).
#  - base_delay=1.0 gives a 1s/2s/4s backoff sequence (<8s total wait).
# Together they fit inside BRENDA's 15s default timeout with room to spare.
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0

RETRYABLE_STATUSES = frozenset({429, 502, 503})

# ---------------------------------------------------------------------------
# One answer per question, per process
# ---------------------------------------------------------------------------
#
# Traced 2026-09-29 on one API lookup (hexokinase Km, human): 20 requests, of
# which NCBI Taxonomy was asked for "Homo sapiens" FOUR times and for
# "lymphocytes" three, and PubChem for the same compound names twice. The
# fourth taxonomy call drew a 429 and a 1 s backoff: NCBI allows 3 requests/s
# without a key, and the API test suite runs many of these processes at
# once, which is how the flagship hexokinase tests came to time out in CI
# three runs running.
#
# The same GET within one process gets the same answer: the runner is one
# process per lookup, `caterva compose` one per model, and neither lives long
# enough for BRENDA, NCBI or PubChem to change underneath it. So a response
# is kept for the life of the process and handed back to the next identical
# request. Only definitive answers are kept (anything below 500 except 429);
# a server error or a throttle is never remembered, so the next caller
# retries it for real.
MEMO_MAX = 512
_MEMO: dict = {}


def _memo_key(url: str, kwargs: dict) -> tuple:
    params = kwargs.get("params")
    if isinstance(params, dict):
        params = tuple(sorted((str(k), str(v)) for k, v in params.items()))
    headers = kwargs.get("headers")
    if isinstance(headers, dict):
        headers = tuple(sorted((str(k), str(v)) for k, v in headers.items()))
    return (url, repr(params), repr(headers), bool(kwargs.get("follow_redirects", False)))


def clear_memo() -> None:
    """Forget every remembered response (for tests that need a cold start)."""
    _MEMO.clear()


# ---------------------------------------------------------------------------
# Recorded answers, for the test suites that run the real resolver
# ---------------------------------------------------------------------------
#
# The API server's tests spawn the real science_agent_runner.py, unmocked,
# because the defects they guard live in the seam between the resolver and
# the engine. BRENDA pages were already replayed for them from
# Tests/fixtures/recorded/ (CATERVA_BRENDA_RECORDED, read in
# brenda_client.fetch_brenda_html). Everything else still went to the
# network. Recorded on 2026-09-30, one human hexokinase Km lookup made 15
# distinct requests even with the memo above: two NCBI Taxonomy esearches
# (the organism, and "lymphocytes" from a row's commentary), one UniProt
# search and twelve PubChem name-to-CID and parent-CID lookups. Those tests
# timed out in CI whenever NCBI or PubChem was slow. A test that
# fails on a slow third party reports the weather, and it teaches people to
# re-run a red build rather than read it.
#
# So a GET is answered from a recording when one exists for exactly that
# request, and goes live exactly as before when none does: the same policy
# as the BRENDA pages. A recording is a real response, written down by
# CATERVA_HTTP_RECORD during a real run (scripts/record_http_fixtures.py),
# never a hand-written stand-in, and it is replayed as a real
# httpx.Response so every caller's raise_for_status/json/text path runs
# unchanged.
#
# Only test configuration sets either variable. The product must always
# ask the database; a stale answer served to a user as current would be a
# worse defect than any timeout.
RECORDED_ENV = "CATERVA_HTTP_RECORDED"
RECORD_ENV = "CATERVA_HTTP_RECORD"

#: Query parameters that carry a credential. A request with any of these is
#: never written to disk and never answered from a recording, so a key can
#: neither leak into a committed file nor be silently dropped from a request
#: that was supposed to carry it.
#:
#: `api_key` is the one the literature layer really sends: NCBI's, attached by
#: enzyme_lookup._ncbi_params (Taxonomy esearch/efetch, and source_context's
#: and taxonomy.py's lookups through it) and by fallback_logic's PubMed
#: esearch/esummary whenever NCBI_API_KEY is set. The rest are the other
#: common spellings, listed so that the next API added to the literature
#: layer is excluded by default rather than by someone remembering.
CREDENTIAL_PARAMS = frozenset({
    "api_key", "apikey", "api-key", "key", "token", "access_token",
    "auth", "password", "secret",
})

#: Request headers that carry a credential, excluded for the same reason.
#:
#: `authorization` is the one really sent: CORE's `Authorization: Bearer
#: <CORE_API_KEY>` (core_fulltext.fetch_core_search). The Groq and other LLM
#: keys never pass through this module (the API server's llmResolver.ts
#: calls those providers itself, and the exploratory Tests/big_test*.py
#: scripts use the openai client), but any bearer token that ever does is
#: caught by the same header.
CREDENTIAL_HEADERS = frozenset({
    "authorization", "proxy-authorization", "x-api-key", "api-key", "cookie",
})

#: Request headers that describe the client or the connection rather than
#: the question, and so are left out of the key. Every OTHER header a caller
#: passes (Accept, Accept-Language, Range, ...) is part of the key: a header
#: nobody anticipated then makes a recording miss and the request go live,
#: which is the safe way to be wrong. The reverse (ignoring a header that
#: did change the answer) would replay a JSON body to a caller that asked
#: for XML.
IGNORED_HEADERS = frozenset({"user-agent", "accept-encoding", "connection"})


def _carries_a_credential(url: str, kwargs: dict) -> bool:
    """Whether this request holds a key, a token or a password anywhere."""
    if kwargs.get("auth") is not None or kwargs.get("cookies"):
        return True
    parsed = httpx.URL(url)
    if parsed.userinfo:
        return True
    names = {k.lower() for k, _ in parsed.params.multi_items()}
    names |= {k.lower() for k, _ in httpx.QueryParams(kwargs.get("params")).multi_items()}
    if names & CREDENTIAL_PARAMS:
        return True
    headers = httpx.Headers(kwargs.get("headers") or {})
    return any(name.lower() in CREDENTIAL_HEADERS for name in headers.keys())


def replay_key(url: str, kwargs: dict, method: str = "GET") -> dict | None:
    """The fields that decide the answer to a request, or None when the
    request carries a credential and so may be neither recorded nor replayed.

    Parameters are taken as httpx will send them (httpx.QueryParams, so 15
    and "15" are the same question, as they are on the wire) and sorted, so
    two callers building the same dict in a different order share one
    recording. `follow_redirects` is part of it because a 301 and the page
    it points to are different answers to the same URL.
    """
    if _carries_a_credential(url, kwargs):
        return None
    params = sorted(httpx.QueryParams(kwargs.get("params")).multi_items())
    headers = sorted(
        (name.lower(), value)
        for name, value in httpx.Headers(kwargs.get("headers") or {}).items()
        if name.lower() not in IGNORED_HEADERS
    )
    return {
        "method": method.upper(),
        "url": url,
        "params": [list(pair) for pair in params],
        "headers": [list(pair) for pair in headers],
        "follow_redirects": bool(kwargs.get("follow_redirects", False)),
    }


def recording_name(key: dict) -> str:
    """The file a request's recording lives in: the sha256 of its key."""
    canonical = json.dumps(key, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest() + ".json.gz"


def _replayed(key: dict) -> httpx.Response | None:
    """The recorded response for this key, when CATERVA_HTTP_RECORDED holds one.

    The stored key is compared with the computed one before anything is
    returned, so a renamed or hand-edited file cannot answer a question it
    was not recorded for; it is ignored and the request goes live.
    """
    directory = os.environ.get(RECORDED_ENV)
    if not directory:
        return None
    path = Path(directory) / recording_name(key)
    if not path.is_file():
        return None
    record = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    if record.get("key") != key:
        return None
    if "body_base64" in record:
        body = base64.b64decode(record["body_base64"])
    else:
        body = record["body"].encode("utf-8")
    headers = {"content-type": record["content_type"]} if record.get("content_type") else {}
    request = httpx.Request(key["method"], record.get("response_url") or key["url"])
    return httpx.Response(record["status"], headers=headers, content=body, request=request)


def _record(key: dict, response: httpx.Response) -> None:
    """Write a live response down when CATERVA_HTTP_RECORD names a directory.

    gzip with mtime=0, so recording the same answer twice produces the same
    bytes and a refresh that changed nothing shows no diff. Written to a
    temporary file and renamed, so a runner killed mid-write cannot leave a
    truncated recording for the next test run to choke on.
    """
    directory = os.environ.get(RECORD_ENV)
    if not directory:
        return
    content = response.content
    record: dict[str, Any] = {
        "key": key,
        "fetched": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "status": response.status_code,
        "content_type": response.headers.get("content-type"),
        "response_url": str(response.url),
    }
    try:
        record["body"] = content.decode("utf-8")
    except UnicodeDecodeError:
        record["body_base64"] = base64.b64encode(content).decode("ascii")
    data = gzip.compress(
        json.dumps(record, sort_keys=True, indent=1).encode("utf-8"), mtime=0,
    )
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=target, suffix=".partial")
    with os.fdopen(handle, "wb") as out:
        out.write(data)
    os.replace(temporary, target / recording_name(key))


def retry_get(
    url: str,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    **kwargs: Any,
) -> httpx.Response:
    """httpx.get with exponential backoff for transient server errors.

    Retries on 429 (Too Many Requests), 502 (Bad Gateway), and 503
    (Service Unavailable). Other status codes (including 4xx client errors
    that aren't 429) are returned immediately -- retrying a 404 or 400
    wastes everyone's time.

    Each retry waits ``base_delay * 2**attempt`` seconds, so the default
    sequence is 1s / 2s / 4s.

    Raises the last ``httpx.HTTPStatusError`` if all retries are exhausted.
    Other exceptions (timeout, connection error) are NOT retried --
    they indicate a different class of problem.

    Under CATERVA_HTTP_RECORDED a request with a recording is answered from
    it without touching the network; under CATERVA_HTTP_RECORD a definitive
    live answer is written down. Neither ever applies to a request that
    carries a credential (see CREDENTIAL_PARAMS / CREDENTIAL_HEADERS).
    """
    key = _memo_key(url, kwargs)
    if key in _MEMO:
        return _MEMO[key]

    # Neither variable set is the product's case, and there the key is not
    # even computed, so the live path does exactly what it did before
    # recordings existed.
    recorded_key = None
    if os.environ.get(RECORDED_ENV) or os.environ.get(RECORD_ENV):
        recorded_key = replay_key(url, kwargs)
    if recorded_key is not None:
        replayed = _replayed(recorded_key)
        if replayed is not None:
            if len(_MEMO) < MEMO_MAX:
                _MEMO[key] = replayed
            return replayed

    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            r = httpx.get(url, **kwargs)
            if r.status_code not in RETRYABLE_STATUSES:
                if r.status_code < 500:
                    if len(_MEMO) < MEMO_MAX:
                        _MEMO[key] = r
                    if recorded_key is not None:
                        _record(recorded_key, r)
                return r
            # 429/502/503: retryable server-side blip.
            last_exc = httpx.HTTPStatusError(
                f"Server error {r.status_code} for {url}",
                request=r.request,
                response=r,
            )
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                time.sleep(delay)
                continue
            # Exhausted retries — let the last error propagate naturally.
            r.raise_for_status()
        except httpx.ConnectError as exc:
            # Connection refused / DNS failure — transient, worth retrying.
            # httpx does NOT raise on 4xx/5xx by default (we handle those
            # above), so HTTPStatusError is never caught here.
            last_exc = exc
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                time.sleep(delay)
                continue
            raise

    # Should be unreachable (the loop always raises or returns), but
    # satisfy the type checker.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"retry_get exhausted all {max_retries + 1} attempts for {url}")
