"""CORE's rate-limit handling in verify_values_live.py -- checked offline.

WHY THIS EXISTS
---------------
The first version of the CORE check slept 6 s before every request and
honoured one 429 for at most 30 s, so a run that met CORE's free-tier limit
reported every remaining DOI unreachable and exited 1. `CoreClient` replaced
that with: wait for the advertised reset when X-RateLimit-Remaining reaches
0, retry a 429 after Retry-After / X-RateLimit-Retry-After (else exponential
backoff), and bound all waiting by CORE_WAIT_BUDGET_S.

That logic only ran against the live API, where a 429 is a matter of luck.
`CoreClient` takes `sleep` and `get` as parameters precisely so it can be
driven here with scripted responses and a recording sleep: no network, no
real waiting, and every wait asserted to the second.
"""

from __future__ import annotations

import datetime
import importlib.util
import pathlib
import sys

import httpx
import pytest

_SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "verify_values_live.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("verify_values_live", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_values_live"] = module
    spec.loader.exec_module(module)
    return module


live = _load()


def _resp(status: int, headers: dict | None = None, body: dict | None = None):
    return httpx.Response(
        status,
        headers=headers or {},
        json=body if body is not None else {"results": []},
        request=httpx.Request("GET", live.CORE_URL),
    )


class Scripted:
    """A `get` that answers from a list and a `sleep` that only records."""

    def __init__(self, *responses: httpx.Response):
        self.responses = list(responses)
        self.calls = 0
        self.slept: list[float] = []

    def get(self, url, **kwargs):
        self.calls += 1
        return self.responses.pop(0)

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    def client(self):
        return live.CoreClient("not-a-key", sleep=self.sleep, get=self.get)


def test_retry_after_delta_seconds_is_honoured_plus_one_second_slack():
    s = Scripted(_resp(429, {"Retry-After": "7"}), _resp(200, body={"results": [1]}))
    c = s.client()
    assert c.search("q") == {"results": [1]}
    assert s.slept == [8.0]
    assert c.waited == 8.0
    assert s.calls == 2


def test_x_ratelimit_retry_after_is_used_when_retry_after_is_absent():
    s = Scripted(_resp(429, {"X-RateLimit-Retry-After": "3"}), _resp(200))
    s.client().search("q")
    assert s.slept == [4.0]


def test_429_without_a_reset_hint_backs_off_exponentially():
    s = Scripted(_resp(429), _resp(429), _resp(200))
    s.client().search("q")
    base = live.CORE_BACKOFF_BASE_S
    assert s.slept == [base, base * 2]


def test_persistent_429_gives_up_after_max_attempts_and_raises():
    s = Scripted(*[_resp(429) for _ in range(live.CORE_MAX_ATTEMPTS)])
    c = s.client()
    with pytest.raises(httpx.HTTPError, match="429 after"):
        c.search("q")
    assert s.calls == live.CORE_MAX_ATTEMPTS
    # One wait between each pair of attempts, none after the last.
    assert len(s.slept) == live.CORE_MAX_ATTEMPTS - 1


def test_a_wait_larger_than_the_budget_is_refused_not_slept():
    too_long = str(int(live.CORE_WAIT_BUDGET_S) + 10)
    s = Scripted(_resp(429, {"Retry-After": too_long}), _resp(200))
    c = s.client()
    with pytest.raises(httpx.HTTPError):
        c.search("q")
    assert s.slept == []
    assert c.waited == 0.0
    assert s.calls == 1


def test_the_budget_is_shared_across_waits_not_per_wait():
    # Each wait fits the budget alone; two of them together do not.
    each = live.CORE_WAIT_BUDGET_S * 0.6
    hint = {"Retry-After": str(each - 1.0)}
    s = Scripted(_resp(429, hint), _resp(429, hint), _resp(200))
    c = s.client()
    with pytest.raises(httpx.HTTPError):
        c.search("q")
    assert s.slept == [each]
    assert c.waited <= live.CORE_WAIT_BUDGET_S
    assert s.calls == 2


def test_remaining_zero_paces_the_next_request_instead_of_spending_a_429():
    exhausted = {"X-RateLimit-Remaining": "0", "X-RateLimit-Retry-After": "20"}
    s = Scripted(_resp(200, exhausted), _resp(200))
    c = s.client()
    c.search("first")
    assert s.slept == []
    c.search("second")
    # 20 s advertised + 1 s slack, less the microseconds the test itself took.
    assert len(s.slept) == 1 and 20.0 < s.slept[0] <= 21.0
    assert s.calls == 2


def test_a_non_429_error_is_raised_not_retried():
    s = Scripted(_resp(500), _resp(200))
    with pytest.raises(httpx.HTTPStatusError):
        s.client().search("q")
    assert s.calls == 1
    assert s.slept == []


def test_core_iso_reset_timestamp_parses():
    # CORE writes its reset as an ISO timestamp with a "+0000" offset.
    now = datetime.datetime(2026, 10, 31, 12, 0, 0, tzinfo=datetime.timezone.utc)
    assert live._seconds_until("2026-10-31T12:00:10+0000", now.timestamp()) == 10.0
    assert live._seconds_until("Sat, 31 Oct 2026 12:00:30 GMT", now.timestamp()) == 30.0
    assert live._seconds_until("not a time", now.timestamp()) is None


def test_core_indexed_needs_the_exact_doi_and_distrusts_a_full_page():
    hit = _resp(200, body={"results": [{"doi": "10.1038/NG.3469"}, {"doi": "10.9/other"}]})
    s = Scripted(hit)
    out = live.core_indexed(["10.1038/ng.3469", "10.1/absent"], s.client())
    assert out == {"10.1038/ng.3469": True, "10.1/absent": False}

    full = _resp(200, body={"results": [{"doi": "10.9/x"}] * live.CORE_PAGE})
    s = Scripted(full)
    assert live.core_indexed(["10.1/absent"], s.client()) == {"10.1/absent": None}


def test_a_paced_wait_beyond_the_budget_raises_without_sending_the_request():
    # The pacing wait (Remaining: 0) is bounded by the same budget as a 429's.
    too_long = str(int(live.CORE_WAIT_BUDGET_S) + 10)
    exhausted = {"X-RateLimit-Remaining": "0", "X-RateLimit-Retry-After": too_long}
    s = Scripted(_resp(200, exhausted), _resp(200))
    c = s.client()
    c.search("first")
    with pytest.raises(httpx.HTTPError, match="budget"):
        c.search("second")
    assert s.slept == []
    assert s.calls == 1
