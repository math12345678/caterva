"""The resolver's `inhibition_mode` argument, on BRENDA's real pages.

BRENDA ref 739793 gives human LDH two Ki values for one quinoline
sulfonamide, from one paper: 0.00059 mM "competitive versus NADH" and
0.00252 mM "noncompetitive versus pyruvate". Without a mode the resolver
returns the lower, whatever model the caller is building. With the model's
mode it must return the row `caterva compose` would carry for that model,
by the same ranking (caterva.compose.ki_mode.rank), and refuse, naming the
modes, when every row states another.

Every page is a committed, unmodified BRENDA page, so this runs offline:

- LDH (1.1.1.27) and monoamine oxidase (1.4.3.4):
  Tests/fixtures/ki_mode/, fetched 2026-09-29 (README there has the hashes);
- hexokinase (2.7.1.1): Tests/fixtures/recorded/brenda_2.7.1.1.html.gz, the
  page the API tests replay, which holds rabbit MgADP-'s two mixed rows.

The LDH page carries six bytes that are not UTF-8; it is decoded with
errors="replace", as `requests` decodes the live page (ki_mode/README.md).
UniProt and NCBI are stubbed as in test_isoform_resolution.
"""
from __future__ import annotations

import functools
import gzip
from pathlib import Path

import pytest

import fallback_logic
from brenda_client import KI_TABLE_LABEL
from fallback_logic import (
    _brenda_entries,
    _naming_no_isoform,
    _partition_mode,
    resolve_kinetic_value,
)
from fixture_lineages import fixture_lineage_provider

FIXTURES = Path(__file__).parent / "fixtures"


def _page(path: Path) -> str:
    return gzip.decompress(path.read_bytes()).decode("utf-8", errors="replace")


PAGES = {
    "1.1.1.27": _page(FIXTURES / "ki_mode" / "brenda_1.1.1.27.html.gz"),
    "1.4.3.4": _page(FIXTURES / "ki_mode" / "brenda_1.4.3.4.html.gz"),
    "2.7.1.1": _page(FIXTURES / "recorded" / "brenda_2.7.1.1.html.gz"),
}
TAXA = {"Homo sapiens": "9606", "Oryctolagus cuniculus": "9986", "Mus musculus": "10090",
        "Trypanosoma cruzi": "5693"}

QUINOLINE = "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid"
COMPETITIVE_VS_NADH = ("pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate reduction, "
                       "competitive versus NADH")
NONCOMPETITIVE_VS_PYRUVATE = ("pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate reduction, "
                              "noncompetitive versus pyruvate")


def ki(ec, inhibitor, organism="Homo sapiens", **kw):
    kw.setdefault("quantity", "ki")
    return resolve_kinetic_value(
        ec, organism, inhibitor,
        html_provider=PAGES.__getitem__,
        uniprot_provider=lambda ec_, org: None,
        taxon_id_provider=TAXA.get,
        search_literature=False,
        **kw,
    )


@functools.lru_cache(maxsize=None)
def plain(ec, inhibitor, organism):
    """The no-mode answer, computed once per inhibitor: parsing the
    monoamine oxidase page takes about two seconds, and the comparison
    below asks for one inhibitor's answer up to nine times."""
    return ki(ec, inhibitor, organism=organism)


def ldh(**kw):
    return ki("1.1.1.27", QUINOLINE, model_substrate="pyruvate", **kw)


class TestTheQuinolineSulfonamide:
    def test_without_a_mode_the_lower_value_is_returned_as_before(self):
        r = ldh()
        assert r.found and r.value == 0.00059 and r.commentary == COMPETITIVE_VS_NADH

    def test_a_noncompetitive_model_gets_the_noncompetitive_row(self):
        r = ldh(inhibition_mode="noncompetitive")
        assert r.found and r.source == "brenda_exact"
        assert r.value == 0.00252 and r.commentary == NONCOMPETITIVE_VS_PYRUVATE
        assert r.citation.reference_id == "739793"
        assert ("Kept the 1 of 2 exact-match row(s) stating noncompetitive inhibition versus "
                "pyruvate, the model's substrate") in r.search_log
        # The ensemble and the tie are of the rows kept: the competitive
        # constant is not offered as an equally good alternative.
        assert [c["value"] for c in r.ensemble_candidates] == [0.00252]

    def test_a_competitive_model_keeps_the_competitive_row_and_says_what_it_measured(self):
        r = ldh(inhibition_mode="competitive")
        assert r.found and r.value == 0.00059 and r.commentary == COMPETITIVE_VS_NADH
        assert ("Kept the 1 of 2 exact-match row(s) stating competitive inhibition, measured "
                "versus another molecule than pyruvate, the model's substrate") in r.search_log

    def test_an_uncompetitive_model_is_refused_and_the_modes_named(self):
        r = ldh(inhibition_mode="uncompetitive")
        assert not r.found and r.value is None
        assert r.source == "mode_withheld"
        assert r.modes_available == ["competitive inhibition versus NADH",
                                     "noncompetitive inhibition versus pyruvate"]
        assert r.search_log[-1].startswith(
            "Every candidate row states an inhibition mode other than uncompetitive")

    def test_the_cross_species_tier_chooses_by_mode_too(self):
        """Asked for mouse, BRENDA holds this Ki for human only; with the
        opt-in and a related organism, the human rows are chosen among by
        the same rule."""
        r = ki("1.1.1.27", QUINOLINE, organism="Mus musculus", allow_cross_species=True,
               lineage_provider=fixture_lineage_provider, inhibition_mode="noncompetitive",
               model_substrate="pyruvate")
        assert r.found and r.source == "brenda_cross_species"
        assert r.value == 0.00252 and r.organism == "Homo sapiens"
        assert any(line.startswith("Kept the 1 of 2 cross-species row(s)") for line in r.search_log)
        refused = ki("1.1.1.27", QUINOLINE, organism="Mus musculus", allow_cross_species=True,
                     lineage_provider=fixture_lineage_provider, inhibition_mode="uncompetitive")
        assert refused.source == "mode_withheld" and len(refused.modes_available) == 2


class TestNoStatedMode:
    def test_gossypol_is_unchanged_and_the_log_says_why(self):
        # BRENDA 711801: three rows, one per isoform, none stating a mode.
        r = ki("1.1.1.27", "gossypol", inhibition_mode="competitive", model_substrate="pyruvate")
        assert r.found and r.value == 0.0014 and r.commentary.startswith("LDH-B")
        assert ("No exact-match row states competitive inhibition; kept the 3 of 3 exact-match "
                "row(s) stating no mode, so whether the value is the competitive constant is "
                "unknown") in r.search_log

    def test_with_an_isoform_the_isoforms_row(self):
        r = ki("1.1.1.27", "gossypol", inhibition_mode="competitive", isoform="LDH-A")
        assert r.found and r.value == 0.0019 and r.commentary.startswith("LDH-A")


class TestMixed:
    """Rabbit erythrocyte hexokinase and MgADP-, BRENDA ref 640206: 3 mM
    "mixed inhibitor versus MgATP2-" and 7.8 mM "mixed inhibitor versus
    glucose", the only mixed Ki rows in the repository's BRENDA pages."""

    RABBIT = dict(organism="Oryctolagus cuniculus")

    def test_without_a_mode_the_versus_mgatp_row(self):
        assert ki("2.7.1.1", "MgADP-", **self.RABBIT).value == 3.0

    def test_a_competitive_model_is_refused(self):
        r = ki("2.7.1.1", "MgADP-", inhibition_mode="competitive", model_substrate="glucose",
               **self.RABBIT)
        assert r.source == "mode_withheld"
        assert r.modes_available == ["mixed inhibition versus MgATP2-",
                                     "mixed inhibition versus glucose"]

    @pytest.mark.parametrize("substrate, value", [("glucose", 7.8), ("MgATP2-", 3.0)])
    def test_a_noncompetitive_model_takes_the_row_versus_its_substrate(self, substrate, value):
        r = ki("2.7.1.1", "MgADP-", inhibition_mode="noncompetitive", model_substrate=substrate,
               **self.RABBIT)
        assert r.found and r.value == value
        assert r.commentary.endswith(f"versus {substrate}")

    def test_naming_no_substrate_leaves_the_two_ranked_alike(self):
        r = ki("2.7.1.1", "MgADP-", inhibition_mode="noncompetitive", **self.RABBIT)
        assert r.value == 3.0
        assert sorted(c["value"] for c in r.ensemble_candidates) == [3.0, 7.8]


class TestIsoformThenMode:
    """Human monoamine oxidase and two hydrazines, BRENDA ref 702238 (Binda
    et al. 2008, Biochemistry 47:5616): rows that name an isoform and a
    mode, and Kitz-Wilson rows, which are irreversible inactivation
    constants filed as Ki."""

    def test_the_isoforms_competitive_row(self):
        r = ki("1.4.3.4", "benzylhydrazine", inhibition_mode="competitive", isoform="MAO-A")
        assert r.found and r.value == 2.096 and "MAO-A" in r.commentary
        assert "Kept the 2 of 4 exact-match row(s) measuring MAO-A" in r.search_log
        # Counted among the rows measuring MAO-A, as the isoform step's own
        # line counts them.
        assert ("Kept the 1 of 2 exact-match row(s) measuring MAO-A, stating competitive "
                "inhibition") in r.search_log

    def test_without_the_isoform_either_isoforms_competitive_row(self):
        r = ki("1.4.3.4", "benzylhydrazine", inhibition_mode="competitive")
        assert r.value == 0.026 and "MAO-B" in r.commentary

    def test_another_isoforms_row_of_the_models_mode_is_never_taken(self):
        # MAO-A's 0.205 mM is the only competitive phenylhydrazine row; for
        # MAO-B only a Kitz-Wilson row exists, and it is carried, named.
        r = ki("1.4.3.4", "phenylhydrazine", inhibition_mode="competitive", isoform="MAO-B")
        assert r.found and r.value == 0.791 and "MAO-B" in r.commentary
        assert any("determined from Kitz-Wilson plots, which give the K_I of an irreversible "
                   "inactivation" in line for line in r.search_log)


def rows(ec, inhibitor, organism="Homo sapiens"):
    """The parsed Ki rows of one inhibitor, as the resolver's pool holds them."""
    return _brenda_entries(ec, organism, inhibitor, PAGES.__getitem__, lambda e, o: None,
                           TAXA.get, table_label=KI_TABLE_LABEL)


class TestRowsNamingNoIsoform:
    """Compose, told the isoform, still takes a row naming none when every
    row naming the isoform states another mode. The resolver's isoform step
    has set those rows aside by then, so `_naming_no_isoform` puts them
    back, and `_partition_mode` ranks them behind the isoform's own."""

    def test_they_come_back_only_when_the_isoform_step_kept_named_rows(self):
        # Human MAO and D-amphetamine: rows naming MAO-A and MAO-B, and rows
        # naming none, one of them the mutant C374A.
        pool = rows("1.4.3.4", "D-amphetamine")
        assert _naming_no_isoform(pool, isoform_matched=False, allow_variants=False) == []
        back = _naming_no_isoform(pool, isoform_matched=True, allow_variants=False)
        assert sorted(e.km_value for e in back) == [0.0144, 0.015]
        assert all("mutant" not in (e.conditions or "") for e in back)
        with_variants = _naming_no_isoform(pool, isoform_matched=True, allow_variants=True)
        assert sorted(e.km_value for e in with_variants) == [0.0115, 0.0144, 0.015]

    def test_and_are_taken_only_when_no_row_for_the_isoform_can_be(self):
        """No real pool has this shape: of the 766 Ki rows parsed from the
        three committed pages, no inhibitor has a row naming an isoform and
        stating a mode beside a row naming no isoform. So two real rows from
        two pools are ranked together, to check the order, and
        are not presented as one pool: MAO-A's competitive benzylhydrazine
        row (2.096 mM, ref 702238) and the quinoline sulfonamide's
        noncompetitive LDH row (0.00252 mM, ref 739793), for a
        noncompetitive model asked for MAO-A."""
        mao_a = next(e for e in rows("1.4.3.4", "benzylhydrazine") if e.km_value == 2.096)
        unnamed = next(e for e in rows("1.1.1.27", QUINOLINE) if e.km_value == 0.00252)
        log = []
        kept, stated = _partition_mode([mao_a, unnamed], "noncompetitive", None, "MAO-A", True,
                                       log, "exact-match")
        assert kept == [unnamed] and stated == []
        assert log[-1].endswith("no row measuring MAO-A could be used for a noncompetitive "
                                "model, so these name no isoform and whether they measured "
                                "MAO-A is unknown")
        # A competitive model keeps the isoform's own row.
        kept, _ = _partition_mode([mao_a, unnamed], "competitive", None, "MAO-A", True, [],
                                  "exact-match")
        assert kept == [mao_a]


def _pool_of(monkeypatch, pool, tier):
    """Serve `pool` as the resolver's BRENDA rows for one tier and none for
    the other: the exact tier asks `_brenda_entries` for the organism, the
    cross-species tier for any organism (organism None)."""
    def entries(ec, organism, substrate, *args, **kwargs):
        wanted = organism is None if tier == "cross-species" else organism == "Homo sapiens"
        return list(pool) if wanted else []
    monkeypatch.setattr(fallback_logic, "_brenda_entries", entries)


class TestRowsNamingNoIsoformThroughTheResolver:
    """The pool above and one more, through `resolve_kinetic_value`, in both
    tiers, so the `+ _naming_no_isoform(...)` term in each tier is what a
    test fails on when it is removed, and not only the helpers.

    No real pool has this shape. Besides the 766 Ki rows of the three
    committed pages, BRENDA's pages for 31 more ECs were fetched and parsed
    on 2026-09-29 (not committed: 1.1.1.1, 1.1.1.21, 1.1.1.37, 1.1.1.42,
    1.1.1.49, 1.1.1.62, 1.1.1.146, 1.1.1.205, 1.2.1.3, 1.5.1.3, 1.14.13.39,
    1.14.14.1, 1.14.99.1, 1.17.3.2, 2.4.1.1, 2.4.2.1, 2.5.1.18, 2.7.1.2,
    2.7.1.11, 2.7.1.20, 2.7.1.40, 2.7.3.2, 2.7.4.3, 3.1.1.8, 3.1.3.16,
    3.1.3.48, 3.1.4.17, 3.2.1.20, 3.5.1.98, 3.5.4.4, 4.2.1.1): 6,589 Ki
    rows, of which none names an isoform (as caterva.bind.core reads one)
    and states a mode. So each pool here is two real rows of two
    inhibitors (from two pages for MAO-A, from the LDH page for LDH-A),
    served as one pool to exercise the wiring, and is not presented as a
    pool BRENDA holds."""

    MAO_A = ("1.4.3.4", "benzylhydrazine", 2.096)        # ref 702238, MAO-A, competitive
    NONCOMPETITIVE = ("1.1.1.27", QUINOLINE, 0.00252)    # ref 739793, no isoform
    LDH_A = ("1.1.1.27", "gossypol", 0.0019)             # ref 711801, LDH-A, no mode
    COMPETITIVE = ("1.1.1.27", QUINOLINE, 0.00059)       # ref 739793, no isoform

    @staticmethod
    def row(ec, inhibitor, value):
        return next(e for e in rows(ec, inhibitor) if e.km_value == value)

    @staticmethod
    def resolve(tier, ec, inhibitor, **kw):
        """The isoform's row's EC and inhibitor; asked for mouse in the
        cross-species tier, as test_the_cross_species_tier_chooses_by_mode_too
        asks, so the human rows are offered as a related organism's."""
        where = (dict(organism="Mus musculus", allow_cross_species=True,
                      lineage_provider=fixture_lineage_provider)
                 if tier == "cross-species" else {})
        return ki(ec, inhibitor, **where, **kw)

    @pytest.mark.parametrize("tier, source", [("exact-match", "brenda_exact"),
                                              ("cross-species", "brenda_cross_species")])
    def test_a_row_naming_no_isoform_is_taken_when_none_for_the_isoform_can_be(
            self, monkeypatch, tier, source):
        _pool_of(monkeypatch, [self.row(*self.MAO_A), self.row(*self.NONCOMPETITIVE)], tier)
        r = self.resolve(tier, *self.MAO_A[:2], inhibition_mode="noncompetitive", isoform="MAO-A")
        assert r.found and r.source == source, r.search_log
        assert r.value == 0.00252 and r.citation.reference_id == "739793"
        assert (f"Kept the 1 of 1 {tier} row(s) naming no isoform, stating noncompetitive "
                f"inhibition; no row measuring MAO-A could be used for a noncompetitive model, "
                f"so these name no isoform and whether they measured MAO-A is unknown"
                ) in r.search_log
        # Without the rows put back, the one row measuring MAO-A states
        # another mode and the constant is refused.
        monkeypatch.setattr(fallback_logic, "_naming_no_isoform", lambda *a, **k: [])
        refused = self.resolve(tier, *self.MAO_A[:2], inhibition_mode="noncompetitive",
                               isoform="MAO-A")
        assert refused.source == "mode_withheld"
        assert refused.modes_available == ["competitive inhibition"]

    @pytest.mark.parametrize("tier", ["exact-match", "cross-species"])
    def test_the_isoforms_row_comes_first_and_the_log_names_the_row_passed_over(
            self, monkeypatch, tier):
        """A row measuring the isoform and stating no mode ranks before a
        row naming no isoform that states the model's mode, as in compose.
        The log must not then say that no row states the mode."""
        _pool_of(monkeypatch, [self.row(*self.LDH_A), self.row(*self.COMPETITIVE)], tier)
        r = self.resolve(tier, *self.LDH_A[:2], inhibition_mode="competitive", isoform="LDH-A")
        assert r.found and r.value == 0.0019 and r.commentary.startswith("LDH-A")
        assert (f"No {tier} row measuring LDH-A states competitive inhibition; kept the 1 of 1 "
                f"{tier} row(s) measuring LDH-A, stating no mode, so whether the value is the "
                f"competitive constant is unknown; {tier} row(s) naming no isoform and stating "
                f"competitive inhibition versus NADH were passed over, because a row measuring "
                f"LDH-A is taken before one that may not have measured it, as caterva compose "
                f"takes it") in r.search_log


class TestKitzWilson:
    def test_they_are_taken_only_when_nothing_else_is_left(self):
        # A noncompetitive model: MAO-A's competitive row is another mode,
        # and the two Kitz-Wilson rows are what remains.
        r = ki("1.4.3.4", "phenylhydrazine", inhibition_mode="noncompetitive")
        assert r.found and r.value == 0.523
        assert sorted(c["value"] for c in r.ensemble_candidates) == [0.523, 0.791]
        assert any(line.startswith("No exact-match row states noncompetitive inhibition or is a "
                                   "reversible constant stating no mode") for line in r.search_log)


#: (EC, organism, inhibitor, model's mode, model's substrate, isoform): every
#: row set above, and each mode.
CASES = [
    *[("1.1.1.27", "Homo sapiens", QUINOLINE, m, "pyruvate", None)
      for m in ("competitive", "noncompetitive", "uncompetitive")],
    ("1.1.1.27", "Homo sapiens", QUINOLINE, "competitive", "NADH", None),
    ("1.1.1.27", "Homo sapiens", "gossypol", "competitive", "pyruvate", None),
    ("1.1.1.27", "Homo sapiens", "gossypol", "noncompetitive", "pyruvate", "LDH-A"),
    # An isoform no row names (test_isoform_resolution's): both refuse for
    # the isoform before a mode is read.
    ("1.1.1.27", "Homo sapiens", "gossypol", "competitive", "pyruvate", "LDH-X"),
    *[("2.7.1.1", "Oryctolagus cuniculus", "MgADP-", m, s, None)
      for m in ("competitive", "noncompetitive", "uncompetitive")
      for s in ("glucose", "MgATP2-", None)],
    *[("1.4.3.4", "Homo sapiens", inh, m, "kynuramine", iso)
      for inh in ("benzylhydrazine", "phenylhydrazine")
      for m in ("competitive", "noncompetitive", "uncompetitive")
      for iso in (None, "MAO-A", "MAO-B")],
]


def composed_from(result):
    """The Measurement `caterva compose` builds from a resolver answer, by
    the path compose itself takes: caterva.agents.adapters turns the
    KineticResult into a ParameterSource (its `ensemble_candidates` become
    `candidates`), and caterva.compose.export.measured_from_search turns
    that into the Measurement whose `alternatives` select_mode ranks."""
    from types import SimpleNamespace

    from caterva.agents.adapters import to_parameter_source
    from caterva.compose.export import measured_from_search

    source, why_not = to_parameter_source("ki", result)
    assert source is not None, why_not
    return measured_from_search(
        SimpleNamespace(resolutions={"reaction_Ki": SimpleNamespace(source=source)}))


class TestTheSameRowAsCompose:
    """One ranking, so one answer. For each case, `caterva compose`'s
    selection (select_isoform, then select_mode, over the Measurement the
    resolver's no-mode answer becomes) and the resolver asked for the mode
    must carry the same row, or both refuse.

    WHAT THIS DOES AND DOES NOT CHECK. Both sides rank with the same
    function, caterva.compose.ki_mode.rank, so agreement here cannot show
    that the rule is right; the rule is held to BRENDA's own rows by the
    tests above (0.00252 and 0.00059 mM of ref 739793, the refusals, the
    mixed and Kitz-Wilson rows). What it checks is everything around the
    rule, which the two callers do differently: which rows each ranks, the
    isoform-then-mode order, the tie-break, and when each refuses. A
    difference would be one of those.

    They differ where a row of the model's mode is dominated on evidence:
    compose ranks the frontier, the resolver the whole pool
    (`_partition_mode`, and the Trypanosoma cruzi test below). In every
    case in CASES the rows of one inhibitor are graded alike, so that does
    not arise."""

    MOTIF = {"competitive": "competitive_inhibition",
             "noncompetitive": "noncompetitive_inhibition",
             "uncompetitive": "uncompetitive_inhibition"}

    @pytest.mark.parametrize("ec, organism, inhibitor, mode, substrate, isoform", CASES)
    def test_compose_and_the_resolver_agree(self, ec, organism, inhibitor, mode, substrate,
                                           isoform):
        from caterva.compose.isoform import select_isoform
        from caterva.compose.ki_mode import select_mode

        unranked = plain(ec, inhibitor, organism)
        assert unranked.found
        measured = composed_from(unranked)
        resolved = ki(ec, inhibitor, organism=organism, inhibition_mode=mode,
                      model_substrate=substrate, isoform=isoform)
        if isoform:
            by_isoform = select_isoform(measured, isoform)
            if "reaction_Ki" in by_isoform.refused:
                # Refused for the isoform before any mode is read, on both.
                assert resolved.source == "isoform_withheld", resolved.search_log
                return
            measured = by_isoform.measured
        composed = select_mode(measured, {"reaction_Ki": (self.MOTIF[mode], "ki")},
                               substrate=substrate, isoform=isoform)
        if "reaction_Ki" in composed.refused:
            assert resolved.source == "mode_withheld", resolved.search_log
        else:
            carried = composed.measured["reaction_Ki"]
            assert resolved.found, resolved.search_log
            assert (resolved.value, resolved.commentary) == (carried.value, carried.commentary)


class TestWhereComposeCannotSeeTheRow:
    """Trypanosoma cruzi hexokinase and ADP, on the recorded page: 0.13 mM
    (no commentary), 1.3 mM ("natural hexokinase from epimastigotes, at pH
    7.5"), 1.5 mM ("competitive to ATP"), 7.0 mM ("noncompetitive to
    glucose"). The evidence frontier keeps 1.3 alone, so compose's
    alternatives hold one row and a competitive model can only carry it; the
    resolver narrows by mode first and returns the competitive row."""

    CRUZI = dict(organism="Trypanosoma cruzi")

    def test_without_a_mode_the_frontier_keeps_only_the_row_with_a_ph(self):
        r = ki("2.7.1.1", "ADP", **self.CRUZI)
        assert r.value == 1.3 and [c["value"] for c in r.ensemble_candidates] == [1.3]

    @pytest.mark.parametrize("mode, value, commentary", [
        ("competitive", 1.5, "competitive to ATP"),
        ("noncompetitive", 7.0, "noncompetitive to glucose"),
    ])
    def test_the_resolver_returns_the_row_of_the_mode(self, mode, value, commentary):
        r = ki("2.7.1.1", "ADP", inhibition_mode=mode, model_substrate="glucose", **self.CRUZI)
        assert (r.value, r.commentary) == (value, commentary)

    def test_compose_over_the_frontier_carries_the_row_stating_no_mode(self):
        from caterva.compose.ki_mode import select_mode

        measured = composed_from(plain("2.7.1.1", "ADP", "Trypanosoma cruzi"))
        out = select_mode(measured, {"reaction_Ki": ("competitive_inhibition", "ki")},
                          substrate="glucose")
        assert out.measured["reaction_Ki"].value == 1.3


class TestTheArgument:
    def test_a_mode_is_not_applied_to_a_km(self):
        plain = ki("2.7.1.1", "glucose", quantity="km")
        asked = ki("2.7.1.1", "glucose", quantity="km", inhibition_mode="competitive")
        assert (asked.value, asked.commentary) == (plain.value, plain.commentary)
        assert ("inhibition mode 'competitive' not applied: it chooses among Ki rows, and this "
                "is a km lookup") in asked.search_log

    @pytest.mark.parametrize("mode", ["mixed", "Competitive", "partial", ""])
    @pytest.mark.parametrize("quantity", ["ki", "km"])
    def test_a_mode_no_model_is_of_is_refused(self, mode, quantity):
        """For a Km too: the mode is not applied to one, but a caller
        sending "mixed" has made the same mistake either way."""
        with pytest.raises(ValueError, match="inhibition_mode must be one of"):
            ldh(inhibition_mode=mode, quantity=quantity)
