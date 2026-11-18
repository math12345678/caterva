"""A value carried for a named protein is a row of that protein (compose/protein_rows.py).

Found reviewing the names stream live on 2026-11-12: "SIRT1 kinetics in
human" was GROUNDED on BRENDA ref 739668, a row of UniProt Q8IXJ6 (sirtuin-2);
"HER2 kinase in human" carried IGF1R's Km (P08069); "NDM-1 ... meropenem"
carried VIM-4's (Q8KRJ3); "KPC-2 with imipenem" carried the L1
metallo-beta-lactamase's metal-substituted rows; "ERK2 kinetics in human"
carried a row whose commentary says "activated p38 MAPKalpha". Offline: the
rows are the live ones, served by a stub of `defaults.table_rows`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from caterva.compose import defaults, protein_rows
from caterva.enzymes.symbols import ALIASES_PATH


@dataclass
class _M:
    value: float
    unit: str
    citation: str
    organism: str
    reference_id: str = None


def _model(*tables):
    return SimpleNamespace(resolvable=[SimpleNamespace(parameter_id=f"reaction_{t}", table=t.lower())
                                       for t in tables])


def _serve(monkeypatch, rows):
    """rows: {(table, organism): [_Row, ...]}"""

    def table_rows(ec, table, organism):
        return tuple(r for (t, org), listed in rows.items() if t == table
                     and (organism is None or org == organism) for r in listed)

    monkeypatch.setattr(defaults, "table_rows", table_rows)


def _row(compound, org, conditions, value, ref, uniprot=None):
    return defaults._Row(compound, org, conditions, value, ref, uniprot)


def test_sirt1_is_not_given_sirtuin_2s_row(monkeypatch):
    _serve(monkeypatch, {
        ("km", "Homo sapiens"): [_row("[histone H3]-N6-acetyl-L-lysine9", "Homo sapiens",
                                      "at pH 8.0 and 37°C", 0.019, "739668", "Q8IXJ6")],
        ("kcat", "Homo sapiens"): [_row("[histone H3]-N6-acetyl-L-lysine9", "Homo sapiens",
                                        "at pH 8.0 and 37°C", 0.275, "739668", "Q8IXJ6")],
    })
    measured = {"reaction_Km": _M(0.019, "mM", "BRENDA ref 739668", "Homo sapiens"),
                "reaction_kcat": _M(0.275, "1/s", "BRENDA ref 739668", "Homo sapiens")}
    out = protein_rows.other_protein_withheld(_model("Km", "kcat"), measured, "2.3.1.286", "SIRT1",
                                              "Homo sapiens")
    assert set(out) == {"reaction_Km", "reaction_kcat"}
    assert "Q8IXJ6 (SIRT2)" in out["reaction_Km"]
    # The same row IS sirtuin-2's, and is kept for SIRT2.
    assert protein_rows.other_protein_withheld(_model("Km", "kcat"), measured, "2.3.1.286", "SIRT2",
                                               "Homo sapiens") == {}


def test_her2_is_not_given_the_igf1_receptors_km(monkeypatch):
    _serve(monkeypatch, {("km", "Homo sapiens"): [
        _row("Ac-DYFE-6-chloro-W-NHMe", "Homo sapiens", "pH 7.4, 25°C", 0.0051, "722195", "P08069")]})
    out = protein_rows.other_protein_withheld(
        _model("Km"), {"reaction_Km": _M(0.0051, "mM", "BRENDA ref 722195", "Homo sapiens")},
        "2.7.10.1", "ERBB2", "Homo sapiens")
    assert "P08069 (IGF1R)" in out["reaction_Km"]


def test_hk2_is_not_given_glucokinases_kcat(monkeypatch):
    """Any isoform, typed or read: a row whose accession is another protein of the EC is not it."""
    _serve(monkeypatch, {("kcat", "Homo sapiens"): [
        _row("D-glucose", "Homo sapiens", "pH 7.6, 25°C", 60.4, "703624", "P35557")]})
    out = protein_rows.other_protein_withheld(
        _model("kcat"), {"reaction_kcat": _M(60.4, "1/s", "BRENDA ref 703624", "Homo sapiens")},
        "2.7.1.1", "HK2", "Homo sapiens")
    assert "P35557 (GCK)" in out["reaction_kcat"]


def test_erk2_is_not_given_a_row_that_names_p38_and_p38_is(monkeypatch):
    row = _row("protein ATF2", "Homo sapiens",
               "pH 7.6, 27°C, purified, recombinant detagged, activated p38 MAPKalpha", 0.0019, "663620")
    _serve(monkeypatch, {("km", "Homo sapiens"): [row]})
    measured = {"reaction_Km": _M(0.0019, "mM", "BRENDA ref 663620", "Homo sapiens")}
    erk2 = protein_rows.other_protein_withheld(_model("Km"), measured, "2.7.11.24", "MAPK1", "Homo sapiens")
    assert "does not say it measured MAPK1" in erk2["reaction_Km"]
    assert protein_rows.other_protein_withheld(_model("Km"), measured, "2.7.11.24", "MAPK14",
                                               "Homo sapiens") == {}


def test_a_named_beta_lactamase_takes_only_its_own_rows(monkeypatch):
    vim4 = _row("meropenem", "Pseudomonas aeruginosa", "pH 7.0, 25°C", 0.008, "718584", "Q8KRJ3")
    ndm1 = _row("meropenem", "Klebsiella pneumoniae", "pH 7.5, 30°C", 0.05, "999", "C7C422")
    l1 = _row("Imipenem", "Escherichia coli", "lactamase ZnFe-L1, 25°C, pH 7.0", 0.027, "696320")
    _serve(monkeypatch, {("km", "Pseudomonas aeruginosa"): [vim4], ("km", "Klebsiella pneumoniae"): [ndm1],
                         ("km", "Escherichia coli"): [l1]})
    out = protein_rows.other_protein_withheld(
        _model("Km"), {"reaction_Km": _M(0.008, "mM", "BRENDA ref 718584", "Pseudomonas aeruginosa")},
        "3.5.2.6", "NDM-1", None)
    assert "Q8KRJ3" in out["reaction_Km"] and "C7C422" in out["reaction_Km"]
    assert "Klebsiella pneumoniae (1 km row)" in out["reaction_Km"]
    assert protein_rows.other_protein_withheld(
        _model("Km"), {"reaction_Km": _M(0.05, "mM", "BRENDA ref 999", "Klebsiella pneumoniae")},
        "3.5.2.6", "NDM-1", None) == {}
    kpc = protein_rows.other_protein_withheld(
        _model("Km"), {"reaction_Km": _M(0.027, "mM", "BRENDA ref 696320", "Escherichia coli")},
        "3.5.2.6", "KPC-2", None)
    assert "ZnFe-L1" in kpc["reaction_Km"]


def test_several_accessions_in_one_cell_are_read_apart(monkeypatch):
    row = _row("ampicillin", "Escherichia coli", "pH 7.2", 0.05, "1", "I3VKD5,P62593")
    _serve(monkeypatch, {("km", "Escherichia coli"): [row]})
    assert protein_rows.other_protein_withheld(
        _model("Km"), {"reaction_Km": _M(0.05, "mM", "BRENDA ref 1", "Escherichia coli")},
        "3.5.2.6", "TEM-1", None) == {}


def test_a_restriction_enzyme_is_matched_by_the_row_naming_it(monkeypatch):
    row = _row("ColE1 DNA", "Escherichia coli", "EcoRI, activated by Co2+, 37°C", 0.0004, "134262")
    _serve(monkeypatch, {("km", "Escherichia coli"): [row]})
    measured = {"reaction_Km": _M(0.0004, "mM", "BRENDA ref 134262", "Escherichia coli")}
    assert protein_rows.other_protein_withheld(_model("Km"), measured, "3.1.21.4", "EcoRI", None) == {}
    assert "EcoRV" in protein_rows.other_protein_withheld(_model("Km"), measured, "3.1.21.4", "EcoRV",
                                                          None)["reaction_Km"]


def test_a_row_that_cannot_be_found_or_an_unlisted_protein_is_not_judged(monkeypatch):
    _serve(monkeypatch, {("km", "Homo sapiens"): [
        _row("pyruvate", "Homo sapiens", "", 0.03, "286469")]})
    measured = {"reaction_Km": _M(0.5, "mM", "BRENDA ref 1", "Homo sapiens"),
                "reaction_kcat": _M(9.0, "1/s", "BRENDA ref 2", "Homo sapiens")}
    assert protein_rows.other_protein_withheld(_model("Km", "kcat"), measured, "1.1.1.27", "LDHA",
                                               "Homo sapiens") == {}
    # A row naming no protein, for an isoform whose rows need not name it, is the
    # engine's documented "unknown" case, not withheld here.
    measured = {"reaction_Km": _M(0.03, "mM", "BRENDA ref 286469", "Homo sapiens")}
    assert protein_rows.other_protein_withheld(_model("Km"), measured, "1.1.1.27", "LDHA",
                                               "Homo sapiens") == {}


def test_every_strict_alias_is_marked_with_an_accession_or_a_name():
    rows = json.loads(ALIASES_PATH.read_text())["aliases"]
    strict = [r for r in rows if r.get("rows_must_name_it")]
    assert {"KPC-2", "NDM-1", "OXA-48", "CTX-M-15", "TEM-1", "ERK2", "p38", "SIRT1", "EcoRI"} <= {
        n for r in strict for n in r["names"]}
    for r in strict:
        assert r.get("isoform"), r["names"]
        for acc in r.get("accessions", []):
            assert acc.isalnum() and len(acc) in (6, 10), acc


@pytest.mark.parametrize("text,names,named", [
    ("activated p38 MAPKalpha", ["p38"], True),
    ("p38gamma, pH 7.5", ["p38"], False),
    ("recombinant MAPK14", ["MAPK1"], False),
    ("ERK-2, 30°C", ["ERK2", "ERK-2"], True),
    ("EcoR1, 12 C", ["EcoRI", "EcoR1"], True),
])
def test_naming_is_a_word_of_its_own(text, names, named):
    assert protein_rows._names_it(text, names) is named


def test_a_row_that_names_the_isoform_is_kept_whatever_its_accession_cell_says(monkeypatch):
    """BRENDA ref 702238 files the MAO-A benzylhydrazine Ki under P27338 (MAO-B)."""
    _serve(monkeypatch, {("ki", "Homo sapiens"): [_row(
        "benzylhydrazine", "Homo sapiens",
        "pH 7.5, MAO-A, determined from competitive inhibition data of substrate oxidation at 25°C",
        2.096, "702238", "P27338")]})
    measured = {"reaction_Ki": _M(2.096, "mM", "BRENDA ref 702238", "Homo sapiens")}
    assert protein_rows.other_protein_withheld(_model("Ki"), measured, "1.4.3.4", "MAO-A",
                                               "Homo sapiens") == {}
