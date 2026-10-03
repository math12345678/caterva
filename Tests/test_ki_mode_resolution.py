"""The resolver's `inhibition_mode` argument, on BRENDA's real pages.

BRENDA ref 739793 gives human LDH two Ki values for one quinoline
sulfonamide, from one paper: 0.00059 mM "competitive versus NADH" and
0.00252 mM "noncompetitive versus pyruvate". Without a mode the resolver
returns the lower, whatever model the caller is building. With the model's
mode it must return the row `caterva compose` would carry for that model,
by the same ranking (caterva.compose.ki_mode.rank), and refuse, naming the
modes, when every row states another. Asked for no mode with the model's as
`compare_mode`, which `caterva compose --any-mode` sends, it must return
exactly its no-mode answer and name the row the call with the mode returns
(`TestAnyMode`).

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


@functools.lru_cache(maxsize=None)
def no_mode(ec, inhibitor, organism, isoform):
    """The question the API and the TypeScript CLI ask when no mode is sent:
    `resolve_kinetic_value` with `inhibition_mode=None`."""
    if isoform is None:
        return plain(ec, inhibitor, organism)
    return ki(ec, inhibitor, organism=organism, isoform=isoform)


@functools.lru_cache(maxsize=None)
def asked_for(ec, inhibitor, organism, mode, substrate, isoform):
    """The default's question: the model's mode, substrate and isoform."""
    return ki(ec, inhibitor, organism=organism, inhibition_mode=mode, model_substrate=substrate,
              isoform=isoform)


@functools.lru_cache(maxsize=None)
def any_mode_asks(ec, inhibitor, organism, mode, substrate, isoform):
    """`caterva compose --any-mode`'s question (ComposedModel.
    parameter_requests(any_mode=True)): no mode, the model's as the one to
    compare with."""
    return ki(ec, inhibitor, organism=organism, compare_mode=mode, model_substrate=substrate,
              isoform=isoform)


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


class TestEvidenceAgainstTheMechanism:
    """The row that says the model's mechanism is wrong for this inhibitor.

    A competitive pyruvate model rightly carries 0.00059 mM "competitive
    versus NADH": it is the only row stating the model's mode. The same
    paper's 0.00252 mM "noncompetitive versus pyruvate" says that against
    pyruvate the inhibitor is not competitive. `_partition_mode` sets that
    row aside, so without `mechanism_evidence` it reached no caller but
    `caterva compose`, which says it in its notes."""

    def test_a_competitive_pyruvate_model_is_told_the_pyruvate_row(self):
        r = ldh(inhibition_mode="competitive")
        assert r.found and r.value == 0.00059
        assert r.mechanism_evidence.model_dump() == {
            "value": 0.00252, "unit": "mM", "organism": "Homo sapiens",
            "reference_id": "739793", "inhibition_mode": "noncompetitive",
            "versus": "pyruvate", "conditions": NONCOMPETITIVE_VS_PYRUVATE,
            "model_mode": "competitive", "model_substrate": "pyruvate"}
        # caterva compose's note, word for word (caterva/tests/test_ki_mode.py).
        assert r.search_log[-1] == (
            "A ranked row states noncompetitive inhibition versus pyruvate (0.00252 mM, BRENDA "
            "ref 739793), measured against pyruvate, this model's substrate, and the row carried "
            "(0.00059 mM, BRENDA ref 739793) states competitive inhibition versus NADH. Measured "
            "against pyruvate this inhibitor is not competitive, which is evidence against this "
            "model's mechanism for it; no choice of row fixes that")

    def test_a_noncompetitive_nadh_model_is_told_the_nadh_row(self):
        # The same paper the other way round, and the only other model any
        # of the 766 Ki rows on the three committed pages gives this finding
        # for: the noncompetitive row is the only one of that mode, measured
        # versus pyruvate, and against NADH the inhibitor was competitive.
        r = ki("1.1.1.27", QUINOLINE, inhibition_mode="noncompetitive", model_substrate="NADH")
        assert r.found and r.value == 0.00252 and r.commentary == NONCOMPETITIVE_VS_PYRUVATE
        e = r.mechanism_evidence
        assert (e.value, e.inhibition_mode, e.versus, e.conditions) == (
            0.00059, "competitive", "NADH", COMPETITIVE_VS_NADH)
        assert (e.model_mode, e.model_substrate) == ("noncompetitive", "NADH")

    def test_none_when_the_row_returned_is_the_models_own_assay(self):
        # Noncompetitive versus pyruvate is this model's mode and substrate;
        # the NADH row's other mode is a different assay's constant.
        assert ldh(inhibition_mode="noncompetitive").mechanism_evidence is None

    def test_none_for_a_model_of_the_other_substrate(self):
        r = ki("1.1.1.27", QUINOLINE, inhibition_mode="competitive", model_substrate="NADH")
        assert r.value == 0.00059 and r.mechanism_evidence is None

    def test_none_without_the_models_substrate_or_without_a_mode(self):
        # Nothing to be measured against, and nothing to contradict.
        assert ki("1.1.1.27", QUINOLINE, inhibition_mode="competitive").mechanism_evidence is None
        assert ldh().mechanism_evidence is None

    def test_none_where_no_row_states_a_mode(self):
        r = ki("1.1.1.27", "gossypol", inhibition_mode="competitive", model_substrate="pyruvate")
        assert r.found and r.mechanism_evidence is None

    def test_the_cross_species_tier_says_it_too_and_whose_row_it_is(self):
        r = ki("1.1.1.27", QUINOLINE, organism="Mus musculus", allow_cross_species=True,
               lineage_provider=fixture_lineage_provider, inhibition_mode="competitive",
               model_substrate="pyruvate")
        assert r.found and r.source == "brenda_cross_species" and r.value == 0.00059
        assert (r.mechanism_evidence.value, r.mechanism_evidence.organism) == (
            0.00252, "Homo sapiens")


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
    # The other model the pyruvate/NADH pair is evidence against.
    ("1.1.1.27", "Homo sapiens", QUINOLINE, "noncompetitive", "NADH", None),
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


def compose_selects(resolved, mode, substrate, isoform=None, any_mode=False):
    """What `caterva compose` carries for a Ki, from the resolver's answer to
    the question compose now asks (narrowed.select_for_model, the function
    the command calls): the answer becomes a ParameterSource as the agents'
    scout makes it (caterva.agents.adapters), and a refusal keeps the
    resolver's word for it, as the scout's Resolution does."""
    from types import SimpleNamespace

    from caterva.agents.adapters import to_parameter_source
    from caterva.compose.narrowed import select_for_model

    source, why_not = to_parameter_source("ki", resolved)
    resolution = SimpleNamespace(source=source, reason=why_not,
                                 outcome=None if source is not None else resolved.source)
    return select_for_model(SimpleNamespace(resolutions={"reaction_Ki": resolution}),
                            {"reaction_Ki": (TestTheSameRowAsCompose.MOTIF[mode], "ki")},
                            substrate=substrate, isoform=isoform, any_mode=any_mode)


#: The note `narrowed.carry` adds when the selections alone arrive at
#: another row than the resolver's.
CARRIED = "choosing among the rows the evidence alone returned arrives at"


class TestTheSameRowAsCompose:
    """One ranking, so one answer. `caterva compose` asks the resolver with
    the model's mode, substrate and isoform, as the API does, and carries the
    row it returns; its selections (select_isoform, then select_mode) then
    say what the choice did, shown the resolver's row beside the row the
    evidence alone would take.

    WHAT THIS DOES AND DOES NOT CHECK. Both sides rank with the same
    function, caterva.compose.ki_mode.rank, so agreement here cannot show
    that the rule is right; the rule is held to BRENDA's own rows by the
    tests above (0.00059 and 0.00252 mM of ref 739793, the refusals, the
    mixed and Kitz-Wilson rows). What it checks is everything around the
    rule: what compose sends, what comes back, and that the selections,
    choosing among what they are shown, arrive at the resolver's row by
    themselves, so the report's account of the choice is of the row carried
    (`narrowed.carry` would otherwise have to move it, and says so)."""

    MOTIF = {"competitive": "competitive_inhibition",
             "noncompetitive": "noncompetitive_inhibition",
             "uncompetitive": "uncompetitive_inhibition"}

    @pytest.mark.parametrize("ec, organism, inhibitor, mode, substrate, isoform", CASES)
    def test_compose_carries_the_resolvers_row(self, ec, organism, inhibitor, mode, substrate,
                                               isoform):
        from caterva.compose.ki_mode import ANY_MODE_FLAG

        resolved = asked_for(ec, inhibitor, organism, mode, substrate, isoform)
        chosen = compose_selects(resolved, mode, substrate, isoform)
        if not resolved.found:
            reason = chosen.withheld["reaction_Ki"]
            assert "reaction_Ki" not in chosen.measured
            if resolved.source == "mode_withheld":
                assert ANY_MODE_FLAG in reason
            else:
                assert resolved.source == "isoform_withheld" and f"(--isoform {isoform})" in reason
            return
        carried = chosen.measured["reaction_Ki"]
        assert (carried.value, carried.commentary) == (resolved.value, resolved.commentary)
        assert not any(CARRIED in note for note in chosen.notes), chosen.notes

    @pytest.mark.parametrize("ec, organism, inhibitor, mode, substrate, isoform", CASES)
    def test_the_selections_over_the_unasked_answer_agree_here_too(
            self, ec, organism, inhibitor, mode, substrate, isoform):
        """How compose chose until 2026-09-30: select_isoform then
        select_mode over the answer the resolver gives unasked. In every case
        here the rows of one inhibitor are graded alike, so its frontier holds
        them all and this agrees with the resolver asked; the Trypanosoma
        cruzi case below is one where it did not."""
        from caterva.compose.isoform import select_isoform
        from caterva.compose.ki_mode import select_mode

        unranked = plain(ec, inhibitor, organism)
        assert unranked.found
        measured = composed_from(unranked)
        resolved = asked_for(ec, inhibitor, organism, mode, substrate, isoform)
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
            # And the same evidence against the model's mechanism, in the
            # same words: compose's note is the resolver's log line, and the
            # resolver carries the row for the API and the CLI.
            prefix = "`reaction_Ki`: a ranked row states "
            said = [n[len("`reaction_Ki`: "):] for n in composed.notes if n.startswith(prefix)]
            if said:
                assert said[0][0].upper() + said[0][1:] in resolved.search_log
                assert resolved.mechanism_evidence is not None
            else:
                assert resolved.mechanism_evidence is None, resolved.mechanism_evidence


class TestWhereComposeCouldNotSeeTheRow:
    """Trypanosoma cruzi hexokinase and ADP, on the recorded page: 0.13 mM
    (no commentary), 1.3 mM ("natural hexokinase from epimastigotes, at pH
    7.5"), 1.5 mM ("competitive to ATP"), 7.0 mM ("noncompetitive to
    glucose"). The evidence frontier keeps 1.3 alone. Until 2026-09-30
    compose asked the resolver for no mode and chose among that frontier, so
    a competitive model carried 1.3, a row stating no mode, where the API
    got 1.5; this class pinned the difference. Compose now asks with the
    mode, and the two agree."""

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
        # And says what it would have returned unasked, for compose's report.
        assert r.evidence_only[0]["value"] == 1.3

    @pytest.mark.parametrize("mode, value, commentary", [
        ("competitive", 1.5, "competitive to ATP"),
        ("noncompetitive", 7.0, "noncompetitive to glucose"),
    ])
    def test_compose_now_carries_the_same_row(self, mode, value, commentary):
        resolved = ki("2.7.1.1", "ADP", inhibition_mode=mode, model_substrate="glucose",
                      **self.CRUZI)
        chosen = compose_selects(resolved, mode, "glucose")
        carried = chosen.measured["reaction_Ki"]
        assert (carried.value, carried.commentary) == (value, commentary)
        # The report says which row the mode replaced, and why, as it did
        # when compose could see both rows.
        assert chosen.notes[0].startswith(
            "`reaction_Ki`: the resolver's pick (1.3 mM, BRENDA ref 640265) states no "
            "inhibition mode;")
        assert carried.chosen_because.startswith(f"the row stating {mode} inhibition")

    def test_choosing_after_the_frontier_is_what_carried_the_other_row(self):
        """The old order, kept as the reason for the new one: the mode rule
        applied to the unasked answer can only carry 1.3."""
        from caterva.compose.ki_mode import select_mode

        measured = composed_from(plain("2.7.1.1", "ADP", "Trypanosoma cruzi"))
        out = select_mode(measured, {"reaction_Ki": ("competitive_inhibition", "ki")},
                          substrate="glucose")
        assert out.measured["reaction_Ki"].value == 1.3

    def test_an_answer_with_no_mode_alone_cannot_name_the_defaults_row(self):
        """Why `--any-mode` sends `compare_mode`: over the rows the no-mode
        answer holds, which lack 1.5, the selection keeps 1.3 and says
        nothing, where the default carries 1.5. Until 2026-09-30 this was
        what `--any-mode` printed; TestAnyMode below is what it prints now."""
        unasked = ki("2.7.1.1", "ADP", **self.CRUZI)
        chosen = compose_selects(unasked, "competitive", "glucose", any_mode=True)
        assert chosen.measured["reaction_Ki"].value == 1.3 and chosen.notes == []


#: Every case above, and Trypanosoma cruzi's ADP, whose competitive and
#: noncompetitive rows the no-mode answer's frontier drops.
ANY_MODE_CASES = [
    *CASES,
    *[("2.7.1.1", "Trypanosoma cruzi", "ADP", m, "glucose", None)
      for m in ("competitive", "noncompetitive", "uncompetitive")],
]


class TestAnyMode:
    """`caterva compose --any-mode` asks the resolver what the API and the
    TypeScript CLI ask when no mode is sent, and carries its answer; and it
    names the row its default would carry from the resolver's own answer to
    the default's question (`compare_mode`, `KineticResult.mode_default`).

    Until 2026-09-30 the second half was worked out from the rows the no-mode
    answer held, the frontier of the rows the evidence kept. For
    Trypanosoma cruzi and ADP that frontier is 1.3 mM alone, so the note said
    nothing while the default carried 1.5 mM (the class above keeps the
    reason). Every row here is a committed page's."""

    @pytest.mark.parametrize("ec, organism, inhibitor, mode, substrate, isoform", ANY_MODE_CASES)
    def test_the_answer_is_the_no_mode_answer_field_for_field(self, ec, organism, inhibitor,
                                                              mode, substrate, isoform):
        """Parity with the API and the CLI sent no mode: every field of the
        result but `mode_default`, the search log included, is what
        `inhibition_mode=None` returns."""
        got = any_mode_asks(ec, inhibitor, organism, mode, substrate, isoform)
        bare = no_mode(ec, inhibitor, organism, isoform)
        assert got.model_dump(exclude={"mode_default"}) == bare.model_dump(exclude={"mode_default"})
        assert bare.mode_default is None

    @pytest.mark.parametrize("ec, organism, inhibitor, mode, substrate, isoform", ANY_MODE_CASES)
    def test_the_default_it_names_is_the_defaults_own_answer(self, ec, organism, inhibitor, mode,
                                                            substrate, isoform):
        got = any_mode_asks(ec, inhibitor, organism, mode, substrate, isoform)
        default = asked_for(ec, inhibitor, organism, mode, substrate, isoform)
        if not got.found:
            # Refused before the mode step (LDH-X), so the default refuses
            # the same way and there is nothing to compare.
            assert got.mode_default is None and default.source == got.source
            return
        said = got.mode_default
        assert (said.mode, said.model_substrate) == (mode, substrate)
        if default.found:
            assert said.modes_available == []
            assert (said.row["value"], said.row["conditions"], said.row["reference_id"],
                    said.row["organism"]) == (default.value, default.commentary,
                                              default.citation.reference_id, default.organism)
        else:
            assert default.source == "mode_withheld"
            assert said.row is None and said.modes_available == default.modes_available

    @pytest.mark.parametrize("ec, organism, inhibitor, mode, substrate, isoform", ANY_MODE_CASES)
    def test_compose_carries_the_no_mode_row_and_names_the_defaults(
            self, ec, organism, inhibitor, mode, substrate, isoform):
        from caterva.compose.ki_mode import ANY_MODE_FLAG, read_row, row_label

        chosen = compose_selects(any_mode_asks(ec, inhibitor, organism, mode, substrate, isoform),
                                 mode, substrate, isoform, any_mode=True)
        bare = no_mode(ec, inhibitor, organism, isoform)
        if not bare.found:
            assert "reaction_Ki" not in chosen.measured
            return
        carried = chosen.measured["reaction_Ki"]
        assert (carried.value, carried.commentary) == (bare.value, bare.commentary)
        assert not any(CARRIED in note for note in chosen.notes), chosen.notes
        default = asked_for(ec, inhibitor, organism, mode, substrate, isoform)
        said = [n for n in chosen.notes if n.startswith(f"`reaction_Ki`: {ANY_MODE_FLAG} kept")]
        if default.found and (default.value, default.commentary) == (bare.value, bare.commentary):
            assert said == [], said
            return
        assert len(said) == 1, chosen.notes
        assert ANY_MODE_FLAG in carried.chosen_because
        if not default.found:
            assert "without it the constant would be refused" in said[0]
            assert f"({'; '.join(default.modes_available)})" in said[0]
            return
        # The default's row by value and reference, and the mode it states.
        reading = read_row(default.commentary)
        states = reading.says() if reading.mode != "unstated" else "no inhibition mode"
        label = row_label(default.value, default.unit, default.citation.reference_id)
        assert f"row stating {states} ({label})" in said[0]
        kept = ("every row it keeps once variants"
                + (" and rows naming another isoform" if isoform else "") + " are set aside")
        assert f"ranks by the mode {kept}, before choosing on evidence, and returns it" in said[0]

    def test_trypanosoma_cruzi_names_the_row_its_answer_dropped(self):
        got = any_mode_asks("2.7.1.1", "ADP", "Trypanosoma cruzi", "competitive", "glucose", None)
        assert got.value == 1.3 and [c["value"] for c in got.ensemble_candidates] == [1.3]
        chosen = compose_selects(got, "competitive", "glucose", any_mode=True)
        carried = chosen.measured["reaction_Ki"]
        assert carried.value == 1.3
        assert chosen.notes == [
            "`reaction_Ki`: --any-mode kept the resolver's pick (1.3 mM, BRENDA ref 640265), "
            "which states no inhibition mode; without it the row stating competitive inhibition "
            "versus ATP (1.5 mM, BRENDA ref 640216), this model's mechanism though not its "
            "substrate (glucose), would be used; the resolver, asked for a competitive model of "
            "glucose, ranks by the mode every row it keeps once variants are set aside, before "
            "choosing on evidence, and returns it"]
        # The spread is the default's: 1.3 is carried, 1.5 is among its rows.
        assert carried.disagreement == (1.3, 1.5)

    def test_trypanosoma_cruzi_rows_say_what_they_were_measured_to(self):
        """BRENDA writes these two rows "competitive to ATP" and
        "noncompetitive to glucose" (ref 640216). Read as measured against
        nothing until "to" was read, the 1.5 mM row was carried for a glucose
        model with no remark, and the 7 mM row, which states another mode
        measured against glucose, was never named as evidence against a
        competitive model of glucose."""
        default = asked_for("2.7.1.1", "ADP", "Trypanosoma cruzi", "competitive", "glucose", None)
        assert (default.value, default.commentary) == (1.5, "competitive to ATP")
        against = default.mechanism_evidence
        assert against is not None
        assert (against.value, against.reference_id, against.inhibition_mode, against.versus,
                against.conditions) == (7.0, "640216", "noncompetitive", "glucose",
                                        "noncompetitive to glucose")

    def test_the_quinoline_sulfonamide_names_the_other_mechanisms_row(self):
        got = any_mode_asks("1.1.1.27", QUINOLINE, "Homo sapiens", "noncompetitive", "pyruvate",
                            None)
        chosen = compose_selects(got, "noncompetitive", "pyruvate", any_mode=True)
        assert (chosen.measured["reaction_Ki"].value, chosen.notes[0]) == (0.00059, (
            "`reaction_Ki`: --any-mode kept the resolver's pick (0.00059 mM, BRENDA ref 739793), "
            "which measured competitive inhibition versus NADH, and this model is noncompetitive; "
            "without it the row stating noncompetitive inhibition versus pyruvate (0.00252 mM, "
            "BRENDA ref 739793), this model's mechanism and substrate, would be used; the "
            "resolver, asked for a noncompetitive model of pyruvate, ranks by the mode every row "
            "it keeps once variants are set aside, before choosing on evidence, and returns it"))

    def test_the_quinoline_sulfonamide_for_a_mode_no_row_states(self):
        got = any_mode_asks("1.1.1.27", QUINOLINE, "Homo sapiens", "uncompetitive", "pyruvate",
                            None)
        chosen = compose_selects(got, "uncompetitive", "pyruvate", any_mode=True)
        assert chosen.measured["reaction_Ki"].value == 0.00059 and chosen.withheld == {}
        assert chosen.notes[0].endswith(
            "without it the constant would be refused; the resolver, asked for an uncompetitive "
            "model of pyruvate, finds that every row it keeps once variants are set aside states "
            "another mode (competitive "
            "inhibition versus NADH; noncompetitive inhibition versus pyruvate)")

    @pytest.mark.parametrize("mode", ["competitive", "noncompetitive", "uncompetitive"])
    def test_the_cross_species_tier_names_the_defaults_row_too(self, mode):
        """Asked for mouse with the opt-in, the human rows are the tier's
        (test_the_cross_species_tier_chooses_by_mode_too): the answer is the
        no-mode one, and the default named is the call with the mode's."""
        kw = dict(organism="Mus musculus", allow_cross_species=True,
                  lineage_provider=fixture_lineage_provider, model_substrate="pyruvate")
        got = ki("1.1.1.27", QUINOLINE, compare_mode=mode, **kw)
        bare = ki("1.1.1.27", QUINOLINE, organism="Mus musculus", allow_cross_species=True,
                  lineage_provider=fixture_lineage_provider)
        default = ki("1.1.1.27", QUINOLINE, inhibition_mode=mode, **kw)
        assert got.source == bare.source == "brenda_cross_species"
        assert got.model_dump(exclude={"mode_default"}) == bare.model_dump(exclude={"mode_default"})
        if default.found:
            assert (got.mode_default.row["value"], got.mode_default.row["conditions"]) == (
                default.value, default.commentary)
        else:
            assert got.mode_default.row is None
            assert got.mode_default.modes_available == default.modes_available

    def test_compare_mode_is_refused_beside_a_mode_and_checked_as_one(self):
        with pytest.raises(ValueError, match="compare_mode is for a call asked for no inhibition"):
            ldh(inhibition_mode="competitive", compare_mode="noncompetitive")
        with pytest.raises(ValueError, match="compare_mode must be one of"):
            ldh(compare_mode="mixed")
        # A Km has no mode to compare: nothing is said.
        assert ki("2.7.1.1", "glucose", quantity="km", compare_mode="competitive").mode_default is None


class TestTheCommand:
    """`caterva compose` itself, through the agents' scout and the real
    resolver, over the committed hexokinase page: the scout's resolver is
    given the page and the stubbed identifier lookups these tests use
    everywhere (`brenda_resolver`'s keyword arguments reach
    `resolve_kinetic_value`), and nothing else is replaced."""

    ARGS = ["Michaelis-Menten with a competitive inhibitor", "--subject", "2.7.1.1",
            "--organism", "Trypanosoma cruzi", "--substrate", "glucose", "--inhibitor", "ADP",
            "--no-analysis", "--no-simulate", "--no-ranking"]

    @pytest.fixture
    def compose(self, monkeypatch, capsys):
        from caterva.agents import scouts
        from caterva.compose.__main__ import main

        real = scouts.brenda_resolver
        monkeypatch.setattr(scouts, "brenda_resolver", lambda **kw: real(
            html_provider=PAGES.__getitem__, uniprot_provider=lambda ec_, org: None,
            taxon_id_provider=TAXA.get, search_literature=False))

        def run(*flags):
            code = main([*self.ARGS, *flags])
            return code, capsys.readouterr().out
        return run

    def test_any_mode_carries_the_no_mode_row_and_says_what_the_default_carries(self, compose):
        code, out = compose("--any-mode")
        assert code == 0
        bare = no_mode("2.7.1.1", "ADP", "Trypanosoma cruzi", None)
        assert bare.value == 1.3 and bare.citation.reference_id == "640265"
        assert "| `reaction_Ki` | 1.3 mM | literature (Trypanosoma cruzi) | BRENDA ref 640265 |" in out
        assert ("`reaction_Ki`: --any-mode kept the resolver's pick (1.3 mM, BRENDA ref 640265), "
                "which states no inhibition mode; without it the row stating competitive "
                "inhibition versus ATP (1.5 mM, BRENDA ref 640216)") in out
        assert "spanning **1.3 to 1.5 mM**" in out

    def test_the_default_carries_the_row_the_note_named(self, compose):
        code, out = compose()
        assert code == 0
        default = asked_for("2.7.1.1", "ADP", "Trypanosoma cruzi", "competitive", "glucose", None)
        assert default.value == 1.5 and default.citation.reference_id == "640216"
        assert "| `reaction_Ki` | 1.5 mM | literature (Trypanosoma cruzi) | BRENDA ref 640216 |" in out
        assert "spanning **1.3 to 1.5 mM**" in out
        # "competitive to ATP" is read as measured versus ATP, and said.
        assert ("`reaction_Ki`: the row measured inhibition **versus ATP**, not versus glucose, "
                "the substrate in this model") in out


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
