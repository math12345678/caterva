"""The enzyme finder's endpoints through the studio's dispatch layer.

`GET /api/enzymes/find` must return the finder's candidates, which are the
ones `caterva enzyme QUERY --json` prints: both call
`caterva.enzymes.__main__.find_payload`, and the parity test below proves it
for real queries instead of trusting that sentence. The rest checks what the
contract says: the request limits, the shape of the detail route and its
isozymes, that the UniProt fallback is asked only when the finder found
nothing and the capabilities say the network is reachable, and that it never
offers what UniProt did not return.

Nothing here touches the network: the fallback's UniProt lookup is replaced
by a function that returns what the test says UniProt returned, which is the
seam `caterva.enzymes.policy.literature_uniprot_lookup` exists to provide.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import quote

import pytest

from caterva import netuse
from caterva.studio.adapters import load_registry
from caterva.studio.contract import SESSION_HEADER
from caterva.studio.dispatch import App, Request
from caterva.studio.static_files import StaticSite
from caterva.studio.workspace import Workspace

PORT = 18769
TOKEN = "e" * 43
HEADERS = [("Host", f"127.0.0.1:{PORT}"), (SESSION_HEADER, TOKEN)]

#: The queries the owner complained about, and an abbreviation with an organism.
QUERIES = [
    ("lactate dehydrogenase", None),
    ("pyruvate kinase", None),
    ("hexokinase", None),
    ("glucokinase", None),
    ("LDHA", "human"),
    ("lactate dehydrogenase", "human"),
    ("hexokinse", "human"),
    ("2.7.1.1", "human"),
]


def _options(reachable=None, literature=True):
    return dict(head=lambda h, t: None, literature_import=(lambda: None) if literature else _missing,
                which=lambda n: None, is_executable=lambda p: False)


def _missing():
    raise ImportError("the literature layer is not in this installation")


@pytest.fixture
def app(tmp_path: Path):
    app = App(workspace=Workspace(tmp_path / "data"), port=PORT, token=TOKEN,
              static_site=StaticSite(tmp_path / "no-build"), registry=load_registry(),
              capability_options=_options())
    app.start(apply_environment=False)
    yield app
    app.close()


def get(app: App, target: str):
    response = app.dispatch(Request("GET", target, list(HEADERS), None))
    return response.status, response.json()


def find(app: App, q: str, organism: str | None = None, limit: int | None = None):
    target = f"/api/enzymes/find?q={quote(q)}"
    if organism:
        target += f"&organism={quote(organism)}"
    if limit:
        target += f"&limit={limit}"
    return get(app, target)


def cli_json(query: str, organism: str | None):
    from caterva.enzymes.__main__ import main

    argv = [query, "--json"] + (["--organism", organism] if organism else [])
    out = io.StringIO()
    with redirect_stdout(out):
        main(argv)
    return json.loads(out.getvalue())


# ---------------------------------------------------------------------------
# Parity with `caterva enzyme --json`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query, organism", QUERIES)
def test_the_endpoints_candidates_are_the_commands_candidates(app, query, organism):
    status, body = find(app, query, organism)
    assert status == 200
    printed = cli_json(query, organism)
    assert body["query"] == printed["query"] and body["outcome"] == printed["outcome"]
    assert body["candidates_total"] == printed["candidates_total"]
    assert body["release"] == printed["release"] and body["organism_code"] == printed["organism_code"]
    assert body["resolved_ec"] == printed.get("resolved_ec")
    assert body["recommended_ec"] == printed.get("recommended_ec")
    got = [{k: v for k, v in c.items() if k not in ("recommended", "caution")} for c in body["candidates"]]
    assert got == printed["candidates"], "the page's candidates must be the command's, key for key"
    assert [c["ec"] for c in body["candidates"]]  # a real answer, not an empty one


def test_a_candidate_names_what_the_page_draws(app):
    _, body = find(app, "lactate dehydrogenase", "human")
    first = body["candidates"][0]
    assert first["ec"] == "1.1.1.27" and first["name"] == "L-lactate dehydrogenase"
    assert first["reaction"] and first["class_path"] and first["why"]
    assert first["recommended"] is True and body["recommended_ec"] == "1.1.1.27"
    assert first["has_organism_protein"] is True and first["organism_protein_count"] >= 3
    assert {"LDHA", "LDHB", "LDHC"} <= {p["symbol"] for p in first["organism_proteins"]}
    assert body["outcome"] == "ambiguous" and body["resolved_ec"] is None
    assert body["organism_code"] == "HUMAN" and body["organism_label"] == "human"
    assert [c["recommended"] for c in body["candidates"]].count(True) == 1


def test_a_resolved_name_carries_its_caution_on_the_resolved_candidate(app):
    _, body = find(app, "hexokinase", "human")
    assert body["outcome"] == "resolved" and body["resolved_ec"] == "2.7.1.1"
    resolved = next(c for c in body["candidates"] if c["ec"] == "2.7.1.1")
    assert resolved["recommended"] is False
    assert body["fallback"] is None and "fallback_unavailable" not in body


def test_a_typo_is_a_suggestion_not_a_resolution(app):
    _, body = find(app, "hexokinse", "human")
    assert body["outcome"] == "suggestions" and body["resolved_ec"] is None
    assert any(c["ec"] == "2.7.1.1" for c in body["candidates"])
    assert body["fallback"] is None and "fallback_unavailable" not in body


def test_a_transferred_number_resolves_to_its_successor_and_says_so(app):
    from caterva.enzymes import load_index

    entry = next(e for e in load_index().entries.values() if e.status == "transferred" and len(e.superseded_by) == 1)
    _, body = find(app, entry.ec)
    assert body["outcome"] == "resolved" and body["resolved_ec"] == entry.superseded_by[0]
    old = next(c for c in body["candidates"] if c["ec"] == entry.ec)
    assert old["status"] == "transferred" and old["superseded_by"] == list(entry.superseded_by)
    assert body["cautions"] and "transferred" in body["cautions"][0]
    new = next(c for c in body["candidates"] if c["ec"] == entry.superseded_by[0])
    assert new["caution"]


# ---------------------------------------------------------------------------
# What a request may be
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target, field", [
    ("/api/enzymes/find", "q"),
    ("/api/enzymes/find?q=", "q"),
    ("/api/enzymes/find?q=" + "a" * 201, "q"),
    ("/api/enzymes/find?q=hexo%00kinase", "q"),
    ("/api/enzymes/find?q=hexokinase&organism=" + "h" * 101, "organism"),
    ("/api/enzymes/find?q=hexokinase&limit=0", "limit"),
    ("/api/enzymes/find?q=hexokinase&limit=51", "limit"),
    ("/api/enzymes/find?q=hexokinase&limit=ten", "limit"),
    ("/api/enzymes/find?q=hexokinase&path=/etc/passwd", "path"),
])
def test_a_request_outside_the_limits_is_malformed_under_its_field(app, target, field):
    status, body = get(app, target)
    assert status == 400 and body["error"]["code"] == "malformed" and body["error"]["field"] == field


def test_a_repeated_key_is_malformed(app):
    status, body = get(app, "/api/enzymes/find?q=a&q=b")
    assert status == 400


def test_text_that_looks_like_a_path_is_only_ever_searched_for(app):
    status, body = find(app, "../../etc/passwd")
    assert status == 200 and body["outcome"] == "none" and body["candidates"] == []


def test_the_limit_is_honoured_and_the_total_is_not_cut(app):
    _, body = find(app, "dehydrogenase", limit=3)
    assert len(body["candidates"]) == 3 and body["candidates_total"] > 3


def test_a_second_ask_is_answered_from_memory(app, monkeypatch):
    import caterva.enzymes.__main__ as command
    from caterva.studio.adapters import enzymes

    enzymes._cache.clear()
    find(app, "pyruvate kinase")
    monkeypatch.setattr(command, "find_payload", lambda *a, **k: pytest.fail("asked the finder twice"))
    status, body = find(app, "Pyruvate  Kinase")
    assert status == 200 and body["candidates"]


# ---------------------------------------------------------------------------
# One enzyme, and its isozymes
# ---------------------------------------------------------------------------


def test_the_detail_lists_the_organisms_isozymes_by_entry_name(app):
    status, body = get(app, "/api/enzymes/2.7.1.1?organism=human")
    assert status == 200 and body["ec"] == "2.7.1.1" and body["name"] == "hexokinase"
    iso = body["isozymes"]
    assert iso["organism"] == "HUMAN" and iso["organism_known"] is True and iso["organism_label"] == "human"
    assert iso["count"] == len(iso["proteins"]) >= 5
    entry_names = {p["entry_name"] for p in iso["proteins"]}
    assert {"HXK1_HUMAN", "HXK2_HUMAN", "HXK3_HUMAN", "HXK4_HUMAN", "HKDC1_HUMAN"} <= entry_names
    assert {p["symbol"] for p in iso["proteins"]} >= {"HXK1", "HXK4", "HKDC1"}
    assert body["reaction"] and body["class_path"] and body["status"] == "active"


def test_the_detail_without_an_organism_has_no_isozymes_and_does_not_pretend(app):
    _, body = get(app, "/api/enzymes/2.7.1.1")
    assert body["isozymes"] == {"organism": None, "organism_label": None, "count": 0, "proteins": [],
                                "organism_known": False, "broad": False, "note": None, "organism_scope": None,
                                "filed_elsewhere": None}


def test_a_broad_class_is_not_called_isozymes_and_a_chooser_is_not_built_for_it(app):
    """EC 2.7.11.1 is 245 different human kinases, not isozymes of one enzyme."""
    _, body = get(app, "/api/enzymes/2.7.11.1?organism=human")
    iso = body["isozymes"]
    assert iso["count"] == 245 and iso["broad"] is True
    assert "245 different human proteins share EC 2.7.11.1 (a broad class" in iso["note"]
    assert "isozymes" not in iso["note"].split("(a broad class")[0]


def test_the_family_the_nomenclature_files_elsewhere_is_named_for_alcohol_dehydrogenase(app):
    """ADH1B and ADH4 are filed under EC 1.1.1.105 only, so EC 1.1.1.1's list leaves them out."""
    _, body = get(app, "/api/enzymes/1.1.1.1?organism=human")
    iso = body["isozymes"]
    assert [p["label"] for p in iso["proteins"]] == ["ADH1A", "ADH1C", "ADH6", "ADH7", "ADH5"]
    assert "ADH1B" in iso["filed_elsewhere"] and "ADH4" in iso["filed_elsewhere"] and "EC 1.1.1.105" in iso["filed_elsewhere"]


def test_e_coli_means_the_k_12_strain_and_the_detail_says_so(app):
    _, body = get(app, "/api/enzymes/1.1.1.1?organism=" + quote("E. coli"))
    scope = body["isozymes"]["organism_scope"]
    assert scope.startswith("E. coli K-12") and "other E. coli strains" in scope
    assert "E. coli K-12 isozymes" in body["isozymes"]["note"]


def test_a_transferred_ec_carries_its_replacements_name_and_a_deleted_one_says_it_has_none(app):
    from caterva.enzymes import load_index

    entries = load_index().entries
    moved = next(e for e in sorted(entries) if entries[e].status == "transferred" and len(entries[e].superseded_by) == 1)
    _, body = get(app, f"/api/enzymes/{moved}")
    successor = entries[body["replaced_by"][0]["ec"]]
    assert body["name"] == successor.name != "" and body["replaced_by"] == [{"ec": successor.ec, "name": successor.name}]
    assert "transferred" in body["name_note"]
    gone = next(e for e in sorted(entries) if entries[e].status == "deleted" and not entries[e].superseded_by)
    _, body = get(app, f"/api/enzymes/{gone}")
    assert body["name"] == "Deleted entry" and body["replaced_by"] == [] and "deleted" in body["name_note"]


def test_an_organism_the_finder_does_not_know_is_not_zero_proteins(app):
    _, body = get(app, "/api/enzymes/2.7.1.1?organism=" + quote("Thermus thermophilus"))
    assert body["isozymes"]["organism_known"] is False and body["isozymes"]["proteins"] == []


def test_the_detail_isozymes_are_the_notice_the_report_prints(app):
    from caterva.enzymes.isozyme import isozyme_notice

    _, body = get(app, "/api/enzymes/2.7.1.1?organism=human")
    notice = isozyme_notice("2.7.1.1", "human", None)
    assert tuple(p["label"] for p in body["isozymes"]["proteins"]) == notice.symbols == ("HKDC1", "HK1", "HK2", "HK3", "GCK")
    assert body["isozymes"]["note"] == notice.text and body["isozymes"]["broad"] is False
    first = body["isozymes"]["proteins"][1]
    assert (first["symbol"], first["gene"], first["accession"]) == ("HXK1", "HK1", "P19367")
    assert first["names"][0] == "HK1" and "HK I" in first["names"] and first["engine_matches"] is True


def test_an_ec_the_nomenclature_does_not_list_is_404_in_the_finders_words(app):
    status, body = get(app, "/api/enzymes/9.9.9.9")
    assert status == 404 and "is not in the enzyme nomenclature" in body["error"]["message"]


@pytest.mark.parametrize("path", ["/api/enzymes/hexokinase", "/api/enzymes/2.7.1", "/api/enzymes/2.7.1.1/extra",
                                  "/api/enzymes/..%2f..%2fetc", "/api/enzymes/2.7.1.-"])
def test_anything_but_a_complete_ec_matches_no_route(app, path):
    status, body = get(app, path)
    assert status == 404 and body["error"]["code"] == "not_found"


def test_the_detail_refuses_keys_it_does_not_have(app):
    status, body = get(app, "/api/enzymes/2.7.1.1?q=x")
    assert status == 400 and body["error"]["field"] == "q"


# ---------------------------------------------------------------------------
# The UniProt fallback
# ---------------------------------------------------------------------------


def _lookup(monkeypatch, answer):
    """UniProt's protein-name search, answering `answer` (or raising it)."""
    from caterva.enzymes import policy

    def lookup(timeout=None):
        def ask(name):
            if isinstance(answer, Exception):
                raise answer
            return list(answer)
        return ask

    monkeypatch.setattr(policy, "literature_uniprot_lookup", lookup)


NOTHING = "zzqx protein of no enzyme"


def test_nothing_found_and_the_network_not_known_offers_no_fallback_and_says_why(app, monkeypatch):
    _lookup(monkeypatch, ["2.7.1.40"])
    _, body = find(app, NOTHING)
    assert body["outcome"] == "none" and body["candidates"] == []
    assert body["fallback"] is None and "not known to be reachable" in body["fallback_unavailable"]


def test_nothing_found_and_the_network_reachable_asks_uniprot_through_the_policy(app, monkeypatch):
    _lookup(monkeypatch, ["2.7.1.40"])
    netuse.answered("https://rest.uniprot.org/uniprotkb/search")
    _, body = find(app, NOTHING)
    fallback = body["fallback"]
    assert fallback["kind"] == "uniprot" and "fallback_unavailable" not in body
    assert fallback["suggestions"] == [{"ec": "2.7.1.40", "name": "pyruvate kinase"}]
    assert "exactly one EC number" in fallback["note"]


def test_the_fallback_is_gated_on_uniprots_own_status_not_on_an_aggregate(app, monkeypatch):
    """A BRENDA failure after a UniProt success used to overwrite one flag and block the fallback;
    a BRENDA success with nothing known about UniProt must not open it."""
    _lookup(monkeypatch, ["2.7.1.40"])
    netuse.answered("https://rest.uniprot.org/uniprotkb/search")
    netuse.failed("https://www.brenda-enzymes.org/enzyme.php", "connection reset")
    _, body = find(app, NOTHING)
    assert body["fallback"] is not None and "fallback_unavailable" not in body, "UniProt answered; BRENDA failing is not UniProt failing"
    netuse.failed("https://rest.uniprot.org/uniprotkb/search", "name resolution failed")
    _, body = find(app, NOTHING)
    assert body["fallback"] is None and "UniProt is not known to be reachable" in body["fallback_unavailable"]


def test_a_reachable_brenda_alone_does_not_open_the_uniprot_fallback(app, monkeypatch):
    _lookup(monkeypatch, ["2.7.1.40"])
    app.capabilities._host_status.clear()
    netuse.answered("https://www.brenda-enzymes.org/enzyme.php")
    _, body = find(app, NOTHING)
    assert body["fallback"] is None and "UniProt is not known to be reachable" in body["fallback_unavailable"]


def test_uniprot_naming_several_enzymes_lists_each_and_picks_none(app, monkeypatch):
    _lookup(monkeypatch, ["1.1.1.27", "1.1.1.28"])
    netuse.answered("https://rest.uniprot.org/uniprotkb/search")
    _, body = find(app, NOTHING)
    assert [s["ec"] for s in body["fallback"]["suggestions"]] == ["1.1.1.27", "1.1.1.28"]
    assert all(s["name"] for s in body["fallback"]["suggestions"])
    assert "different enzymes" in body["fallback"]["note"] and body["resolved_ec"] is None


def test_uniprot_finding_nothing_offers_nothing_invented(app, monkeypatch):
    _lookup(monkeypatch, [])
    netuse.answered("https://rest.uniprot.org/uniprotkb/search")
    _, body = find(app, NOTHING)
    assert body["fallback"]["suggestions"] == [] and "UniProt indexes no reviewed enzyme" in body["fallback"]["note"]


def test_a_failed_uniprot_call_is_said_and_marks_the_network(app, monkeypatch):
    _lookup(monkeypatch, ConnectionError("name resolution failed"))
    netuse.answered("https://rest.uniprot.org/uniprotkb/search")
    _, body = find(app, NOTHING)
    assert body["fallback"]["suggestions"] == [] and "Could not look up" in body["fallback"]["note"]


def test_without_the_literature_layer_uniprot_is_not_asked(tmp_path, monkeypatch):
    app = App(workspace=Workspace(tmp_path / "data"), port=PORT, token=TOKEN, static_site=StaticSite(tmp_path / "nb"),
              registry=load_registry(), capability_options=_options(literature=False))
    app.start(apply_environment=False)
    try:
        _lookup(monkeypatch, ["2.7.1.40"])
        netuse.answered("https://rest.uniprot.org/uniprotkb/search")
        _, body = find(app, NOTHING)
        assert body["fallback"] is None and "literature layer" in body["fallback_unavailable"]
    finally:
        app.close()


def test_offline_mode_never_asks_uniprot(app, monkeypatch):
    _lookup(monkeypatch, ["2.7.1.40"])
    netuse.answered("https://rest.uniprot.org/uniprotkb/search")
    app._settings = {**app.settings(), "offline": True}
    _, body = find(app, NOTHING)
    assert body["fallback"] is None and "offline" in body["fallback_unavailable"]


def test_a_finder_hit_never_calls_uniprot(app, monkeypatch):
    _lookup(monkeypatch, AssertionError("UniProt was asked although the finder had an answer"))
    netuse.answered("https://rest.uniprot.org/uniprotkb/search")
    _, body = find(app, "pyruvate kinase")
    assert body["outcome"] == "resolved" and body["fallback"] is None


# ---------------------------------------------------------------------------
# The routes are the contract's
# ---------------------------------------------------------------------------


def test_the_two_routes_are_owned_by_the_kinetics_adapter_and_registered():
    from caterva.studio.routes import ROUTES

    owned = {r.handler: r.owner for r in ROUTES if r.path.startswith("/api/enzymes")}
    assert owned == {"find_enzymes": "compose", "enzyme_detail": "compose"}
    registry = load_registry()
    assert registry.endpoint("find_enzymes") and registry.endpoint("enzyme_detail")
