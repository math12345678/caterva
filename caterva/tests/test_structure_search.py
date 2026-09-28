"""`caterva structure`, against UniProt and RCSB responses recorded 2026-09-27.

The fixture is the real search for EC 1.1.1.27 in human: five proteins,
55 entries. Replayed, so these tests need no network and cannot drift.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from caterva.structure.chimerax import script
from caterva.structure.search import Http, StructureSearchError, find_structures, matches

FIXTURE = Path(__file__).parent / "fixtures" / "structure" / "ldh_human.json"
CALLS = json.loads(FIXTURE.read_text())["calls"]


def _key(url, payload):
    return hashlib.sha256((url + json.dumps(payload, sort_keys=True)).encode()).hexdigest()[:16]


def _replay(url, payload):
    k = _key(url, payload)
    assert k in CALLS, f"the search made a call the fixture did not record: {url}"
    return CALLS[k]["response"]


REPLAY = Http(get_json=_replay, post_json=_replay)


def _search(**kw):
    return find_structures("1.1.1.27", organism="Homo sapiens", http=REPLAY, **kw)


def test_the_isoforms_are_kept_apart():
    s = _search()
    counts = {p.gene: len(p.structures) for p in s.proteins}
    assert counts == {"LDHA": 46, "LDHB": 7, "LDHC": 2, "LDHAL6A": 0, "LDHAL6B": 0}


def test_an_ec_number_that_is_several_proteins_is_refused_not_guessed():
    s = _search()
    assert s.chosen is None and s.ranked() == ()
    assert "3 different proteins" in s.undecided
    assert "--gene" in s.undecided and "LDHA" in s.undecided and "LDHB" in s.undecided


def test_choosing_by_gene_or_accession_is_the_same_choice():
    by_gene, by_acc = _search(gene="ldha"), _search(uniprot="P00338")
    assert by_gene.chosen.accession == by_acc.chosen.accession == "P00338"
    assert {s.pdb_id for s in by_gene.ranked()} == {s.pdb_id for s in by_acc.ranked()}


def test_a_protein_that_is_not_this_enzyme_is_named_as_such():
    s = _search(gene="GAPDH")
    assert s.chosen is None and "not one of the proteins" in s.undecided


def test_oxamate_finds_oxamic_acid_and_ranks_it_first():
    s = _search(gene="LDHA", ligand="oxamate")
    top = s.ranked()[0]
    assert top.pdb_id == "1I10"
    assert any(b.component == "OXM" and b.role == "ligand" for b in top.bound)


def test_ranking_is_method_then_resolution_without_a_ligand():
    ranked = _search(gene="LDHA").ranked()
    xray = [s.resolution for s in ranked if s.method == "X-RAY DIFFRACTION" and s.resolution]
    assert xray == sorted(xray)


def test_additives_are_not_reported_as_ligands():
    s = _search(gene="LDHA")
    for entry in s.chosen.structures:
        assert not any(b.component in {"GOL", "SO4", "ACT", "DMS", "MLA", "MLI"}
                       for b in entry.with_role("ligand")), entry.pdb_id


def test_nadh_is_a_cofactor():
    top = _search(gene="LDHA", ligand="oxamate").ranked()[0]
    assert "NAI" in {b.component for b in top.with_role("cofactor")}


def test_every_entry_is_cited_by_its_paper_or_by_its_own_doi():
    entries = _search(gene="LDHA").chosen.structures
    unpublished = [e for e in entries if not e.published]
    assert len(unpublished) == 12  # "To Be Published", recorded 2026-09-27
    for e in entries:
        text = e.cite()
        assert "doi:" in text or "PMID" in text, (e.pdb_id, text)
        if not e.published:
            assert text.startswith("unpublished deposition")
            assert f"doi:10.2210/pdb{e.pdb_id.lower()}/pdb" in text
            assert "To Be Published" not in text


@pytest.mark.parametrize("asked, component, name, expected", [
    ("oxamate", "OXM", "OXAMIC ACID", True),
    ("pyruvic acid", "PYR", "PYRUVATE", True),
    ("OXM", "OXM", "OXAMIC ACID", True),
    ("lactate", "OXM", "OXAMIC ACID", False),
])
def test_name_matching_folds_only_the_acid_and_its_salt(asked, component, name, expected):
    from caterva.structure.search import BoundMolecule

    assert matches(BoundMolecule(component, name, "ligand"), asked) is expected


def test_the_chimerax_script_shows_the_ligand_and_hides_additives():
    s = _search(gene="LDHA", ligand="oxamate")
    text = script(s.ranked()[0], s.chosen, focus="oxamate")
    assert "open 1i10" in text
    assert "show :OXM" in text and "view :OXM" in text
    assert "hide :ACT" in text
    assert "doi:10.1002/pro.3943" in text and "doi:10.1093/nar/28.1.235" in text
    assert "NOTE" not in text


def test_the_script_says_when_the_ligand_is_not_there():
    s = _search(gene="LDHA")
    entry = next(e for e in s.ranked() if not e.binds("oxamate"))
    assert "NOTE: 'oxamate' is not bound in this entry" in script(entry, s.chosen, focus="oxamate")


def test_a_network_failure_is_a_refusal_with_a_reason():
    def down(url, payload):
        raise ConnectionError("no route to host")

    with pytest.raises(StructureSearchError, match="could not run: ConnectionError"):
        find_structures("1.1.1.27", http=Http(down, down))
