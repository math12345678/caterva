"""Recorded answers: http_retry's replay and record, and the runner run offline.

WHAT THIS PINS
--------------
The API server's tests run the real science_agent_runner.py, and every GET
it makes through http_retry.retry_get is now answered from
Tests/fixtures/recorded/http/ when CATERVA_HTTP_RECORDED names that
directory (see Tests/fixtures/recorded/README.md). Four things have to hold
for that to be worth anything:

1. A recorded request is answered with no network at all, as a real
   httpx.Response a caller cannot tell from a live one.
2. A request with no recording goes live exactly as before. A replay layer
   that failed closed would turn every new lookup into a test failure; one
   that answered from the nearest match would be worse.
3. A request that carries a key is never written down and never answered
   from disk. The recordings are committed to a public repository.
4. The whole runner, for the flagship hexokinase Km lookup, gives the same
   value, citation and taxon id offline as it gave live when recorded. Only
   the real runner shows that: a unit test of retry_get cannot see a
   request some module makes that nobody recorded.

Every body used below is a real response from the committed recordings,
not a hand-written stand-in.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

import http_retry

TESTS = Path(__file__).resolve().parent
RECORDED = TESTS / "fixtures" / "recorded"
HTTP_RECORDED = RECORDED / "http"
MANIFEST = json.loads((HTTP_RECORDED / "MANIFEST.json").read_text(encoding="utf-8"))

LIB_DIR = TESTS.parent / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib"

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
HUMAN_ESEARCH_PARAMS = {
    "db": "taxonomy", "term": "Homo sapiens[Scientific Name]", "retmode": "json",
}
PUBCHEM_HEXOKINASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/hexokinase/cids/JSON"


def _recording(url: str, params: dict | None = None) -> dict:
    """A committed recording, read the way retry_get finds it."""
    key = http_retry.replay_key(url, {"params": params} if params else {})
    path = HTTP_RECORDED / http_retry.recording_name(key)
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


def _live_response(url: str, params: dict | None, recording: dict) -> httpx.Response:
    """What httpx.get returned when this recording was made, rebuilt."""
    return httpx.Response(
        recording["status"],
        headers={"content-type": recording["content_type"]},
        content=recording["body"].encode("utf-8"),
        request=httpx.Request("GET", url, params=params),
    )


@pytest.fixture
def network(monkeypatch):
    """httpx.get replaced: a list of what reached it, and what it answers.

    `answers` maps a URL to the response to hand back; a URL with no answer
    raises, so a test that expected a replay and got a live call fails
    loudly instead of reaching the real service.
    """
    http_retry.clear_memo()
    for name in (http_retry.RECORDED_ENV, http_retry.RECORD_ENV):
        monkeypatch.delenv(name, raising=False)
    sent: list[tuple[str, dict]] = []
    answers: dict[str, httpx.Response] = {}

    def fake_get(url, **kwargs):
        sent.append((url, kwargs))
        if url in answers:
            return answers[url]
        raise AssertionError(f"unexpected live request: {url} {kwargs.get('params')}")

    monkeypatch.setattr(http_retry.httpx, "get", fake_get)
    monkeypatch.setattr(http_retry.time, "sleep", lambda s: None)
    yield sent, answers
    http_retry.clear_memo()


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

def test_a_recorded_get_is_answered_without_the_network(network, monkeypatch):
    sent, _ = network
    monkeypatch.setenv(http_retry.RECORDED_ENV, str(HTTP_RECORDED))

    r = http_retry.retry_get(ESEARCH, params=dict(HUMAN_ESEARCH_PARAMS), timeout=15)

    assert sent == []
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/json; charset=UTF-8"
    assert r.json()["esearchresult"]["idlist"] == ["9606"]
    # Bound to a request, so raise_for_status and r.url work as they do live.
    assert r.request.url.host == "eutils.ncbi.nlm.nih.gov"
    r.raise_for_status()


def test_the_real_caller_gets_the_recorded_taxon(network, monkeypatch):
    """enzyme_lookup.fetch_taxon_id, unchanged, reads the replayed answer."""
    import enzyme_lookup

    sent, _ = network
    monkeypatch.setenv(http_retry.RECORDED_ENV, str(HTTP_RECORDED))
    monkeypatch.setattr(enzyme_lookup, "NCBI_API_KEY", None)
    assert enzyme_lookup.fetch_taxon_id("Homo sapiens") == "9606"
    assert sent == []


def test_a_recorded_not_found_replays_as_a_not_found(network, monkeypatch):
    """PubChem's 404 for a name it does not know is an answer, and most of
    the PubChem lookups in a hexokinase run are exactly that."""
    sent, _ = network
    monkeypatch.setenv(http_retry.RECORDED_ENV, str(HTTP_RECORDED))

    r = http_retry.retry_get(PUBCHEM_HEXOKINASE, timeout=15)

    assert sent == []
    assert r.status_code == 404
    assert r.json()["Fault"]["Code"] == "PUGREST.NotFound"
    with pytest.raises(httpx.HTTPStatusError):
        r.raise_for_status()


def test_a_request_with_no_recording_goes_live(network, monkeypatch):
    sent, answers = network
    monkeypatch.setenv(http_retry.RECORDED_ENV, str(HTTP_RECORDED))
    params = {"db": "taxonomy", "term": "Thermus aquaticus[Scientific Name]", "retmode": "json"}
    live = _live_response(ESEARCH, params, _recording(ESEARCH, HUMAN_ESEARCH_PARAMS))
    answers[ESEARCH] = live

    r = http_retry.retry_get(ESEARCH, params=params, timeout=15)

    assert r is live
    assert len(sent) == 1


def test_a_file_whose_key_disagrees_is_not_trusted(network, monkeypatch, tmp_path):
    """A recording copied under another request's name answers nothing."""
    sent, answers = network
    real = HTTP_RECORDED / http_retry.recording_name(
        http_retry.replay_key(ESEARCH, {"params": HUMAN_ESEARCH_PARAMS})
    )
    params = {"db": "taxonomy", "term": "Mus musculus[Scientific Name]", "retmode": "json"}
    (tmp_path / http_retry.recording_name(
        http_retry.replay_key(ESEARCH, {"params": params})
    )).write_bytes(real.read_bytes())
    monkeypatch.setenv(http_retry.RECORDED_ENV, str(tmp_path))
    answers[ESEARCH] = _live_response(ESEARCH, params, _recording(ESEARCH, HUMAN_ESEARCH_PARAMS))

    http_retry.retry_get(ESEARCH, params=params, timeout=15)

    assert len(sent) == 1, "a recording of Homo sapiens answered a question about Mus musculus"


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------

def test_a_live_answer_is_recorded_and_then_replayed(network, monkeypatch, tmp_path):
    sent, answers = network
    recording = _recording(ESEARCH, HUMAN_ESEARCH_PARAMS)
    answers[ESEARCH] = _live_response(ESEARCH, HUMAN_ESEARCH_PARAMS, recording)
    monkeypatch.setenv(http_retry.RECORD_ENV, str(tmp_path))

    live = http_retry.retry_get(ESEARCH, params=dict(HUMAN_ESEARCH_PARAMS), timeout=15)

    key = http_retry.replay_key(ESEARCH, {"params": HUMAN_ESEARCH_PARAMS})
    written = tmp_path / http_retry.recording_name(key)
    stored = json.loads(gzip.decompress(written.read_bytes()).decode("utf-8"))
    assert stored["key"] == key
    assert stored["status"] == 200
    assert stored["content_type"] == "application/json; charset=UTF-8"
    assert stored["body"] == recording["body"]
    assert len(stored["fetched"]) == 10  # an ISO date
    assert list(tmp_path.glob("*.partial")) == []

    # And back: a fresh process (an empty memo) with the network gone.
    http_retry.clear_memo()
    monkeypatch.delenv(http_retry.RECORD_ENV)
    monkeypatch.setenv(http_retry.RECORDED_ENV, str(tmp_path))
    answers.clear()
    replayed = http_retry.retry_get(ESEARCH, params=dict(HUMAN_ESEARCH_PARAMS), timeout=15)
    assert len(sent) == 1
    assert replayed.status_code == live.status_code
    assert replayed.content == live.content
    assert replayed.headers["content-type"] == live.headers["content-type"]


def test_recording_the_same_answer_twice_gives_the_same_bytes(network, monkeypatch, tmp_path):
    """gzip's timestamp is zeroed, so a refresh that changed nothing shows
    no diff in the repository."""
    _, answers = network
    recording = _recording(ESEARCH, HUMAN_ESEARCH_PARAMS)
    answers[ESEARCH] = _live_response(ESEARCH, HUMAN_ESEARCH_PARAMS, recording)
    monkeypatch.setenv(http_retry.RECORD_ENV, str(tmp_path))
    name = http_retry.recording_name(http_retry.replay_key(ESEARCH, {"params": HUMAN_ESEARCH_PARAMS}))

    http_retry.retry_get(ESEARCH, params=dict(HUMAN_ESEARCH_PARAMS))
    first = (tmp_path / name).read_bytes()
    http_retry.clear_memo()
    http_retry.retry_get(ESEARCH, params=dict(HUMAN_ESEARCH_PARAMS))
    assert (tmp_path / name).read_bytes() == first


def test_a_not_found_is_recorded(network, monkeypatch, tmp_path):
    _, answers = network
    answers[PUBCHEM_HEXOKINASE] = _live_response(
        PUBCHEM_HEXOKINASE, None, _recording(PUBCHEM_HEXOKINASE),
    )
    monkeypatch.setenv(http_retry.RECORD_ENV, str(tmp_path))
    http_retry.retry_get(PUBCHEM_HEXOKINASE)
    assert len(list(tmp_path.glob("*.json.gz"))) == 1


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_a_throttle_or_server_error_is_never_recorded(network, monkeypatch, tmp_path, status):
    """The next recording run must ask again, not inherit an outage."""
    _, answers = network
    answers[ESEARCH] = httpx.Response(status, request=httpx.Request("GET", ESEARCH))
    monkeypatch.setenv(http_retry.RECORD_ENV, str(tmp_path))
    try:
        http_retry.retry_get(ESEARCH, params=dict(HUMAN_ESEARCH_PARAMS), max_retries=0)
    except httpx.HTTPStatusError:
        pass
    assert list(tmp_path.glob("*")) == []


# ---------------------------------------------------------------------------
# The key
# ---------------------------------------------------------------------------

def _name(url: str, **kwargs) -> str:
    return http_retry.recording_name(http_retry.replay_key(url, kwargs))


def test_parameter_order_and_type_do_not_split_one_question():
    """httpx sends size=1 and size="1" identically, and dict order is the
    caller's accident, not the question."""
    url = "https://rest.uniprot.org/uniprotkb/search"
    assert _name(url, params={"query": "ec:2.7.1.1", "size": 1}) == _name(
        url, params={"size": "1", "query": "ec:2.7.1.1"}
    )
    assert _name(url, params={"query": "ec:2.7.1.1"}) != _name(url, params={"query": "ec:2.7.1.2"})
    assert _name(url, params={"query": "ec:2.7.1.1"}) != _name(url + "x", params={"query": "ec:2.7.1.1"})


def test_a_header_that_changes_the_answer_is_part_of_the_key():
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    assert _name(url, headers={"Accept": "application/json"}) != _name(url, headers={"Accept": "text/xml"})
    assert _name(url, headers={"accept": "text/xml"}) == _name(url, headers={"Accept": "text/xml"})


def test_a_header_that_only_names_the_client_is_not():
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    assert _name(url, headers={"User-Agent": "caterva/0.3"}) == _name(url)
    assert _name(url, headers={"Accept-Encoding": "gzip"}) == _name(url)


def test_following_redirects_is_a_different_question():
    url = "https://www.brenda-enzymes.org/literature.php?r=641068"
    assert _name(url, follow_redirects=True) != _name(url)


def test_timeout_is_not_part_of_the_question():
    assert _name(ESEARCH, params=HUMAN_ESEARCH_PARAMS, timeout=15) == _name(
        ESEARCH, params=HUMAN_ESEARCH_PARAMS, timeout=30,
    )


# ---------------------------------------------------------------------------
# Credentials: never on disk, never answered from disk
# ---------------------------------------------------------------------------

def test_the_ncbi_api_key_the_literature_layer_sends_is_excluded(network, monkeypatch, tmp_path):
    """enzyme_lookup._ncbi_params attaches NCBI_API_KEY as `api_key`. With a
    key set, the request is neither recorded nor replayed, although a
    recording of the keyless request sits right there."""
    import enzyme_lookup

    sent, answers = network
    monkeypatch.setattr(enzyme_lookup, "NCBI_API_KEY", "not-a-real-key-0123456789")
    params = enzyme_lookup._ncbi_params(**HUMAN_ESEARCH_PARAMS)
    assert "api_key" in params, "premise: the key is attached as a query parameter"
    assert http_retry.replay_key(ESEARCH, {"params": params}) is None

    answers[ESEARCH] = _live_response(ESEARCH, params, _recording(ESEARCH, HUMAN_ESEARCH_PARAMS))
    monkeypatch.setenv(http_retry.RECORDED_ENV, str(HTTP_RECORDED))
    monkeypatch.setenv(http_retry.RECORD_ENV, str(tmp_path))

    assert enzyme_lookup.fetch_taxon_id("Homo sapiens") == "9606"
    assert len(sent) == 1, "a request carrying an API key was answered from a recording"
    assert list(tmp_path.glob("*")) == [], "a request carrying an API key was written to disk"


def test_the_pubmed_api_key_is_excluded_too():
    """fallback_logic's PubMed esearch/esummary attach the same key the same way."""
    params = {"db": "pubmed", "term": "hexokinase", "retmode": "json", "api_key": "k"}
    assert http_retry.replay_key("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                                 {"params": params}) is None


def test_the_core_bearer_token_is_excluded(network, monkeypatch, tmp_path):
    """core_fulltext.fetch_core_search sends CORE_API_KEY as an
    Authorization header. It must reach CORE and must never reach a file."""
    import core_fulltext

    sent, answers = network
    monkeypatch.setattr(core_fulltext, "CORE_API_KEY", "not-a-real-token-0123456789")
    answers[core_fulltext.CORE_SEARCH_URL] = httpx.Response(
        200, json={"totalHits": 0, "results": []},
        request=httpx.Request("GET", core_fulltext.CORE_SEARCH_URL),
    )
    monkeypatch.setenv(http_retry.RECORD_ENV, str(tmp_path))

    core_fulltext.fetch_core_search("hexokinase glucose Km")

    assert len(sent) == 1
    assert sent[0][1]["headers"]["Authorization"].startswith("Bearer ")
    assert list(tmp_path.glob("*")) == []


@pytest.mark.parametrize(
    "url, kwargs",
    [
        ("https://api.example.org/v1/search", {"headers": {"X-API-Key": "k"}}),
        ("https://api.example.org/v1/search", {"headers": {"Cookie": "session=k"}}),
        ("https://api.example.org/v1/search", {"headers": {"Proxy-Authorization": "Basic k"}}),
        ("https://api.example.org/v1/search", {"auth": ("user", "password")}),
        ("https://api.example.org/v1/search", {"cookies": {"session": "k"}}),
        ("https://api.example.org/v1/search", {"params": {"token": "k"}}),
        ("https://api.example.org/v1/search", {"params": {"apikey": "k"}}),
        ("https://api.example.org/v1/search?api_key=k", {}),
        ("https://user:password@api.example.org/v1/search", {}),
    ],
)
def test_every_other_credential_spelling_is_excluded(url, kwargs):
    assert http_retry.replay_key(url, kwargs) is None


def test_no_committed_recording_holds_a_credential():
    """The other direction: whatever the code says, check the files."""
    names = sorted(HTTP_RECORDED.glob("*.json.gz"))
    assert names, "no recordings found; this test would pass without reading any"
    for path in names:
        record = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        key = record["key"]
        assert http_retry.recording_name(key) == path.name, f"{path.name} is filed under the wrong key"
        assert {k.lower() for k, _ in key["params"]}.isdisjoint(http_retry.CREDENTIAL_PARAMS), path.name
        assert {k.lower() for k, _ in key["headers"]}.isdisjoint(http_retry.CREDENTIAL_HEADERS), path.name
        assert "api_key=" not in record["response_url"], path.name


# ---------------------------------------------------------------------------
# The runner, offline, against what it said live
# ---------------------------------------------------------------------------

@pytest.fixture
def offline(monkeypatch):
    """Both recording variables set, and every real send made impossible.

    httpx.HTTPTransport.handle_request is where every httpx.get ends up;
    replacing it means a request nobody recorded raises instead of reaching
    the service, and `attempts` says which one it was. The keys are cleared
    because a request carrying one is never replayed (see above), and the
    import-time NCBI_API_KEY of a developer's shell would otherwise send
    this test to the network.
    """
    attempts: list[str] = []

    def no_network(self, request):
        attempts.append(str(request.url))
        raise httpx.ConnectError("network disabled in this test", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    # A missing recording then fails in milliseconds rather than after
    # retry_get's 1 s / 2 s / 4 s backoff on the connection error.
    monkeypatch.setattr(http_retry.time, "sleep", lambda s: None)
    monkeypatch.setenv("CATERVA_BRENDA_RECORDED", str(RECORDED))
    monkeypatch.setenv(http_retry.RECORDED_ENV, str(HTTP_RECORDED))
    for name in (http_retry.RECORD_ENV, "CATERVA_ENABLE_KEGG"):
        monkeypatch.delenv(name, raising=False)

    if str(LIB_DIR) not in sys.path:
        sys.path.insert(0, str(LIB_DIR))
    import core_fulltext
    import enzyme_lookup
    import fallback_logic

    monkeypatch.setattr(enzyme_lookup, "NCBI_API_KEY", None)
    monkeypatch.setattr(fallback_logic, "NCBI_API_KEY", None)
    monkeypatch.setattr(core_fulltext, "CORE_API_KEY", None)
    http_retry.clear_memo()
    yield attempts
    http_retry.clear_memo()


def _run_runner(monkeypatch, payload: dict) -> dict:
    import science_agent_runner

    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "stdout", stdout)
    science_agent_runner.main()
    return json.loads(stdout.getvalue())


def _answer(output: dict, recorded: dict) -> dict:
    return {field: output[field] for field in recorded if field in output}


HEXOKINASE_KM = next(
    entry for entry in MANIFEST["payloads"]
    if entry["payload"].get("ecNumber") == "2.7.1.1"
    and entry["payload"]["organism"] == "Homo sapiens"
    and entry["payload"]["quantity"] == "km"
)


def test_the_hexokinase_km_lookup_gives_its_live_answer_offline(offline, monkeypatch):
    """The flagship lookup, the real runner, no network: same value, same
    citation, same taxon as the live run the recordings came from."""
    output = _run_runner(monkeypatch, HEXOKINASE_KM["payload"])
    recorded = HEXOKINASE_KM["answer"]

    assert offline == [], f"these requests were not recorded: {offline}"
    assert output["ok"] is True and output["found"] is True
    assert output["km"] == recorded["km"]
    assert output["unit"] == recorded["unit"]
    assert output["citation"] == recorded["citation"]
    assert output["taxonId"] == recorded["taxonId"] == "9606"
    assert output["requestedTaxonId"] == recorded["requestedTaxonId"]
    assert _answer(output, recorded) == recorded


@pytest.mark.parametrize(
    "entry", MANIFEST["payloads"],
    ids=[f"{e['payload']['enzymeName']}|{e['payload']['organism']}|{e['payload']['quantity']}"
         + ("" if e["payload"].get("ecNumber") else "|no-ec")
         for e in MANIFEST["payloads"]],
)
def test_every_payload_the_api_tests_send_replays_offline(offline, monkeypatch, entry):
    """If an API test's lookup needed a request that was not recorded, it
    would go live in CI; here it raises instead, and says which."""
    output = _run_runner(monkeypatch, entry["payload"])
    assert offline == [], f"these requests were not recorded: {offline}"
    assert _answer(output, entry["answer"]) == entry["answer"]


def test_the_manifest_names_only_files_that_exist():
    listed = {name for entry in MANIFEST["payloads"] for name in entry["recordings"]}
    present = {p.name for p in HTTP_RECORDED.glob("*.json.gz")}
    assert listed == present, (
        f"listed but missing: {sorted(listed - present)}; "
        f"present but unlisted: {sorted(present - listed)}"
    )


def test_the_env_names_match_the_ones_the_test_config_sets():
    """The vitest config and this module must agree on the spelling."""
    config = (TESTS.parent / "Science-Agent-Pipeline" / "artifacts" / "api-server"
              / "vitest.config.ts").read_text(encoding="utf-8")
    assert f"{http_retry.RECORDED_ENV}:" in config
    assert os.path.basename(HTTP_RECORDED) in config
