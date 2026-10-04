"""The resolver's `isoform` argument, on BRENDA's real human-LDH Ki page.

BRENDA 711801 measured gossypol against three human LDH isoforms: 0.0014 mM
(LDH-B), 0.0019 mM (LDH-A), 0.0042 mM (LDH-C). Without an isoform the
resolver returns the first, LDH-B's. Asked for LDH-A it must return LDH-A's;
asked for one BRENDA does not hold, it must refuse and name the three,
rather than return another protein's constant.

The page is the recorded fixture (brenda_ldh_ki_fixture.html), so this runs
offline; UniProt and NCBI are stubbed as in test_agent_architecture_on_real_brenda.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fallback_logic import _partition_variants, _same_isoform, resolve_kinetic_value

FIXTURE = Path(__file__).parent / "fixtures" / "brenda_ldh_ki_fixture.html"


def gossypol(isoform=None, **kw):
    return resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "gossypol", enzyme_name="L-lactate dehydrogenase",
        quantity="ki",
        html_provider=lambda ec: FIXTURE.read_text(encoding="utf-8"),
        uniprot_provider=lambda ec, org: None,
        taxon_id_provider={"Homo sapiens": "9606"}.get,
        search_literature=False,
        isoform=isoform,
        **kw,
    )


def test_without_an_isoform_the_first_ranked_row_is_ldh_b():
    r = gossypol()
    assert r.found and r.value == pytest.approx(0.0014)
    assert r.commentary.startswith("LDH-B")


@pytest.mark.parametrize("asked", ["LDH-A", "ldh-a", "LDH A"])
def test_asking_for_ldh_a_returns_ldh_as_ki(asked):
    r = gossypol(asked)
    assert r.found and r.value == pytest.approx(0.0019)
    assert r.commentary.startswith("LDH-A")
    assert any(f"measuring {asked}" in line for line in r.search_log)


def test_a_name_uniprot_gives_ldh_c_finds_ldh_cs_row():
    """LDH-X is UniProtKB's alternative name for LDHC (the testis subunit), so the request is LDH-C's row."""
    r = gossypol("LDH-X")
    assert r.found and r.value == pytest.approx(0.0042) and r.commentary.startswith("LDH-C")


def test_an_isoform_brenda_does_not_hold_is_refused_and_the_others_named():
    r = gossypol("LDH-Z")
    assert not r.found and r.source == "isoform_withheld"
    assert r.isoforms_available == ["LDH-A", "LDH-B", "LDH-C"]
    assert r.value is None


def test_names_compare_without_case_or_hyphens():
    assert _same_isoform("LDH-A", "ldh a") and not _same_isoform("LDH-A", "LDH-B")
    assert not _same_isoform(None, "LDH-A")


class _Verdict:
    def __init__(self, status, kind):
        self.status, self.kind = status, kind


class _Row:
    def __init__(self, status, kind):
        self.variant = _Verdict(status, kind)


def test_the_isozyme_asked_for_is_not_withheld_as_a_variant():
    # "isoenzyme LDH-A, pH 7.4" is classified a variant (kind isozyme) and
    # withheld by default. When LDH-A is what was asked for, it is the
    # enzyme, not a variant of it; a point mutant is still withheld.
    rows = [_Row("variant", "isozyme"), _Row("variant", "substitution"), _Row("unstated", None)]
    usable, withheld = _partition_variants(rows)
    assert len(usable) == 1 and len(withheld) == 2
    usable, withheld = _partition_variants(rows, keep_isozymes=True)
    assert len(usable) == 2 and [w.variant.kind for w in withheld] == ["substitution"]


# -- Isoform names BRENDA writes with a space ---------------------------------
#
# The committed monoamine oxidase page (Tests/fixtures/ki_mode/, fetched
# 2026-09-29, unmodified) writes one isoform "MAO-A", "MAO A", "isoform MAO A"
# and "monoamine oxidase A". The reader took "isoform MAO A" as "MAO" and the
# rest of the spaced forms as naming no isoform (caterva/bind/core.py).

MAO_PAGE = Path(__file__).parent / "fixtures" / "ki_mode" / "brenda_1.4.3.4.html.gz"


def mao(inhibitor, isoform=None):
    import gzip
    page = gzip.decompress(MAO_PAGE.read_bytes()).decode("utf-8", errors="replace")
    return resolve_kinetic_value(
        "1.4.3.4", "Homo sapiens", inhibitor, quantity="ki",
        html_provider=lambda ec: page,
        uniprot_provider=lambda ec, org: None,
        taxon_id_provider={"Homo sapiens": "9606"}.get,
        search_literature=False,
        isoform=isoform,
    )


def test_clorgyline_for_mao_a_is_the_row_written_isoform_mao_a():
    """Human MAO and clorgyline: two Ki rows. 1.2e-05 mM, ref 742446,
    "isoform MAO A, at pH 7.4 and 37°C"; and 1.28e-06 mM, "pH and temperature
    not specified in the publication", naming no isoform. Read as "MAO", the
    first was some other isoform's, no row named MAO-A, and the one naming
    none, 1.28e-06, was returned with "may or may not have measured it"."""
    r = mao("Clorgyline", "MAO-A")
    assert r.found and r.value == pytest.approx(1.2e-05)
    assert r.commentary == "isoform MAO A, at pH 7.4 and 37°C"
    assert r.citation.reference_id == "742446"
    assert "Kept the 1 of 2 exact-match row(s) measuring MAO-A" in r.search_log
    # Asked for the other isoform, that row is another protein's: the row
    # naming none is kept, and said to be unknown.
    b = mao("Clorgyline", "MAO-B")
    assert b.value == pytest.approx(1.28e-06)
    assert any(line.startswith("No exact-match row names MAO-B") for line in b.search_log)


def test_isatin_for_mao_b_counts_every_spelling_of_mao_b():
    """Isatin's 26 human Ki rows name MAO-B in three spellings; 13 name it,
    where the hyphen-only reader found 10."""
    r = mao("isatin", "MAO-B")
    assert r.found and r.value == pytest.approx(0.00031)
    assert "Kept the 13 of 26 exact-match row(s) measuring MAO-B" in r.search_log


def test_names_compare_as_caterva_compares_them():
    """One function: caterva.bind.core.same_isoform."""
    assert _same_isoform("MAO B", "MAO-B") and _same_isoform("MAOB", "mao-b")
    assert _same_isoform("I and II", "II") and not _same_isoform("I and II", "III")


# -- A request is read as the rows are read ------------------------------------
#
# Potato (Solanum tuberosum) hexokinase on the recorded page
# (Tests/fixtures/recorded/brenda_2.7.1.1.html.gz, unmodified): ref 640239
# writes its three isoforms "HK1", "HK2", "HK3", and the reader spells them
# "HK-1", "HK-2", "HK-3". A request was compared as typed, so "2" (what the
# API sends for "hexokinase isozyme 2") and "hexokinase 2" named none of
# them: the Km for glucose was refused as measured only on other isoforms,
# and the Ki of ADP came from a row naming no isoform (0.04 mM) while HK2's
# own row (0.108 mM) was in the pool.

HK_PAGE = Path(__file__).parent / "fixtures" / "recorded" / "brenda_2.7.1.1.html.gz"


def potato(quantity, compound, isoform):
    import gzip
    page = gzip.decompress(HK_PAGE.read_bytes()).decode("utf-8", errors="replace")
    return resolve_kinetic_value(
        "2.7.1.1", "Solanum tuberosum", compound, enzyme_name="hexokinase", quantity=quantity,
        html_provider=lambda ec: page,
        uniprot_provider=lambda ec, org: None,
        taxon_id_provider={"Solanum tuberosum": "4113"}.get,
        search_literature=False,
        isoform=isoform,
    )


@pytest.mark.parametrize("asked", ["2", "HK2", "HK-2", "hexokinase 2", "isozyme 2"])
def test_every_way_of_asking_for_potato_hk2_finds_its_rows(asked):
    """ADP's six potato Ki rows: 0.04 mM ("HK1"; "hexokinase 1"; none) and
    0.108 / 0.11 mM ("HK2"; "hexokinase 2"; none). Two name HK2."""
    ki = potato("ki", "ADP", asked)
    assert ki.found and ki.value == pytest.approx(0.108) and ki.commentary == "HK2"
    assert ki.citation.reference_id == "640239"
    assert f"Kept the 2 of 6 exact-match row(s) measuring {asked}" in ki.search_log
    km = potato("km", "D-glucose", asked)
    assert km.found and km.value == pytest.approx(0.13) and km.commentary == "HK2"


def test_another_numbering_of_potato_hk2_is_still_refused():
    """"II" is hexokinase II's numbering, which these rows do not use; which
    one a paper meant is not the reader's to assert (caterva/bind/core.py),
    so the refusal names the three BRENDA holds."""
    r = potato("km", "D-glucose", "II")
    assert not r.found and r.source == "isoform_withheld"
    assert r.isoforms_available == ["HK-1", "HK-2", "HK-3"]
