"""A label the chooser offers matches the rows that state that isozyme, on the committed BRENDA pages.

WHY THIS EXISTS
---------------
The isozyme notice and the Studio's isoform chooser offered UniProt entry-name
mnemonics (HXK1, GCK, LDH6A, AOFA). `caterva compose --isoform HXK1` left the
BRENDA rows unchanged (Km 6.0 mM, ref 641068, which names no isozyme) and
the notice went quiet, because the engine that reads a row's commentary
knew the papers' spelling ("hexokinase I") and compared a request with it as
spelled. `caterva/enzymes/isoforms.py` says which names UniProtKB gives one
protein; `bind.core.same_isoform` uses it; these tests hold the result to the
recorded page of BRENDA's EC 2.7.1.1 and the recorded pages of LDH and
monoamine oxidase, row by row.
"""
from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from caterva.bind.core import read_isoform, same_isoform
from caterva.enzymes import isozymes
from caterva.enzymes.isoforms import can_match, equivalent, keys_of, names_for

REPO = Path(__file__).resolve().parents[2]
HEXOKINASE_PAGE = REPO / "Tests" / "fixtures" / "recorded" / "brenda_2.7.1.1.html.gz"


@pytest.mark.parametrize(
    "a, b",
    [
        ("HK1", "hexokinase I"), ("HXK1", "HK-I"), ("hexokinase 1", "HK I"), ("HK-1", "HXK-1"), ("HK-I", "HK-1"),
        ("HK2", "hexokinase II"), ("HXK2", "hexokinase type II"), ("hexokinase-2", "HK-II"),
        ("HK3", "hexokinase III"), ("GCK", "glucokinase"), ("GCK", "HK-IV"), ("glucokinase", "HK-IV"),
        ("HXK4", "hexokinase IV"), ("LDHA", "LDH-A"), ("LDHA", "LDH-M"), ("LDHB", "LDH-H"), ("LDHC", "LDH-X"), ("MAOA", "MAO-A"),
        ("MAOB", "monoamine oxidase B"),
    ],
)
def test_names_uniprot_gives_one_protein_are_one_isoform(a, b):
    assert same_isoform(a, b) and same_isoform(b, a)


@pytest.mark.parametrize(
    "a, b",
    [("HK1", "hexokinase II"), ("HK2", "HK-I"), ("GCK", "HK-III"), ("LDHA", "LDH-B"), ("MAOA", "MAO-B"),
     ("HK2", "hexokinase"), ("HK-2", "II"), ("HK-II", "2"), ("H4", "LDH-B4")],
)
def test_names_of_different_proteins_and_codes_alone_are_still_different(a, b):
    assert not same_isoform(a, b)


def test_every_listed_human_protein_of_ec_2_7_1_1_has_a_gene_symbol_the_engine_knows():
    found = isozymes("2.7.1.1", "human")
    assert [p.gene for p in found.proteins] == ["HKDC1", "HK1", "HK2", "HK3", "GCK"]
    assert [p.symbol for p in found.proteins] == ["HKDC1", "HXK1", "HXK2", "HXK3", "HXK4"], "the mnemonics are not the symbols"
    for protein in found.proteins:
        assert can_match(protein.label), protein.label
        assert protein.names[0] == protein.gene and protein.symbol in names_for(protein.accession, protein.symbol)


def test_a_label_that_names_no_protein_is_known_not_to_match_beyond_spelling():
    assert not can_match("HK9") and not can_match("isozyme zzz")
    assert keys_of("HK9") == {"hk9"}


def test_the_mnemonic_stems_are_names_too_so_what_the_old_notice_offered_still_works():
    for mnemonic, name in [("HXK1", "HK1"), ("AOFA", "MAO-A"), ("AOFB", "MAO-B"), ("LDH6A", "LDHAL6A")]:
        assert same_isoform(mnemonic, name), (mnemonic, name)


# ---------------------------------------------------------------------------
# The recorded BRENDA page for EC 2.7.1.1, row by row
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def human_rows():
    """The human Km, kcat rows of the recorded page: (value, reference, commentary)."""
    from caterva.checkout import LiteratureLayerUnavailable, literature_module

    try:
        brenda_client = literature_module("brenda_client")
    except LiteratureLayerUnavailable:  # pragma: no cover - the wheel
        pytest.skip("the literature layer is not installed")
    html = gzip.decompress(HEXOKINASE_PAGE.read_bytes()).decode("utf-8", errors="replace")
    rows = []
    for label in (brenda_client.KM_TABLE_LABEL, brenda_client.TURNOVER_TABLE_LABEL):
        for row in brenda_client.parse_brenda_km_html(
                html, "glucose", [], target_organism="Homo sapiens", require_substrate_match=False, table_label=label):
            rows.append((label, row.reference_id, row.conditions or ""))
    assert rows, "the recorded page holds human rows"
    return rows


def _named(rows, label):
    return {(t, ref) for t, ref, text in rows if same_isoform(read_isoform(text), label)}


def test_every_name_of_hexokinase_1_finds_the_same_rows_and_none_of_hexokinase_2s(human_rows):
    one = _named(human_rows, "HK1")
    assert one, "the page has human rows that say hexokinase I"
    for label in ("HXK1", "hexokinase 1", "hexokinase I", "HK-I", "hexokinase type I", "HK I"):
        assert _named(human_rows, label) == one, label
    two = _named(human_rows, "HK2")
    assert two and not (one & two)
    for label in ("HXK2", "hexokinase II", "hexokinase 2", "HK II", "hexokinase type II"):
        assert _named(human_rows, label) == two, label
    # The rows BRENDA's page states for hexokinase II are the ones the old spelling alone found.
    assert _named(human_rows, "hexokinase II") == two


def test_before_this_change_the_gene_symbol_found_no_row(human_rows):
    """The defect: only "hexokinase II" matched hexokinase II's row; HK2, HXK2 and the rest found nothing."""
    spelling_only = {
        (t, ref) for t, ref, text in human_rows
        if (read_isoform(text) or "").lower().replace("-", "") == "hkii"}
    assert spelling_only and spelling_only == _named(human_rows, "HK2")
    assert any((read_isoform(text) or "").replace("-", "").lower() == "hki" for _, _, text in human_rows)


def test_glucokinase_finds_the_rows_that_name_it_and_the_others_do_not(human_rows):
    named = _named(human_rows, "GCK")
    assert named == _named(human_rows, "glucokinase") == _named(human_rows, "HXK4") == _named(human_rows, "hexokinase IV")
    assert named.isdisjoint(_named(human_rows, "HK1")) and named.isdisjoint(_named(human_rows, "HK2"))
