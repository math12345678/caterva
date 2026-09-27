"""
Stage 5 Part 2: the golden set.

Rule 1 for provenance (Stage 4 close, question 3): the numeric side has
closed forms; the provenance side needs an equivalent — a golden set of
hand-verified enzyme/substrate/Km/citation tuples asserted end to end
(plus the Ki pairs added for the competitive-inhibition domain, which
carry their own quantity="ki" resolution and citation).

These tuples were hand-verified against primary literature through the
BRENDA fixture HTML (the fixture files were previously captured from live
BRENDA and verified row-by-row; see the *_realrows_debug.py scripts).

Every tuple is asserted in full: value, unit, organism, source tier,
citation reference id, citation URL, and the cross-species flag. If the
resolution chain ever returns a plausible-but-wrong value (wrong organism
row, wrong substrate, flagged row surfacing), this table fails.

The mutation proof (question 4) is documented in STAGE_05_PART_02.md:
mutating the row selection in fallback_logic.py makes this suite fail, and
reverting the mutation makes it pass again.
"""

import pathlib
import os

import pytest

from fixture_lineages import fixture_lineage_provider
from fallback_logic import KineticResult, resolve_kinetic_value

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Real UniProt accessions / NCBI taxon IDs, previously verified (mirrors
# test_fallback_logic.py).
FAKE_UNIPROT_BY_EC = {
    "1.1.1.27": "P00338",
    "3.1.1.7": "P22303",
}
FAKE_TAXON_IDS = {
    "Homo sapiens": "9606",
    "Mus musculus": "10090",
    "Sus scrofa": "9823",
}


def fake_uniprot_provider(ec_number: str, taxon_id: str):
    return FAKE_UNIPROT_BY_EC.get(ec_number)


def fake_taxon_id_provider(organism_name: str):
    return FAKE_TAXON_IDS.get(organism_name)


def make_html_provider(fixture_name: str):
    def provider(ec_number: str) -> str:
        with open(os.path.join(FIXTURES_DIR, fixture_name), encoding="utf-8") as f:
            return f.read()

    return provider


# ---------------------------------------------------------------------------
# The golden set. Fields: ec, substrate, organism, km, unit, source tier,
# citation ref, cross_species_flag. Hand-verified against the BRENDA
# fixtures (which are captures of real BRENDA rows).
#
# EVERY TUPLE CARRIES `verified_on`, AND THAT IS NOT BOOKKEEPING.
#
# This is Caterva's ground truth. Every claim the project makes about
# resolving real values traces back to these numbers, and until now nothing
# recorded WHEN they were last checked against BRENDA, or ever asked.
#
# BRENDA is curated continuously. A reference id can be superseded, a row
# can be corrected, an organism assignment can change. None of that would
# fail a single test here, because these assertions compare the resolver
# against a FIXTURE -- a photograph of BRENDA taken in July 2026. The
# fixture and the resolver would agree with each other forever while both
# drifted away from the database they claim to represent.
#
# That is the "check that cannot fail" shape, one level below the code:
# ground truth that silently ages while everything downstream keeps
# reporting "verified".
#
# `scripts/check_golden_freshness.py` reads these dates and says how old
# they are. It checks AGE, NOT CORRECTNESS -- age is a proxy, and the script
# says so itself rather than letting a green tick imply more than it means.
# The golden data lives in Tests/golden_set.py so that guards and the
# live verifier can read it without importing pytest. See that module.
from golden_set import FIXTURES_CAPTURED, GOLDEN  # noqa: E402

__all__ = ["FIXTURES_CAPTURED", "GOLDEN"]


def _resolve(entry) -> KineticResult:
    return resolve_kinetic_value(
        entry["ec"],
        entry["organism"],
        entry["substrate"],
        html_provider=make_html_provider(entry["fixture"]),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity=entry.get("quantity", "km"),
        allow_cross_species=entry.get("allow_cross_species", False),
        allow_variants=entry.get("allow_variants", False),
        lineage_provider=fixture_lineage_provider,
    )


@pytest.mark.parametrize("entry", GOLDEN, ids=lambda e: e["id"])
def test_golden_tuple_end_to_end(entry):
    expected = entry["expected"]
    result = _resolve(entry)

    assert result.found is True, f"{entry['id']}: not found"
    assert result.value == pytest.approx(expected["km"]), (
        f"{entry['id']}: value {result.value} != golden {expected['km']} — "
        "a plausible-but-wrong row may have been selected"
    )
    assert result.unit == expected["unit"]
    assert result.organism == expected["organism"]
    assert result.source == expected["source"]
    assert result.cross_species_flag is expected["cross_species_flag"]

    assert result.citation is not None, f"{entry['id']}: no citation"
    assert result.citation.source == "BRENDA"
    assert result.citation.reference_id == expected["ref"]
    assert result.citation.url is not None, f"{entry['id']}: no citation URL"


@pytest.mark.parametrize("entry", GOLDEN, ids=lambda e: e["id"])
def test_golden_citation_is_locatable(entry):
    result = _resolve(entry)
    assert result.citation is not None
    ref = result.citation.reference_id
    url = result.citation.url
    assert (ref is not None and ref != "n/a") or (url is not None), (
        f"{entry['id']}: citation has no locator"
    )


@pytest.mark.parametrize(
    "entry",
    [e for e in GOLDEN if e.get("allow_cross_species")],
    ids=lambda e: e["id"],
)
def test_cross_species_golden_tuples_withhold_by_default(entry):
    """The same tuple, without the opt-in, must return nothing.

    Kept as a golden test rather than a unit test because the point is
    about these specific real BRENDA rows: a pig Km offered for a mouse,
    and a Plasmodium falciparum Ki offered for a mouse. Both were returned
    automatically before ADR 0024.
    """
    result = resolve_kinetic_value(
        entry["ec"],
        entry["organism"],
        entry["substrate"],
        html_provider=make_html_provider(entry["fixture"]),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity=entry.get("quantity", "km"),
        lineage_provider=fixture_lineage_provider,
    )
    assert result.found is False
    assert result.source == "cross_species_withheld"
    assert result.value is None
    # The organism the old code would have silently substituted is named,
    # not hidden -- that is what makes the opt-in a real choice.
    assert entry["expected"]["organism"] in result.cross_species_organisms_available


@pytest.mark.parametrize(
    "entry",
    [e for e in GOLDEN if e["expected"].get("rejected_organisms")],
    ids=lambda e: e["id"],
)
def test_golden_relatedness_rejections_are_reported(entry):
    """The organisms the filter dropped must appear in the result.

    A filter that reports only survivors is unauditable: a reader cannot
    tell whether Plasmodium was excluded on principle or simply absent from
    BRENDA that day, and those are very different facts about the answer
    they are being given.
    """
    result = _resolve(entry)
    rejected = {v.candidate_organism for v in result.relatedness
                if v.status == "too_distant"}
    assert rejected == entry["expected"]["rejected_organisms"]

    accepted = {v.candidate_organism for v in result.relatedness
                if v.status == "close_enough"}
    assert result.organism in accepted


@pytest.mark.parametrize(
    "entry",
    [e for e in GOLDEN if e.get("allow_variants")],
    ids=lambda e: e["id"],
)
def test_variant_golden_tuples_resolve_differently_by_default(entry):
    """Without the opt-in, the same query returns a DIFFERENT row.

    This is the concrete cost of the defect ADR 0029 fixes, in one number.

    G3's winning row was `pH 8.5, 25°C, isozyme H4` at 0.0026 mM. LDH's H4
    and M4 isozymes have genuinely different kinetics, and a plain "lactate
    dehydrogenase" query did not ask for one of them — but it got one, with
    a real citation, and nothing in the output said so.

    With variant rows excluded from selection the same query resolves to
    10.73 mM: about four thousand times larger. A student comparing the two
    would not be looking at measurement noise, they would be looking at two
    different proteins.

    `variant_withheld` is NOT expected here, and that distinction matters: it
    fires only when EVERY candidate is a variant. When usable rows remain,
    the right behaviour is to use them, not to refuse.
    """
    with_variants = _resolve(entry)
    without = resolve_kinetic_value(
        entry["ec"],
        entry["organism"],
        entry["substrate"],
        html_provider=make_html_provider(entry["fixture"]),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity=entry.get("quantity", "km"),
        allow_cross_species=entry.get("allow_cross_species", False),
        lineage_provider=fixture_lineage_provider,
    )

    assert with_variants.found is True
    assert without.found is True, (
        "usable non-variant rows remained, so the resolver should have used "
        "them rather than refusing"
    )
    assert without.value != with_variants.value, (
        "excluding variant rows changed nothing; the filter is not reaching "
        "the selection"
    )
    # And the log has to say what was removed, or the change is invisible.
    assert any("protein variant" in line for line in without.search_log)


def test_variant_withheld_only_when_every_candidate_is_a_variant():
    """The AChE turnover table is 35/72 mutants — but not 72/72.

    Asserting the `variant_withheld` path needs a pool where nothing
    survives, which is constructed here rather than hoped for. The earlier
    version of this test assumed G3 would refuse; it did not, because two
    usable rows remained, and assuming would have shipped an assertion that
    passed for the wrong reason.
    """
    from brenda_client import BRENDAKmEntry
    from protein_variant import classify
    from fallback_logic import _partition_variants, _variant_withheld_result

    rows = [
        BRENDAKmEntry(
            km_value=v, substrate="lactate", organism="Homo sapiens",
            conditions=c, variant=classify(c),
        )
        for v, c in [(0.1, "Y124C mutant"), (0.2, "pH 8.5, 25C, isozyme H4")]
    ]
    usable, withheld = _partition_variants(rows)
    assert usable == []
    assert len(withheld) == 2

    log: list[str] = []
    result = _variant_withheld_result(withheld, log)
    assert result.found is False
    assert result.source == "variant_withheld"
    assert set(result.variant_candidates_available) == {"Y124C", "isozyme H4"}
    assert any("withheld" in line for line in log)


# ---------------------------------------------------------------------------
# Ground truth has to say when it was last true
# ---------------------------------------------------------------------------

def test_every_golden_tuple_records_when_it_was_verified():
    """A tuple with no verification date cannot be assessed for staleness at
    all, which is worse than an old one: an old date is a known quantity.

    This is a TEST rather than only a guard because adding a tuple is when
    the date is cheapest to supply and easiest to forget. The guard
    (scripts/check_golden_freshness.py) answers "should someone look?"; this
    answers "did you say when?", and only the second belongs in the suite.
    """
    import datetime as _dt

    for entry in GOLDEN:
        assert "verified_on" in entry, f"{entry['id']} has no verified_on"
        # Parsed, not merely present. A date nothing can read is decoration.
        _dt.date.fromisoformat(entry["verified_on"])


def test_the_freshness_guard_and_the_golden_set_agree_on_the_tuples():
    """The guard parses this file with a regex. If the file's shape changes
    -- a renamed key, a restructure -- the guard would silently examine
    nothing and report OK.

    It refuses to report success on an empty set for exactly that reason,
    and this asserts the two stay in step, so a restructure fails here
    rather than quietly disarming the guard.
    """
    import subprocess
    import sys as _sys

    result = subprocess.run(
        [_sys.executable, str(pathlib.Path(__file__).parent.parent
                              / "scripts" / "check_golden_freshness.py")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # Every tuple this file defines must appear in the guard's report.
    for entry in GOLDEN:
        assert entry["id"] in result.stdout, (
            f"{entry['id']} is in the golden set but the freshness guard did "
            "not see it -- the guard's parser and this file have drifted"
        )
