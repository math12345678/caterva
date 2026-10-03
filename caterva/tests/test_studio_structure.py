"""The studio's `structure` kind and the viewer's coordinates give what `caterva structure` and `caterva prepare` give.

The search replays the real UniProt and RCSB answers for EC 1.1.1.27 in
human recorded 2026-09-27 (fixtures/structure/ldh_human.json, the same
recording test_structure_search.py uses), through the command's own
`live_http`, so the command line and the adapter read the same answers and
neither touches the network. The coordinates are 1I10's real mmCIF
(trimmed, fixtures/prepare/) served through `caterva prepare`'s own fetch.

Parity is checked on the library objects (every resolution in the result
is the Structure's float, unrounded), on the printed text (the report is
the command's stdout, byte for byte), and on the exit code.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from caterva.studio import contract
from caterva.studio.adapters import EndpointRequest, RunContext, load_registry
from caterva.studio.adapters import structure as adapter

FIX = Path(__file__).parent / "fixtures"
CALLS = json.loads((FIX / "structure" / "ldh_human.json").read_text())["calls"]


class Progress:
    def __init__(self):
        self.stages = []

    def stage(self, key, label, fraction=None):
        self.stages.append(key)

    def log(self, line):
        pass

    def check_cancelled(self):
        pass


def _replay(url, payload):
    key = hashlib.sha256((url + json.dumps(payload, sort_keys=True)).encode()).hexdigest()[:16]
    assert key in CALLS, f"a call the recording does not hold: {url}"
    return CALLS[key]["response"]


@pytest.fixture(autouse=True)
def recorded_search(monkeypatch):
    from caterva.structure import search

    monkeypatch.setattr(search, "live_http", lambda timeout=30.0: search.Http(_replay, _replay))


def _ctx(tmp_path):
    run_dir = tmp_path / "runs" / "20260930-120000-structure-0badc0de"
    run_dir.mkdir(parents=True)
    return RunContext("20260930-120000-structure-0badc0de", run_dir, tmp_path, Progress())


def _cli(argv):
    from caterva.structure.__main__ import main

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _both(tmp_path, request, cli_extra=()):
    ctx = _ctx(tmp_path)
    got = adapter.structure_run(request, ctx)
    argv = [a.replace(adapter.RUN_DIR_PLACEHOLDER, str(tmp_path / "cli")) for a in adapter.structure_argv(request)]
    (tmp_path / "cli" / "artifacts").mkdir(parents=True, exist_ok=True)
    return got, _cli(argv), ctx


def test_a_chosen_protein_with_a_ligand_matches_the_command(tmp_path):
    from caterva.structure.search import find_structures

    request = {"subject": "1.1.1.27", "organism": "human", "gene": "LDHA", "ligand": "oxamate", "top": 5,
               "chimerax": True}
    got, (code, out, err), ctx = _both(tmp_path, request)
    assert got.exit_code == code == 0 and err == ""
    result = got.result
    printed_path = str(tmp_path / "cli" / "artifacts" / adapter.CHIMERAX_ARTIFACT)
    assert result["report_markdown"] == out.replace(printed_path, str(ctx.run_dir / "artifacts" / "structure.cxc"))
    assert ctx.progress.stages == ["search", "rank"]
    library = find_structures("1.1.1.27", organism="Homo sapiens", gene="LDHA", ligand="oxamate")
    ranked = library.ranked()
    assert [e["pdb_id"] for e in result["entries"]] == [s.pdb_id for s in ranked]
    assert result["total"] == len(ranked) == 46 and result["top"] == 5
    for row, s in zip(result["entries"], ranked):
        if s.resolution is None:
            assert row["resolution"] is None
        else:
            assert row["resolution"]["value"] == s.resolution
            assert row["resolution"]["provenance"]["kind"] == "measured"
            line = next((x for x in out.splitlines() if f"[{s.pdb_id}](" in x), None)
            if line is not None:  # the report lists the top entries; the result holds every one
                assert f"| {s.resolution:.2f} A |" in line
        assert row["citation"]["text"] == s.cite()
        assert row["binds_ligand"] == s.binds("oxamate")
    assert result["entries"][0]["pdb_id"] == "1I10" and result["entries"][0]["binds_ligand"] is True
    assert result["chosen"] == "P00338" and result["undecided"] is None
    assert [p["gene"] for p in result["proteins"] if p["chosen"]] == ["LDHA"]
    (artifact,) = got.artifacts
    assert artifact.name == result["chimerax_artifact"] == "structure.cxc"
    assert artifact.content.decode() == Path(printed_path).read_text()
    assert not (ctx.run_dir / "artifacts" / "structure.cxc").exists()  # the server stores it, not the adapter


def test_an_ec_number_that_is_several_proteins_is_refused_with_the_table(tmp_path):
    got, (code, out, err), _ = _both(tmp_path, {"subject": "1.1.1.27", "organism": "human"})
    assert got.exit_code == code == 3
    assert got.result["report_markdown"] == out
    assert got.refusal.startswith("Refused: EC 1.1.1.27 in Homo sapiens is 3 different proteins")
    assert got.refusal in out
    assert got.result["chosen"] is None and got.result["entries"] == []
    assert {p["gene"]: p["entries"] for p in got.result["proteins"]} == {
        "LDHA": 46, "LDHB": 7, "LDHC": 2, "LDHAL6A": 0, "LDHAL6B": 0}
    assert contract.outcome_for("structure", got.exit_code, got.summary, got.refusal)["meaning"] == "refused"


def test_a_chimerax_script_for_a_protein_with_no_entry_is_refused_not_a_crash(tmp_path):
    """The command indexed ranked()[0] of an empty ranking and crashed (exit 1)."""
    got, (code, out, err), _ = _both(tmp_path, {"subject": "1.1.1.27", "organism": "human", "gene": "LDHAL6A",
                                                "chimerax": True})
    assert got.exit_code == code == 3
    assert "has no entry in the PDB" in err and got.refusal == err.strip()
    assert got.artifacts == () and got.result["chimerax_artifact"] is None


NAMES = json.loads((FIX / "structure" / "uniprot_ec_by_name.json").read_text())["answers"]


@pytest.fixture
def recorded_names(monkeypatch):
    """UniProt's real answers to the name lookup (recorded 2026-10-01), parsed by the resolver's own parser."""
    from caterva.checkout import literature_module

    lookup = literature_module("enzyme_lookup")
    monkeypatch.setattr(lookup, "fetch_ec_numbers_by_name",
                        lambda name, taxon_id=None, timeout=15: lookup.parse_ec_number_candidates(NAMES[name]))


def test_a_name_is_looked_up_and_searched_as_its_ec_number(tmp_path, recorded_names):
    request = {"subject": "L-lactate dehydrogenase A chain", "organism": "human", "gene": "LDHA", "top": 3}
    got, (code, out, err), _ = _both(tmp_path, request)
    assert got.exit_code == code == 0 and err == ""
    assert got.result["report_markdown"] == out
    assert out.startswith("Read 'L-lactate dehydrogenase A chain' as EC 1.1.1.27 (L-lactate dehydrogenase)")
    assert got.result["ec"] == "1.1.1.27" and got.result["subject_name"] == "L-lactate dehydrogenase A chain"
    assert got.result["subject_notes"] and out.startswith(got.result["subject_notes"][0])
    by_ec, _, _ = _both(tmp_path / "ec", {**request, "subject": "1.1.1.27"})
    assert [e["pdb_id"] for e in got.result["entries"]] == [e["pdb_id"] for e in by_ec.result["entries"]]
    assert by_ec.result["subject_name"] is None
    assert adapter._needs(request) == ("network", "literature")
    assert adapter._needs({"subject": "1.1.1.27"}) == ("network",)


def test_a_name_that_is_several_enzymes_is_refused_with_every_candidate_named(tmp_path):
    """The one name policy refuses, offline, and the outcome carries its named candidates."""
    got, (code, out, err), _ = _both(tmp_path, {"subject": "lactate dehydrogenase"})
    assert got.exit_code == code == 3 and out == "" and got.result is None
    assert got.refusal == err.strip() and "names 2 enzymes" in got.refusal
    refusal = got.name_refusal
    assert refusal["kind"] == "ambiguous" and refusal["rerun_flag"] == "--subject {ec}"
    assert refusal["recommended"] is None and refusal["message"] in got.refusal
    named = {c["ec"]: c for c in refusal["named_candidates"]}
    assert named["1.1.1.27"]["name"] == "L-lactate dehydrogenase" and named["1.1.1.28"]["name"] == "D-lactate dehydrogenase"
    assert all(c["name"] and c["why"] for c in refusal["named_candidates"]), "never a bare list of EC numbers"
    outcome = contract.outcome_for("structure", got.exit_code, got.summary, got.refusal, got.name_refusal)
    assert outcome["meaning"] == "refused" and outcome["name_refusal"]["named_candidates"] == refusal["named_candidates"]


def test_the_recommended_enzyme_is_named_when_the_organism_has_one_protein_set(tmp_path):
    got, _, _ = _both(tmp_path, {"subject": "lactate dehydrogenase", "organism": "human"})
    assert got.exit_code == 3 and got.name_refusal["recommended"] == "1.1.1.27"
    assert got.name_refusal["named_candidates"][0]["has_organism_protein"] is True


def test_a_refusal_that_is_not_a_name_carries_no_name_refusal(tmp_path):
    got, _, _ = _both(tmp_path, {"subject": "1.1.1.27", "organism": "human"})
    assert got.exit_code == 3 and got.name_refusal is None


def test_no_network_is_a_refusal_with_no_result(tmp_path, monkeypatch):
    from caterva.structure import search

    def down(url, payload):
        raise ConnectionError("network is unreachable")

    monkeypatch.setattr(search, "live_http", lambda timeout=30.0: search.Http(down, down))
    got, (code, out, err), _ = _both(tmp_path, {"subject": "1.1.1.27"})
    assert got.exit_code == code == 3 and got.result is None
    assert got.refusal == err.strip() and "could not run" in got.refusal


@pytest.mark.parametrize("request_, field", [
    ({}, "subject"),
    ({"subject": "1.1.1.27", "top": "5"}, "top"),
    ({"subject": "1.1.1.27", "chimerax": 1}, "chimerax"),
    ({"subject": "1.1.1.27", "path": "/etc/passwd"}, "path"),
])
def test_a_malformed_request_names_its_field(request_, field):
    with pytest.raises(contract.Malformed) as e:
        adapter.structure_argv(request_)
    assert e.value.field == field


def test_the_kind_and_its_endpoint_are_registered():
    registry = load_registry()
    assert registry.get("structure").cli_prefix == ("caterva", "structure")
    assert registry.endpoint("structure_coordinates") is adapter.coordinates


# --- coordinates -------------------------------------------------------------------------------


def _cif(pid):
    with gzip.open(FIX / "prepare" / f"{pid}.trimmed.cif.gz", "rt") as fh:
        return fh.read()


@pytest.fixture
def recorded_prepare(monkeypatch, tmp_path):
    """`caterva prepare`'s fetch, answered from the committed entries and sequences."""
    from caterva.prepare import __main__ as prepare

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    seen = []

    def fetch(url):
        seen.append(url)
        name = url.rsplit("/", 1)[-1]
        if name.endswith(".cif"):
            pid = name[:-4]
            if not (FIX / "prepare" / f"{pid}.trimmed.cif.gz").exists():
                raise prepare.PrepareError(f"not found: {url}")
            return _cif(pid)
        return (FIX / "prepare" / name).read_text()

    monkeypatch.setattr(prepare, "live_fetch", lambda timeout=60.0: fetch)
    return seen


def _coordinates(pdb_id, tmp_path, query=None):
    return adapter.coordinates(EndpointRequest({"pdb_id": pdb_id}, query or {}, None, tmp_path))


def test_coordinates_are_the_first_model_as_the_file_gives_them(tmp_path, recorded_prepare):
    from caterva.prepare.audit import _first_model, audit
    from caterva.prepare.cif import parse
    from caterva.prepare.__main__ import sequence_fetcher

    got = _coordinates("1i10", tmp_path)
    text = _cif("1I10")
    rows = _first_model(parse(text).get("atom_site", []))
    assert got["pdb_id"] == "1I10" and got["count"] == len(rows) == len(got["atoms"]["x"])
    assert got["truncated"] is False and got["omitted"] is None
    for i in (0, len(rows) // 2, len(rows) - 1):
        assert got["atoms"]["x"][i] == float(rows[i]["Cartn_x"])
        assert got["atoms"]["z"][i] == float(rows[i]["Cartn_z"])
        assert got["atoms"]["chain"][i] == rows[i]["auth_asym_id"]
        assert got["atoms"]["hetero"][i] == (rows[i]["group_PDB"] == "HETATM")
    assert recorded_prepare[0] == "https://files.rcsb.org/download/1I10.cif"

    a = audit(text, sequence_fetcher(lambda url: (FIX / "prepare" / url.rsplit("/", 1)[-1]).read_text()))
    assert got["chains"] == a.chains
    assert [(c["chain"], c["resseq"], c["resname"]) for c in got["catalytic"]] == [
        (c.chain, c.auth_seq_id, c.found) for c in a.catalytic]
    ref = got["catalytic_reference"]
    assert ref["mcsa_id"] == a.reference.mcsa_id and ref["identity"]["value"] == a.reference.identity
    assert ref["identity"]["provenance"]["kind"] == "computed"
    assert "10.1093/nar/gkx1012" in ref["citation"]["text"]
    assert got["catalytic_reason"] is None
    assert got["resolution"]["value"] == a.resolution
    assert got["citation"]["registry"] == "PDB" and got["citation"]["url"]
    # The findings are the ones `caterva prepare 1I10` lists, in its order.
    from caterva.studio.adapters import prepare as prepare_adapter

    ctx = RunContext("20260930-120000-prepare-0badc0de", tmp_path, tmp_path, Progress())
    audited = prepare_adapter.prepare_run({"entry": "1I10"}, ctx).result
    assert got["findings"] == audited["findings"] and len(got["findings"]) == len(a.findings) > 0
    json.dumps(got, allow_nan=False)


def test_an_entry_the_pdb_does_not_have_is_not_found_in_its_words(tmp_path, recorded_prepare):
    with pytest.raises(contract.NotFound, match="not found: https://files.rcsb.org/download/9ZZZ.cif"):
        _coordinates("9zzz", tmp_path)


def test_no_network_is_unavailable_with_the_reason(tmp_path, monkeypatch):
    import requests
    from caterva.prepare import __main__ as prepare

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    def down(url):
        raise requests.ConnectionError("network is unreachable")

    monkeypatch.setattr(prepare, "live_fetch", lambda timeout=60.0: down)
    with pytest.raises(contract.Unavailable, match="could not reach the PDB"):
        _coordinates("1I10", tmp_path)


def test_the_catalytic_residues_are_left_out_with_the_audits_reason_when_uniprot_is_down(tmp_path, monkeypatch):
    import requests
    from caterva.prepare import __main__ as prepare

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    def cif_only(url):
        if url.endswith(".cif"):
            return _cif("1I10")
        raise requests.ConnectionError("UniProt is unreachable")

    monkeypatch.setattr(prepare, "live_fetch", lambda timeout=60.0: cif_only)
    got = _coordinates("1I10", tmp_path)
    assert got["count"] > 0 and got["catalytic"] == []
    assert got["catalytic_reason"].startswith("caterva prepare: could not reach the PDB or UniProt")


def test_a_large_entry_is_cut_to_the_limit_and_says_what_it_left_out(tmp_path, recorded_prepare, monkeypatch):
    """The trimmed 1I10 holds no water, so over the limit the polymer and
    ligand atoms themselves are cut, in file order, and the response says so."""
    full = _coordinates("1I10", tmp_path)
    assert "HOH" not in full["atoms"]["resname"]
    monkeypatch.setattr(contract, "MAX_VIEWER_ATOMS", full["count"] - 1)
    got = _coordinates("1I10", tmp_path)
    assert got["truncated"] is True and got["count"] == full["count"] - 1
    assert got["atoms"]["x"] == full["atoms"]["x"][:-1]
    assert got["omitted"].startswith("0 water and solvent atoms of model 1")
    assert f"and 1 polymer and ligand atoms after the first {full['count'] - 1}" in got["omitted"]


def test_a_query_is_malformed(tmp_path, recorded_prepare):
    with pytest.raises(contract.Malformed):
        _coordinates("1I10", tmp_path, {"model": "2"})
