"""A miss that tells you what you could have asked for.

THE MEASUREMENT
---------------
Through the real resolver, on the LDH fixture:

    substrate="lactate"    -> found=True, 10.73
    substrate="L-lactate"  -> found=False, source="not_found"

Both name the same compound. BRENDA's label is `(S)-lactate`: "lactate"
matches as a substring, "L-lactate" does not. A student reasonably concludes
BRENDA has no lactate dehydrogenase data, and the data is right there.

ADR 0024 already fixed this for ORGANISMS — a withheld cross-species result
names which organisms held values, "so the opt-in can actually be
exercised". It was never applied to substrates, which is the field a student
is far more likely to get wrong: an organism has one binomial name, a
metabolite has a dozen aliases.
"""
from __future__ import annotations

import pytest

from brenda_client import KM_TABLE_LABEL
from fallback_logic import (
    KineticResult,
    _nothing_matched,
    resolve_kinetic_value,
    substrates_present,
)
from fixture_lineages import fixture_lineage_provider
from test_fallback_logic import (
    fake_taxon_id_provider,
    fake_uniprot_provider,
    load_fixture,
    make_html_provider,
)

LDH = "1.1.1.27"


def ldh_provider():
    return make_html_provider({LDH: load_fixture("brenda_ldh_fixture.html")})


def ask(substrate: str, organism: str = "Homo sapiens") -> KineticResult:
    return resolve_kinetic_value(
        LDH, organism, substrate,
        html_provider=ldh_provider(),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        allow_cross_species=False,
        quantity="km",
        lineage_provider=fixture_lineage_provider,
    )


# ---------------------------------------------------------------------------
# The measurement this exists for
# ---------------------------------------------------------------------------


def test_the_synonym_that_missed_now_says_what_the_table_holds():
    result = ask("L-lactate")
    assert not result.found
    assert result.source == "not_found"
    assert "(S)-lactate" in result.substrates_available, (
        "the label that would have worked is not named, so the student has "
        "no way to discover it"
    )


def test_the_substring_that_worked_still_works():
    """The pair is the point: one string resolves and its synonym does not,
    which is what makes the miss so misleading."""
    assert ask("lactate").found
    assert not ask("L-lactate").found


def test_nothing_is_substituted():
    """A list, not a match.

    Silently resolving "L-lactate" to the `(S)-lactate` row would return a
    measurement of a compound the student did not name, on the reasoning
    that the names look similar — ADR 0024's cross-species error in another
    costume. `expand_substrates_with_synonyms` exists and was deliberately
    not wired here: a PubChem synonym list can carry a salt, a stereoisomer
    or an ester, and any of those is a different molecule.
    """
    result = ask("L-lactate")
    assert result.value is None
    assert result.found is False


def test_the_list_is_real_labels_from_the_table():
    """Not guessed, not a synonym set — what the fetched HTML contains."""
    available = substrates_present(LDH, ldh_provider())
    assert available == ["(S)-lactate", "NAD+", "oxamate", "pyruvate"]


# ---------------------------------------------------------------------------
# When it must stay quiet
# ---------------------------------------------------------------------------


def test_a_found_result_does_not_pay_for_the_list():
    """Building it costs a second parse of the table, and a reader who got
    an answer does not need it."""
    result = ask("lactate")
    assert result.found
    assert result.substrates_available == []


def test_a_miss_that_is_not_about_the_substrate_stays_silent():
    """The substrate IS in the table; the organism is what failed."""
    result = ask("pyruvate", organism="Danio rerio")
    assert not result.found
    assert result.substrates_available == []


def test_the_suppression_guard_is_tested_where_it_lives():
    """The test above passes for the wrong reason, and mutation proved it.

    Deleting the guard that suppresses the hint when the requested
    substrate IS present broke nothing: `pyruvate` in *Danio rerio*
    returns `cross_species_withheld`, a branch that never calls this
    helper, so the assertion above was about the source branch and not
    about the guard it names.

    Naming the substrate list when the substrate was fine points a reader
    at the wrong thing — the cry-wolf shape ADR 0028 describes, where a
    hint that fires on the wrong case gets ignored on the right one. So it
    is asserted directly.
    """
    log: list[str] = []
    present = _nothing_matched(LDH, "pyruvate", ldh_provider(), KM_TABLE_LABEL, log)
    assert present == [], "the substrate was present; there is nothing to suggest"
    assert log == [], "and nothing should have been said about it"

    absent = _nothing_matched(LDH, "L-lactate", ldh_provider(), KM_TABLE_LABEL, log)
    assert "(S)-lactate" in absent, "the helper must still fire on a real miss"


def test_the_guard_is_case_insensitive_on_BOTH_sides():
    """`nad+` and BRENDA's `NAD+` are the same request.

    The first version of this test asked for `PYRUVATE`, and mutation
    showed it was worth nothing: the label is already lower-case, so
    `asked == label` and `asked == label.lower()` agree and dropping the
    `.lower()` on the label side broke nothing. `NAD+` is the label that
    actually carries capitals, so it is the one that exercises it.
    """
    log: list[str] = []
    assert _nothing_matched(LDH, "nad+", ldh_provider(), KM_TABLE_LABEL, log) == [], (
        "asking for 'nad+' when the table says 'NAD+' is not a substrate miss"
    )
    assert _nothing_matched(LDH, "PYRUVATE", ldh_provider(), KM_TABLE_LABEL, log) == []


def test_the_diagnostic_reparse_cannot_turn_a_miss_into_a_crash():
    """This runs on a path that has ALREADY failed.

    A diagnostic that raises has replaced "no value found" with a stack
    trace, which is strictly worse for the person it was written for.

    The first version of this test handed in a provider that raised
    immediately, and it failed — correctly. An unreachable BRENDA raises in
    the MAIN fetch, long before any of this, and that is the resolver
    behaving properly. The case this guards is narrower and real: the
    lookup succeeded, and the SECOND parse, the one added for the hint,
    goes wrong.
    """
    good = load_fixture("brenda_ldh_fixture.html")
    calls = {"n": 0}

    # A substrate miss reads the table three times: the exact-organism
    # tier, the cross-species tier, and then this hint. Measured rather
    # than assumed — the first attempt failed on call two, which is the
    # cross-species fetch and not the diagnostic at all.
    DIAGNOSTIC_READ = 3

    def fails_on_the_second_read(_ec: str) -> str:
        calls["n"] += 1
        if calls["n"] < DIAGNOSTIC_READ:
            return good
        raise RuntimeError("connection reset while re-reading the table")

    result = resolve_kinetic_value(
        LDH, "Homo sapiens", "L-lactate",
        html_provider=fails_on_the_second_read,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        allow_cross_species=False,
        quantity="km",
        lineage_provider=fixture_lineage_provider,
    )
    assert not result.found
    assert result.substrates_available == []
    assert any("Could not list the substrates" in line for line in result.search_log), (
        "the hint failed silently; a reader should be told why it is absent"
    )


def test_an_enzyme_whose_table_is_empty_says_nothing_rather_than_an_empty_list():
    """An empty suggestion list rendered as "this enzyme reports: " would be
    worse than silence."""
    empty = make_html_provider({LDH: "<html><body>no tables here</body></html>"})
    assert substrates_present(LDH, empty) == []


# ---------------------------------------------------------------------------
# The sentence a reader actually gets
# ---------------------------------------------------------------------------


def test_the_log_names_the_labels_and_refuses_to_substitute():
    joined = " ".join(ask("L-lactate").search_log)
    assert "(S)-lactate" in joined
    assert "does not substitute one substrate for another" in joined


@pytest.mark.parametrize("substrate", ["L-lactate", "lactic acid", "L-lactic acid"])
def test_the_aliases_a_student_would_plausibly_type_all_get_help(substrate):
    """Three spellings of the same compound, none of which BRENDA uses.

    Parametrised because the defect is not about one string: it is about
    every reasonable name for a metabolite whose label happens to carry a
    stereo-descriptor.
    """
    result = ask(substrate)
    assert not result.found
    assert "(S)-lactate" in result.substrates_available
