"""Tests for evidence_rank.py.

The motivating case is real and is asserted against the actual fixture:
human LDH, where `min()` discards the only STRENDA-complete row in the pool
for one with no commentary at all.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

from brenda_client import BRENDAKmEntry, parse_brenda_km_html, KM_TABLE_LABEL
from evidence_rank import (
    EvidenceProfile,
    describe_discards,
    dominates,
    frontier,
    profile,
)
from protein_variant import classify

sys.path.insert(0, str(pathlib.Path(__file__).parent))


def row(value: float, ph=None, temp=None, commentary=None) -> BRENDAKmEntry:
    return BRENDAKmEntry(
        km_value=value,
        substrate="lactate",
        organism="Homo sapiens",
        conditions=commentary,
        assay_ph=ph,
        assay_temperature_c=temp,
        variant=classify(commentary),
    )


# ---------------------------------------------------------------------------
# The axes
# ---------------------------------------------------------------------------

def test_completeness_reads_both_strenda_fields():
    assert profile(row(1, ph=7.4, temp=37)).completeness == "complete"
    assert profile(row(1, ph=7.4)).completeness == "partial"
    assert profile(row(1, temp=37)).completeness == "partial"
    assert profile(row(1)).completeness == "absent"


def test_variant_statement_orders_saying_over_silence_over_nothing():
    assert profile(row(1, commentary="wild-type enzyme")).variant_statement == "wild_type"
    assert profile(row(1, commentary="pH 7.4, 37C")).variant_statement == "unstated"
    assert profile(row(1, commentary=None)).variant_statement == "absent"


def test_a_profile_offers_no_total():
    # The refusal is load-bearing: a total needs weights, Bakker has not
    # supplied them, and reliabilityScore.ts refuses to produce one for the
    # same reason. Inventing one here would make that refusal incoherent.
    p = profile(row(1, ph=7.4, temp=37))
    assert not hasattr(p, "total")
    assert not hasattr(p, "score")


# ---------------------------------------------------------------------------
# Dominance
# ---------------------------------------------------------------------------

def test_better_on_one_axis_and_equal_elsewhere_dominates():
    complete = profile(row(1, ph=7.4, temp=37, commentary="pH 7.4, 37C"))
    partial = profile(row(2, ph=7.4, commentary="pH 7.4"))
    assert dominates(complete, partial)
    assert not dominates(partial, complete)


def test_neither_dominates_when_each_wins_a_different_axis():
    """The case a weighted score would silently resolve and this will not.

    A fully-described row whose commentary says nothing about the protein,
    against a row that says "wild-type" but reports no conditions. Which is
    better depends on a trade-off nobody has supplied.
    """
    described = profile(row(1, ph=7.4, temp=37, commentary="pH 7.4, 37C"))
    identified = profile(row(2, commentary="wild-type enzyme"))
    assert not dominates(described, identified)
    assert not dominates(identified, described)


def test_identical_profiles_do_not_dominate_each_other():
    # Without the `!=` guard this returns True both ways and `frontier`
    # discards both rows -- the pool empties and the resolver reports
    # nothing found for a system that had candidates.
    a = profile(row(1, ph=7.4, temp=37))
    b = profile(row(2, ph=7.4, temp=37))
    assert not dominates(a, b)
    assert not dominates(b, a)


def test_ordinals_are_never_summed():
    """The integers are ordinal. Their gaps mean nothing.

    Asserted because the temptation to add them is exactly how the invented
    weighting would arrive, and it would look like a refactor.
    """
    import inspect
    import evidence_rank

    source = inspect.getsource(evidence_rank)
    body = source.split('"""', 2)[-1]  # skip the module docstring
    assert "sum(" not in body, "ordinals must not be summed into a total"


# ---------------------------------------------------------------------------
# The frontier
# ---------------------------------------------------------------------------

def test_a_dominated_row_is_removed():
    good = row(0.045, ph=7.4, temp=37, commentary="inhibition assay, pH 7.4, 37C")
    poor = row(0.03, commentary=None)
    kept = frontier([poor, good])
    assert kept == [good]


def test_both_survive_when_neither_dominates():
    described = row(1.0, ph=7.4, temp=37, commentary="pH 7.4, 37C")
    identified = row(2.0, commentary="wild-type enzyme")
    assert len(frontier([described, identified])) == 2


def test_a_single_candidate_is_returned_unchanged():
    # Returning an empty list here would turn "one candidate" into "none".
    only = row(1.0)
    assert frontier([only]) == [only]
    assert frontier([]) == []


def test_the_frontier_is_never_empty():
    rows = [row(1, ph=7.4, temp=37), row(2, ph=7.4, temp=37), row(3)]
    assert frontier(rows)


def test_discards_say_what_beat_them():
    good = row(0.045, ph=7.4, temp=37, commentary="pH 7.4, 37C")
    poor = row(0.03, commentary=None)
    lines = describe_discards([poor, good], frontier([poor, good]))
    assert len(lines) == 1
    assert "0.03" in lines[0]
    assert "assay complete" in lines[0]


def test_nothing_is_reported_when_nothing_was_discarded():
    rows = [row(1, ph=7.4, temp=37), row(2, ph=7.4, temp=37)]
    assert describe_discards(rows, frontier(rows)) == []


# ---------------------------------------------------------------------------
# The real fixture: the case this module was built for
# ---------------------------------------------------------------------------

def test_the_ldh_pool_stops_choosing_the_undocumented_row():
    """Human LDH, this repository's own fixture.

    `min()` picks 0.03 — a row where BRENDA reported no commentary at all —
    over 0.045, the only STRENDA-complete row in the pool. This asserts the
    frontier removes it, and that the surviving choice is the described one.
    """
    html = pathlib.Path(__file__).parent.joinpath(
        "fixtures", "brenda_ldh_fixture.html"
    ).read_text(errors="replace")
    rows = parse_brenda_km_html(
        html, "1.1.1.27", [], target_organism="Homo sapiens",
        require_substrate_match=False, table_label=KM_TABLE_LABEL,
    )
    pool = [r for r in rows if classify(r.conditions).status != "variant"]
    assert len(pool) >= 2, "fixture no longer has a pool to choose from"

    before = min(pool, key=lambda e: e.km_value)
    assert before.assay_ph is None and before.assay_temperature_c is None, (
        "the fixture no longer demonstrates min() selecting an undocumented "
        "row; re-verify before relaxing this"
    )

    kept = frontier(pool)
    after = min(kept, key=lambda e: e.km_value)

    assert after is not before, "the frontier did not change the selection"
    assert after.assay_ph is not None and after.assay_temperature_c is not None, (
        "the new selection is still not STRENDA-complete"
    )
    assert before not in kept, "the undocumented row survived the frontier"


def test_the_frontier_does_not_simply_prefer_larger_numbers():
    """Guards against the laziest possible wrong implementation.

    If `frontier` were `max()` in disguise, the LDH test above would still
    pass. Here the best-evidenced row is also the SMALLEST, so an
    implementation biased toward magnitude in either direction fails.
    """
    best_and_smallest = row(0.01, ph=7.4, temp=37, commentary="wild-type, pH 7.4, 37C")
    worse_and_larger = row(99.0, commentary=None)
    kept = frontier([worse_and_larger, best_and_smallest])
    assert kept == [best_and_smallest]


# ---------------------------------------------------------------------------
# The organism axis, which shipped dead
#
# `profile()` originally read `entry._organism_exact` -- an attribute nothing
# ever set. The axis was the constant True. On the exact-match tier that was
# right by accident; on the cross-species tier it discriminated nothing and
# wrote "organism exact" into the search log for rows measured in a different
# organism than the caller asked about.
#
# These assert the axis reads its argument, and that the summary never claims
# a match that was not checked. The second is the one that matters: a false
# line in the audit trail is worse than a missing one.
# ---------------------------------------------------------------------------

def organism_row(value: float, organism: str) -> BRENDAKmEntry:
    return BRENDAKmEntry(
        km_value=value,
        substrate="lactate",
        organism=organism,
        conditions="pH 7.4, 37C",
        assay_ph=7.4,
        assay_temperature_c=37.0,
        variant=classify("pH 7.4, 37C"),
    )


def test_an_exact_organism_beats_a_cross_species_one():
    mouse = organism_row(1.0, "Mus musculus")
    human = organism_row(2.0, "Homo sapiens")
    assert dominates(
        profile(mouse, "Mus musculus"), profile(human, "Mus musculus")
    )
    assert frontier([human, mouse], "Mus musculus") == [mouse]


def test_the_summary_never_claims_a_match_that_was_not_checked():
    """The false log line this axis shipped with."""
    human = organism_row(1.0, "Homo sapiens")
    assert "organism exact" not in profile(human, "Mus musculus").summary
    assert "cross-species" in profile(human, "Mus musculus").summary


def test_an_unknown_request_is_not_assessed_rather_than_exact():
    human = organism_row(1.0, "Homo sapiens")
    p = profile(human, None)
    assert p.organism_match == "not_assessed"
    assert "not assessed" in p.summary
    assert "organism exact" not in p.summary


def test_not_assessed_neither_beats_nor_loses_to_cross_species():
    """An unasked question must not decide anything.

    `not_assessed` shares an ordinal with `cross_species` so that when the
    requested organism is unknown every row scores identically and the axis
    drops out of the comparison -- rather than silently ranking rows by a
    fact nobody established.
    """
    a = organism_row(1.0, "Homo sapiens")
    b = organism_row(2.0, "Sus scrofa")
    assert len(frontier([a, b], None)) == 2
    assert not dominates(profile(a, None), profile(b, None))


def test_organism_comparison_ignores_case_and_padding():
    row_ = organism_row(1.0, "  homo SAPIENS ")
    assert profile(row_, "Homo sapiens").organism_match == "exact"


def test_a_row_with_no_organism_is_not_assessed():
    blank = BRENDAKmEntry(
        km_value=1.0, substrate="lactate", organism="",
        conditions="pH 7.4, 37C", assay_ph=7.4, assay_temperature_c=37.0,
    )
    assert profile(blank, "Mus musculus").organism_match == "not_assessed"


def test_discards_report_the_organism_honestly():
    mouse = organism_row(1.0, "Mus musculus")
    human = organism_row(2.0, "Homo sapiens")
    kept = frontier([human, mouse], "Mus musculus")
    lines = describe_discards([human, mouse], kept, "Mus musculus")
    assert lines

    # The line names BOTH rows: the discarded one and what beat it. Assert
    # the halves separately -- a blanket "organism exact" not in line was
    # wrong, because the WINNER legitimately is exact and saying so is the
    # point of the message.
    discarded_half, _, winner_half = lines[0].partition("beaten on every axis by one with")
    assert "cross-species" in discarded_half, (
        f"the discarded row's organism was misreported: {discarded_half!r}"
    )
    assert "organism exact" in winner_half, (
        f"the winning row's organism was not named: {winner_half!r}"
    )


def test_a_row_with_no_organism_does_not_outrank_one_that_names_a_different_organism():
    """The mixed case, which the paired-`None` test above cannot reach.

    Within one `frontier()` call every row shares the same
    `requested_organism`, so it is tempting to think `not_assessed` and
    `cross_species` never meet. They do: a row whose OWN organism cell is
    blank is `not_assessed` even when the request is known.

    Giving `not_assessed` its own rank above `cross_species` would then make
    a row that does not say where it came from beat one that says
    "Homo sapiens" — silence outranking a fact. That mutation passed every
    other test in this file.
    """
    blank = BRENDAKmEntry(
        km_value=1.0, substrate="lactate", organism="",
        conditions="pH 7.4, 37C", assay_ph=7.4, assay_temperature_c=37.0,
        variant=classify("pH 7.4, 37C"),
    )
    named_but_different = organism_row(2.0, "Homo sapiens")

    blank_p = profile(blank, "Mus musculus")
    named_p = profile(named_but_different, "Mus musculus")
    assert blank_p.organism_match == "not_assessed"
    assert named_p.organism_match == "cross_species"

    assert not dominates(blank_p, named_p), (
        "a row with no organism outranked one naming a different organism; "
        "silence must not beat a fact"
    )
    assert len(frontier([blank, named_but_different], "Mus musculus")) == 2


# ---------------------------------------------------------------------------
# Relatedness DEPTH: the degree behind ADR 0024's yes/no
#
# The gate asks "shares a class?" and refuses anything that does not. Every
# survivor was then treated as equally related, so for a Mus musculus query a
# Homo sapiens value (shares the superorder Euarchontoglires, depth 10) ranked
# level with a Sus scrofa one (shares only the class Mammalia, depth 7).
# taxonomy.py had already computed both.
# ---------------------------------------------------------------------------

from taxonomy import Relatedness  # noqa: E402


def verdict(candidate: str, shared_rank: str | None) -> Relatedness:
    return Relatedness(
        status="close_enough" if shared_rank else "unknown",
        shared_rank=shared_rank,
        shared_name="x" if shared_rank else None,
        query_organism="Mus musculus",
        candidate_organism=candidate,
        reason="fixture",
    )


def test_a_closer_relative_dominates_a_more_distant_one():
    human = organism_row(1.0, "Homo sapiens")   # superorder, depth 10
    pig = organism_row(2.0, "Sus scrofa")       # class, depth 7
    rel = {
        "Homo sapiens": verdict("Homo sapiens", "superorder"),
        "Sus scrofa": verdict("Sus scrofa", "class"),
    }
    assert dominates(
        profile(human, "Mus musculus", rel), profile(pig, "Mus musculus", rel)
    )
    assert frontier([pig, human], "Mus musculus", rel) == [human]


def test_without_the_verdicts_the_two_are_indistinguishable():
    """What the code did before: the gate's answer was thrown away.

    Asserted so the improvement is a measured difference rather than a
    claim -- if this ever starts discriminating without verdicts, the depth
    is coming from somewhere it should not.
    """
    human = organism_row(1.0, "Homo sapiens")
    pig = organism_row(2.0, "Sus scrofa")
    assert len(frontier([pig, human], "Mus musculus")) == 2


def test_an_unresolved_lineage_is_not_comparable_rather_than_distant():
    """A failed lineage lookup must not read as 'far away'.

    Scoring None as zero would make a row whose lineage did not resolve lose
    to one that merely shares a class -- turning a lookup failure into
    evidence about biology.
    """
    known = organism_row(1.0, "Sus scrofa")
    unresolved = organism_row(2.0, "Rattus norvegicus")
    rel = {
        "Sus scrofa": verdict("Sus scrofa", "class"),
        "Rattus norvegicus": verdict("Rattus norvegicus", None),
    }
    p_known = profile(known, "Mus musculus", rel)
    p_unresolved = profile(unresolved, "Mus musculus", rel)

    assert p_known.relatedness_depth == 7
    assert p_unresolved.relatedness_depth is None
    assert not dominates(p_known, p_unresolved)
    assert not dominates(p_unresolved, p_known)
    assert len(frontier([known, unresolved], "Mus musculus", rel)) == 2


def test_depth_does_not_override_a_worse_assay():
    """Dominance is conjunctive: closer relative, worse description, no win.

    A weighted score would trade these off. Nobody supplied the exchange
    rate, so neither row dominates and both survive to the tie-break.
    """
    close_but_undescribed = BRENDAKmEntry(
        km_value=1.0, substrate="lactate", organism="Homo sapiens",
        conditions=None, variant=classify(None),
    )
    distant_but_described = organism_row(2.0, "Sus scrofa")
    rel = {
        "Homo sapiens": verdict("Homo sapiens", "superorder"),
        "Sus scrofa": verdict("Sus scrofa", "class"),
    }
    assert not dominates(
        profile(close_but_undescribed, "Mus musculus", rel),
        profile(distant_but_described, "Mus musculus", rel),
    )
    assert len(
        frontier([close_but_undescribed, distant_but_described], "Mus musculus", rel)
    ) == 2


def test_two_wholly_incomparable_rows_are_not_ranked(monkeypatch):
    """When NO axis can be compared, nothing dominates.

    The first version of this test built two profiles differing only in
    `relatedness_depth=None` — and never reached the branch, because the
    other three axes always produce a value, so `pairs` was never empty.
    Mutating `if not pairs: return False` to `return True` passed all 29
    tests. Unreachable defensive code, with a test that claimed to cover it.

    Every axis is forced to None here so the branch is actually executed.
    `all([])` is True and `any([])` is False, so the empty case decides
    itself differently depending on which quantifier a future edit writes
    first — which is exactly why it is asserted rather than assumed.
    """
    a = EvidenceProfile(
        completeness="complete", variant_statement="wild_type",
        organism_match="exact", relatedness_depth=None, summary="a",
    )
    b = EvidenceProfile(
        completeness="absent", variant_statement="absent",
        organism_match="cross_species", relatedness_depth=None, summary="b",
    )
    monkeypatch.setattr(
        EvidenceProfile, "ordinals", lambda self: (None, None, None, None)
    )
    assert not dominates(a, b), "an all-incomparable pair must not rank"
    assert not dominates(b, a)


def test_a_partially_comparable_pair_still_ranks():
    """The counterpart. Without it, a `dominates` that always returned False
    would pass the test above."""
    better = EvidenceProfile(
        completeness="complete", variant_statement="wild_type",
        organism_match="exact", relatedness_depth=None, summary="better",
    )
    worse = EvidenceProfile(
        completeness="absent", variant_statement="absent",
        organism_match="cross_species", relatedness_depth=None, summary="worse",
    )
    assert dominates(better, worse)


def test_the_summary_names_the_shared_rank():
    human = organism_row(1.0, "Homo sapiens")
    rel = {"Homo sapiens": verdict("Homo sapiens", "superorder")}
    assert "shares superorder" in profile(human, "Mus musculus", rel).summary


# ---------------------------------------------------------------------------
# How far the relatedness-depth axis actually reaches
#
# ADR 0047 added depth as a fourth axis and justified it with a worked
# example: for a Mus musculus query, Homo sapiens shares the superorder
# Euarchontoglires (depth 10) and Sus scrofa shares only the class Mammalia
# (depth 7), so selection "ranked them level" and depth would fix that.
#
# Measured through the real resolver afterwards, that example does not
# happen. Both facts below were false-in-the-ADR until these tests pinned
# them, and both are pinned rather than quietly corrected because the
# corpus can change and turn either one true.
# ---------------------------------------------------------------------------


def _ldh_row_per_organism(*organisms: str) -> list:
    """One real parsed fixture row for each named organism, in order."""
    html = (
        pathlib.Path(__file__).parent / "fixtures" / "brenda_ldh_fixture.html"
    ).read_text(errors="replace")
    rows = parse_brenda_km_html(
        html, "1.1.1.27", [], target_organism=None,
        require_substrate_match=False, table_label=KM_TABLE_LABEL,
    )
    picked: dict[str, object] = {}
    for entry in rows:
        name = (entry.organism or "").strip()
        if name in organisms and name not in picked:
            picked[name] = entry
    missing = [o for o in organisms if o not in picked]
    assert not missing, (
        f"the LDH fixture no longer contains rows for {missing}; this test "
        "encodes a claim about that fixture and must be re-measured, not "
        "adjusted"
    )
    return [picked[o] for o in organisms]


def test_depth_does_not_break_the_tie_the_adr_said_it_would():
    """ADR 0047's own worked example, run on the real fixture rows.

    Depth changes nothing here, and the reason is not a bug: on the actual
    rows *Sus scrofa* is the better-described measurement (pH 8.5, 25 C ->
    complete) while *Homo sapiens* is the closer organism (superorder ->
    depth 10, against class -> depth 7). Each beats the other on an axis.

    Pareto dominance is therefore *correct* to keep both, and the ADR was
    wrong to imply depth resolves this pair. A weighted score would have
    picked one -- by inventing the exchange rate between "better described"
    and "more closely related" that Bakker was asked for and has not given.

    So this is the honest outcome, and the test exists to stop a future
    change from "fixing" it into a ranking.
    """
    human, pig = _ldh_row_per_organism("Homo sapiens", "Sus scrofa")
    rel = {
        "Homo sapiens": verdict("Homo sapiens", "superorder"),
        "Sus scrofa": verdict("Sus scrofa", "class"),
    }
    human_p = profile(human, "Mus musculus", rel)
    pig_p = profile(pig, "Mus musculus", rel)

    # The premise: they really do differ on both axes, in opposite directions.
    assert human_p.relatedness_depth > pig_p.relatedness_depth
    assert pig_p.completeness == "complete"
    assert human_p.completeness == "partial"

    assert not dominates(human_p, pig_p), "closer organism is not a clean win"
    assert not dominates(pig_p, human_p), "better assay is not a clean win"
    assert len(frontier([human, pig], "Mus musculus", rel)) == 2


def test_no_fixture_pool_reaches_the_frontier_with_two_different_depths(
    monkeypatch,
):
    """A canary. The depth axis fires on nothing in the corpus today.

    Every cross-species pool that survives ADR 0024's gate is
    single-organism, so `relatedness_depth` is identical across the pool and
    drops out of every comparison. The axis is exercised only by the
    synthetic profiles above.

    That is worth pinning rather than deleting, for the reason a concurrent
    agent gave for `selectedForm`: a value that is constant in every fixture
    today is one BRENDA update away from not being. When this test fails,
    the depth axis has started deciding real selections and any golden value
    touching that path must be re-verified rather than adjusted to match.

    The first version of this test asserted on `result.relatedness` -- the
    gate's verdicts -- and failed, because on the LDH km query two depths
    (class and superorder) genuinely do pass the gate. But the deeper of the
    two rows never reaches `frontier`: ADR 0029's variant filter removes the
    *Sus scrofa* row first. Asserting on the verdicts measured a *copy* of
    the pool rather than the pool, which is the recurring defect this
    repository keeps finding in its own verification. It now observes the
    real call.
    """
    import evidence_rank as module
    from fallback_logic import resolve_kinetic_value
    from fixture_lineages import fixture_lineage_provider
    from test_fallback_logic import (
        fake_taxon_id_provider, fake_uniprot_provider, load_fixture,
        make_html_provider,
    )

    cases = [
        ("brenda_ldh_fixture.html", "1.1.1.27", "lactate", "km"),
        ("brenda_ldh_ki_fixture.html", "1.1.1.27", "gossypol", "ki"),
        ("brenda_ldh_kcat_fixture.html", "1.1.1.27", "lactate", "kcat"),
        ("brenda_hexokinase_fixture.html", "2.7.1.1", "glucose", "km"),
    ]
    real_frontier = module.frontier
    seen: list[tuple[str, str, list]] = []
    exercised = []

    for fixture, ec, substrate, quantity in cases:
        pools: list[list] = []

        def capture(entries, requested=None, rel=None, _pools=pools):
            _pools.append(
                sorted(
                    {
                        profile(e, requested, rel).relatedness_depth
                        for e in entries
                    },
                    key=lambda d: (d is None, d),
                )
            )
            return real_frontier(entries, requested, rel)

        monkeypatch.setattr(module, "frontier", capture)
        try:
            resolve_kinetic_value(
                ec, "Mus musculus", substrate,
                html_provider=make_html_provider({ec: load_fixture(fixture)}),
                uniprot_provider=fake_uniprot_provider,
                taxon_id_provider=fake_taxon_id_provider,
                search_literature=False, allow_cross_species=True,
                quantity=quantity, lineage_provider=fixture_lineage_provider,
            )
        finally:
            monkeypatch.setattr(module, "frontier", real_frontier)

        for depths in pools:
            seen.append((fixture, quantity, depths))
            if len([d for d in depths if d is not None]) > 1:
                exercised.append((fixture, quantity, depths))

    # The premise: `frontier` really was reached on the real path. Without
    # this, a resolver that stopped calling it would pass silently -- the
    # exact "computed and never delivered" shape ADR 0047 was written about.
    assert seen, (
        "frontier() was never called by resolve_kinetic_value on any of "
        f"{[c[0] for c in cases]}; this test proves nothing until it is"
    )
    assert not exercised, (
        "the relatedness-depth axis now discriminates on a real query: "
        f"{exercised}. This is not a failure of the axis -- it means ADR "
        "0047's fourth axis has begun affecting selection. Re-verify any "
        "golden value on that path and update the ADR's reach note."
    )
