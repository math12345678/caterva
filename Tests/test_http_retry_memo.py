"""One answer per question, per process (http_retry._MEMO).

Traced 2026-09-29: one hexokinase lookup asked NCBI Taxonomy for "Homo
sapiens" four times and drew a 429. The memo hands back a definitive answer
to an identical request and never remembers a throttle or a server error.
"""
import httpx
import pytest

import http_retry


class _Resp:
    def __init__(self, status):
        self.status_code = status
        self.request = httpx.Request("GET", "https://example.test/")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=self.request, response=self)


@pytest.fixture
def calls(monkeypatch):
    http_retry.clear_memo()
    log = []
    statuses = {}

    def fake_get(url, **kw):
        log.append((url, kw.get("params")))
        return _Resp(statuses.get(url, 200))

    monkeypatch.setattr(http_retry.httpx, "get", fake_get)
    monkeypatch.setattr(http_retry.time, "sleep", lambda s: None)
    yield log, statuses
    http_retry.clear_memo()


def test_the_same_request_is_sent_once(calls):
    log, _ = calls
    a = http_retry.retry_get("https://ncbi.test/esearch", params={"term": "Homo sapiens"})
    b = http_retry.retry_get("https://ncbi.test/esearch", params={"term": "Homo sapiens"})
    assert a is b and len(log) == 1


def test_different_parameters_are_different_questions(calls):
    log, _ = calls
    http_retry.retry_get("https://ncbi.test/esearch", params={"term": "Homo sapiens"})
    http_retry.retry_get("https://ncbi.test/esearch", params={"term": "lymphocytes"})
    assert len(log) == 2


def test_a_not_found_is_an_answer_and_is_kept(calls):
    log, statuses = calls
    statuses["https://pubchem.test/x"] = 404
    http_retry.retry_get("https://pubchem.test/x")
    http_retry.retry_get("https://pubchem.test/x")
    assert len(log) == 1


@pytest.mark.parametrize("status", [429, 500, 503])
def test_a_throttle_or_server_error_is_never_remembered(calls, status):
    log, statuses = calls
    statuses["https://brenda.test/"] = status
    for _ in range(2):
        try:
            http_retry.retry_get("https://brenda.test/", max_retries=0)
        except httpx.HTTPStatusError:
            pass
    assert len(log) == 2, "a transient failure was served from memory"
