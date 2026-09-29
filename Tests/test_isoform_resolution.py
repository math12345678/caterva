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


def test_an_isoform_brenda_does_not_hold_is_refused_and_the_others_named():
    r = gossypol("LDH-X")
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
