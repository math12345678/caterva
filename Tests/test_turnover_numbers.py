"""kcat (turnover number) extraction from BRENDA's Turnover Numbers table.

Every value asserted here comes from `fixtures/brenda_ache_kcat_fixture.html`,
a live capture of BRENDA EC 3.1.1.7 (acetylcholinesterase) taken 2026-08-02
via `brenda_kcat_capture.py`. Nothing is invented: the fixture is real page
markup, and these tests read it the same way the resolver does.

Why kcat and not something else
-------------------------------
`kcat` was already named in `STRENDA_GOVERNED_FIELDS` with no lookup path
behind it (ADR 0010 carried item 3), specifically so that adding one could
not silently bypass the reporting requirement. This is that lookup path, so
the STRENDA rule now applies to a second field automatically.

Units matter here. `BRENDAKmEntry.km_value` carries the kcat in s^-1, NOT
mM -- the field name is inherited from the shared row model. A Km of 6500 mM
is a unit error; a kcat of 6500 s^-1 is an ordinary fast enzyme. See ADR 0012.
"""

from __future__ import annotations

import pathlib

import pytest

import brenda_client
import enzyme_lookup
from brenda_client import (
    KCAT_PLAUSIBLE_MAX_PER_S,
    KCAT_PLAUSIBLE_MIN_PER_S,
    TURNOVER_TABLE_LABEL,
    parse_brenda_km_html,
    parse_brenda_turnover_html,
)

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
KCAT_FIXTURE = FIXTURES / "brenda_ache_kcat_fixture.html"

# Substrates present in the captured AChE turnover table.
SUBSTRATES = [
    "acetylcholine",
    "Acetylcholine",
    "acetylthiocholine",
    "acetyl thiocholine",
    "heroin",
    "6-monoacetylmorphine",
    "propionylthiocholine",
]


@pytest.fixture(scope="module")
def kcat_entries():
    """Parsed turnover entries. Assertion, not skip -- the fixture is
    committed, so its absence or an empty parse is a regression."""
    assert KCAT_FIXTURE.exists(), f"committed fixture missing: {KCAT_FIXTURE}"
    entries = parse_brenda_turnover_html(
        html=KCAT_FIXTURE.read_text(encoding="utf-8"),
        ec_number="3.1.1.7",
        target_substrates=SUBSTRATES,
        target_organism="Homo sapiens",
        require_substrate_match=False,
    )
    assert entries, "parsed zero kcat entries from the committed fixture"
    return entries


class TestRealCapturedValues:
    def test_the_golden_human_kcat_is_present(self, kcat_entries):
        """Hand-verified against the fixture:

            118 | 6-monoacetylmorphine | Homo sapiens | P22303
            "recombinant enzyme, pH 7.4, 37 C" | BRENDA ref 750291
        """
        match = [
            e for e in kcat_entries
            if e.km_value == 118.0 and e.reference_id == "750291"
        ]
        assert len(match) == 1
        entry = match[0]
        assert entry.organism == "Homo sapiens"
        assert entry.assay_ph == 7.4
        assert entry.assay_temperature_c == 37.0
        assert entry.flagged is False

    def test_values_span_orders_of_magnitude_and_none_are_flagged(self, kcat_entries):
        """Real turnover numbers range widely. The Km bounds (1e-7..1e3 mM)
        would flag the fast ones, which is exactly the mistake these
        separate kcat bounds exist to prevent."""
        values = sorted(e.km_value for e in kcat_entries)
        assert values[0] < 10.0 < values[-1]
        for entry in kcat_entries:
            assert KCAT_PLAUSIBLE_MIN_PER_S <= entry.km_value <= KCAT_PLAUSIBLE_MAX_PER_S
            assert entry.flagged is False, entry.flag_reason

    def test_a_fast_kcat_is_not_flagged_as_an_implausible_km(self, kcat_entries):
        """kcat 6500 s^-1 is a real captured human value. Under the Km
        ceiling of 1000 mM it would be flagged as a unit error."""
        fast = [e for e in kcat_entries if e.km_value == 6500.0]
        assert fast, "the 6500 s^-1 row vanished from the fixture"
        assert fast[0].flagged is False
        assert 6500.0 > 1000.0  # i.e. it WOULD fail the Km bound  # noqa: PLR0133


class TestStrendaAppliesToKcat:
    def test_assay_conditions_travel_with_the_turnover_number(self, kcat_entries):
        """ADR 0010 governs kcat exactly as it governs Km: a turnover number
        measured at an unreported pH or temperature cannot be reproduced."""
        complete = [
            e for e in kcat_entries
            if e.assay_ph is not None and e.assay_temperature_c is not None
        ]
        assert complete, "no kcat entry carried both pH and temperature"
        for entry in complete:
            assert 0.0 <= entry.assay_ph <= 14.0
            assert -20.0 <= entry.assay_temperature_c <= 150.0


class TestTheKcatCommentaryHeuristicIsNotInverted:
    def test_kcat_in_commentary_does_not_flag_a_turnover_row(self, kcat_entries):
        """The Km parser flags a row whose commentary mentions Kcat, because
        in the KM Values table that suggests a turnover number in the wrong
        place. In the Turnover Numbers table it is what belongs there.

        Applied unconditionally, that rule flagged the real captured row
        (6500 s^-1, "...does not alter the Kcat value") for being precisely
        what it claims to be.
        """
        mentions = [
            e for e in kcat_entries
            if e.conditions and "kcat" in e.conditions.lower()
        ]
        assert mentions, "fixture no longer has a Kcat-mentioning row"
        for entry in mentions:
            assert entry.flagged is False, entry.flag_reason

    def test_the_rule_still_applies_to_the_km_table(self):
        """The inversion must not disable the check where it is correct.
        A synthetic KM Values row (labelled as such, not BRENDA data) whose
        commentary mentions Kcat must still be flagged."""
        html = """
        <html><body>
        <a href="javascript:showTable('tab12')">KM Values</a>
        <div id="tab12">
          <div class="row">
            <div class="cell">5.0</div>
            <div class="cell">acetylcholine</div>
            <div class="cell">Homo sapiens</div>
            <div class="cell">-</div>
            <div class="cell">pH 7.4, 37C, Kcat measurement</div>
            <div class="cell">999999</div>
          </div>
        </div>
        </body></html>
        """
        entries = parse_brenda_km_html(
            html=html,
            ec_number="3.1.1.7",
            target_substrates=["acetylcholine"],
            target_organism="Homo sapiens",
            require_substrate_match=False,
        )
        assert entries
        assert entries[0].flagged is True
        assert "kcat" in (entries[0].flag_reason or "").lower()


class TestNoDuplicateRows:
    def test_each_measurement_appears_once(self, kcat_entries):
        """Regression: `rows + subrows` concatenated without deduplicating,
        so a sub-row that also carried class="row" was parsed twice. The Km
        fixtures never tripped it; this capture has 11 such rows, so every
        heavily-studied substrate came back duplicated."""
        keys = [(e.km_value, e.reference_id, e.substrate) for e in kcat_entries]
        assert len(keys) == len(set(keys)), "duplicate measurements returned"


class TestTheOrchestratorIsReachable:
    """`parse_brenda_turnover_html` had no caller when it was written.

    An extraction nothing can invoke is half-delivered: the parser worked,
    but there was no path from "EC number" to "kcat with its conditions"
    the way `fetch_and_parse_brenda_km` provides for Km. These tests drive
    that path with the network stubbed out.
    """

    @staticmethod
    def _stub_network(monkeypatch, html: str):
        """Replace every outbound call with fixture data.

        Substrate resolution is stubbed rather than mocked away entirely so
        the three-tier match (strict -> synonyms -> unverified) still runs.
        """
        monkeypatch.setattr(
            brenda_client, "fetch_brenda_html", lambda ec, timeout=15: html
        )
        monkeypatch.setattr(
            enzyme_lookup, "fetch_uniprot_accession", lambda ec, tax: "P22303"
        )
        monkeypatch.setattr(enzyme_lookup, "fetch_kegg_enzyme_text", lambda ec: "")
        monkeypatch.setattr(
            enzyme_lookup, "parse_kegg_substrates", lambda text: ["acetylcholine"]
        )
        monkeypatch.setattr(
            enzyme_lookup,
            "expand_substrates_with_synonyms",
            lambda subs: list(subs) + SUBSTRATES,
        )

    def test_ec_number_in_kcat_entries_out(self, monkeypatch):
        self._stub_network(monkeypatch, KCAT_FIXTURE.read_text(encoding="utf-8"))

        entries = brenda_client.fetch_and_parse_brenda_kcat("3.1.1.7")

        assert entries, "orchestrator returned nothing from a fixture with 7 rows"
        for entry in entries:
            assert entry.flagged is False, entry.flag_reason
            assert entry.substrate_verified is True
        # The golden tuple survives the full orchestrator path, not just the
        # parser called directly.
        assert any(
            e.km_value == 118.0
            and e.reference_id == "750291"
            and e.assay_ph == 7.4
            and e.assay_temperature_c == 37.0
            for e in entries
        )

    def test_every_matching_tier_reads_the_turnover_table(self, monkeypatch):
        """`table_label` must thread through ALL THREE tiers, not just the
        one a given query happens to reach.

        Found by mutation: dropping `table_label` from the strict tier and
        from the unverified-fallback tier both left the suite green,
        because the stubbed substrates made an earlier tier succeed and the
        later ones never ran. A call site no test reaches is a call site
        with no coverage.

        This drives each tier in isolation and asserts the label every
        time, by spying on the shared parser.
        """
        html = KCAT_FIXTURE.read_text(encoding="utf-8")
        self._stub_network(monkeypatch, html)

        seen: list = []
        original = brenda_client.parse_brenda_km_html

        def spy(*args, **kwargs):
            seen.append(kwargs.get("table_label", "<not passed>"))
            return original(*args, **kwargs)

        monkeypatch.setattr(brenda_client, "parse_brenda_km_html", spy)

        # Tier 3: nothing matches by name, so strict and synonym-expanded
        # both return empty and the unverified fallback runs.
        monkeypatch.setattr(
            enzyme_lookup, "parse_kegg_substrates", lambda text: ["not-a-real-substrate"]
        )
        monkeypatch.setattr(
            enzyme_lookup,
            "expand_substrates_with_synonyms",
            lambda subs: ["still-not-a-real-substrate"],
        )

        entries = brenda_client.fetch_and_parse_brenda_kcat("3.1.1.7")

        assert len(seen) == 3, f"expected all three tiers to run, saw {len(seen)}"
        assert all(label == TURNOVER_TABLE_LABEL for label in seen), seen
        # The fallback tier returns real rows, marked unverified.
        assert entries
        assert all(e.substrate_verified is False for e in entries)

    def test_it_reads_the_turnover_table_not_the_km_table(self, monkeypatch):
        """The delegation must actually change which table is read.

        If `table_label` failed to thread through, this would fall back to a
        whole-page scan and flag every row -- so the assertion is on the
        flags, not merely on getting some result.
        """
        self._stub_network(monkeypatch, KCAT_FIXTURE.read_text(encoding="utf-8"))

        kcat_entries = brenda_client.fetch_and_parse_brenda_kcat("3.1.1.7")
        km_entries = brenda_client.fetch_and_parse_brenda_km("3.1.1.7")

        assert all(e.flagged is False for e in kcat_entries)
        # The same HTML read as a KM Values table has no such container, so
        # every row comes back unscoped and flagged.
        assert km_entries, "expected the Km path to still return rows"
        assert any(e.flagged for e in km_entries), (
            "reading the turnover fixture as KM Values should flag rows as "
            "unscoped; if it does not, table_label is not threading through"
        )


def _all_kcat_fixtures() -> list:
    """Every captured turnover fixture in the repository.

    Discovered by glob rather than listed, so a newly captured enzyme is
    covered by the invariants below the moment it lands -- without anyone
    remembering to add it here. The AChE-specific tests above still pin the
    exact golden values; these check what must hold for ANY turnover table.
    """
    return sorted(FIXTURES.glob("brenda_*_kcat_fixture.html"))


@pytest.mark.parametrize(
    "fixture", _all_kcat_fixtures(), ids=lambda p: p.stem.replace("brenda_", "")
)
class TestInvariantsAcrossEveryCapturedEnzyme:
    """Properties that must hold for every turnover table, not just AChE.

    The parser had only ever seen one BRENDA page when it was written, and
    that is exactly how the duplicate-row bug survived: the Km fixtures
    could not reach it, so nothing caught it until a second page shape
    arrived. These run against whatever has been captured.
    """

    @staticmethod
    def _parse(fixture):
        return parse_brenda_turnover_html(
            html=fixture.read_text(encoding="utf-8"),
            ec_number="0.0.0.0",  # not used for matching in permissive mode
            target_substrates=[],
            target_organism=None,  # cross-species: accept every organism
            require_substrate_match=False,
        )

    def test_the_fixture_parses_to_at_least_one_entry(self, fixture):
        entries = self._parse(fixture)
        assert entries, f"{fixture.name} parsed to zero entries"

    def test_no_duplicate_measurements(self, fixture):
        """The regression that motivated capturing a second enzyme.

        `rows + subrows` concatenated without dedup, so a sub-row also
        carrying class="row" was parsed twice. It was invisible until a
        page with 11 such rows showed up.

        The key MUST include `conditions`. Without it this test reported a
        false positive on real AChE data: three sub-rows carrying
        kcat 2667 s^-1, ref 652194, Mus musculus, acetylthiocholine iodide
        -- identical in every other cell -- are the **wild-type enzyme, the
        A262C mutant, and the E81C mutant**, which share that turnover
        number to the reported precision.

        They are three measurements of three different proteins. A dedup
        that collapsed them would silently delete real data, which is worse
        than the duplication it set out to prevent.
        """
        entries = self._parse(fixture)
        keys = [
            (e.km_value, e.reference_id, e.substrate, e.organism, e.conditions)
            for e in entries
        ]
        assert len(keys) == len(set(keys)), f"{fixture.name} returned duplicates"

    def test_variants_sharing_a_value_are_kept_apart(self, fixture):
        """Guards the distinction the test above depends on.

        If `conditions` ever stopped being captured, the dedup key would
        collapse genuinely different enzyme variants into one entry and the
        test above would still pass -- silently, because there would be
        nothing left to tell them apart.
        """
        entries = self._parse(fixture)
        by_value: dict = {}
        for entry in entries:
            # `substrate` belongs in the key. Without it this grouped two
            # real Mus musculus H287C rows -- kcat 3000 s^-1 measured on
            # Acetylcholine (ref 652016) and on acetylthiocholine iodide
            # (ref 652194) -- and then demanded they have distinct
            # commentary, which they correctly do not: the same mutant can
            # turn over two substrates at the same rate.
            key = (entry.km_value, entry.reference_id, entry.organism, entry.substrate)
            by_value.setdefault(key, []).append(entry)

        for group in by_value.values():
            if len(group) > 1:
                commentaries = {e.conditions for e in group}
                assert len(commentaries) == len(group), (
                    f"{fixture.name}: {len(group)} entries share a value and "
                    "reference but do not have distinct commentary -- either "
                    "they are true duplicates, or `conditions` is no longer "
                    "being captured"
                )

    def test_every_value_is_a_plausible_turnover_number(self, fixture):
        """Km bounds would flag real fast enzymes; kcat bounds must not."""
        for entry in self._parse(fixture):
            assert KCAT_PLAUSIBLE_MIN_PER_S <= entry.km_value <= KCAT_PLAUSIBLE_MAX_PER_S, (
                f"{fixture.name}: kcat {entry.km_value} outside plausible range"
            )

    def test_rows_are_table_scoped(self, fixture):
        """Each fixture must carry its nav anchor. Without it the parser
        falls back to a whole-page scan and flags everything -- the defect
        the capture script was fixed for."""
        for entry in self._parse(fixture):
            assert getattr(entry, "table_scoped", True) is True, (
                f"{fixture.name}: row not table-scoped; was the nav anchor "
                "captured alongside the container?"
            )

    def test_assay_conditions_are_parsed_where_reported(self, fixture):
        """Not every row reports conditions -- BRENDA often says so
        explicitly. But any value that IS parsed must be physically
        sensible, never a stray number from the commentary."""
        for entry in self._parse(fixture):
            if entry.assay_ph is not None:
                assert 0.0 <= entry.assay_ph <= 14.0, f"{fixture.name}: pH {entry.assay_ph}"
            if entry.assay_temperature_c is not None:
                assert -20.0 <= entry.assay_temperature_c <= 150.0, (
                    f"{fixture.name}: T {entry.assay_temperature_c}"
                )


LDH_KCAT_FIXTURE = FIXTURES / "brenda_ldh_kcat_fixture.html"


class TestLdhTurnoverGolden:
    """A second enzyme, captured live 2026-08-02 from BRENDA EC 1.1.1.27.

    The point of a second fixture is generality: the parser had only ever
    seen one BRENDA page, and the commentary-cell bug (§ Stage 8 Part 3
    §5a) existed precisely because one page could not expose it. This one
    is structurally different -- 92 entries across eight-plus organisms,
    heavy aggregate expansion, no human rows at all.

    Every value below was read out of the fixture HTML before being
    asserted, not copied from the parser's own output.
    """

    @staticmethod
    def _entries():
        # Assertion, not skipif. The fixture is committed, so its absence is
        # a broken checkout rather than an environment to tolerate -- and a
        # class-level skipif would retire all five goldens silently, which
        # is the exact pattern check_no_silent_skips.py exists to catch.
        assert LDH_KCAT_FIXTURE.exists(), (
            f"committed fixture missing: {LDH_KCAT_FIXTURE}"
        )
        return parse_brenda_turnover_html(
            html=LDH_KCAT_FIXTURE.read_text(encoding="utf-8"),
            ec_number="1.1.1.27",
            target_substrates=[],
            target_organism=None,
            require_substrate_match=False,
        )

    def test_the_fixture_yields_a_substantial_cross_species_table(self):
        entries = self._entries()
        assert len(entries) > 50, f"only {len(entries)} entries"
        organisms = {e.organism for e in entries}
        assert len(organisms) >= 8, organisms
        # No human rows. Worth pinning: the AChE tests filtered to
        # Homo sapiens, and that filter is exactly what hid the mutant
        # rows which exposed the commentary-cell bug.
        assert "Homo sapiens" not in organisms

    def test_golden_row_hand_verified_against_the_fixture_html(self):
        """Raw HTML row `tab44r16sr6`:

            17479 | phenylpyruvate | Lacticaseibacillus casei | A0A2U9AUU1
            | "mutant Q88R, presence of D-fructose-1,6-diphosphate,
               pH 5.5, 30 C" | 761568
        """
        match = [
            e for e in self._entries()
            if e.km_value == 17479.0 and e.reference_id == "761568"
        ]
        assert len(match) == 1
        entry = match[0]
        assert entry.substrate == "phenylpyruvate"
        assert entry.organism == "Lacticaseibacillus casei"
        assert entry.assay_ph == 5.5
        assert entry.assay_temperature_c == 30.0
        assert "Q88R" in (entry.conditions or "")
        assert entry.flagged is False

    def test_zero_celsius_is_a_real_temperature_not_a_falsy_placeholder(self):
        """*Champsocephalus gunnari* is an Antarctic icefish; 0 C is its
        physiological assay temperature, and the commentary says so
        ("pH 7.0, 0 C, recombinant enzyme").

        A truthiness check anywhere in the chain would silently drop it and
        report the record as temperature-less. This is the same class of
        bug as pH 0 being discarded, guarded in the STRENDA suite.
        """
        icefish = [
            e for e in self._entries()
            if e.organism == "Champsocephalus gunnari"
        ]
        assert icefish, "the icefish rows vanished from the fixture"
        zero_c = [e for e in icefish if e.assay_temperature_c == 0.0]
        assert zero_c, "0 C was dropped as falsy"
        assert zero_c[0].assay_ph == 7.0

    def test_explicitly_unreported_is_distinguished_from_merely_absent(self):
        """The distinction ADR 0010 exists for, holding on unseen data.

        BRENDA states "temperature not specified in the publication" on
        some rows -- a fact about the literature. Others simply carry no
        temperature -- a fact about our parsing. Collapsing the two would
        make an honest gap indistinguishable from a silent one.
        """
        entries = self._entries()
        stated = [e for e in entries if "temperature" in (e.assay_unreported or [])]
        assert stated, "no row records an explicitly-unreported temperature"
        for entry in stated:
            assert entry.assay_temperature_c is None
            # The claim must come from the commentary, not from nowhere.
            assert "not specified" in (entry.conditions or "").lower()

    def test_a_majority_of_rows_carry_complete_assay_conditions(self):
        """Measured, not aspirational: 52 of 92 rows (57%) are
        STRENDA-complete in this capture, versus ~41% across the Km
        fixtures. Asserted loosely so a fixture refresh does not fail on a
        few rows, but tightly enough to catch the conditions pipeline
        breaking wholesale.
        """
        entries = self._entries()
        complete = [
            e for e in entries
            if e.assay_ph is not None and e.assay_temperature_c is not None
        ]
        assert len(complete) / len(entries) > 0.4, (
            f"only {len(complete)}/{len(entries)} rows are STRENDA-complete"
        )


class TestCommentaryIsReadByPositionNotLength:
    """`conditions` used to be `max(cell_texts, key=len)` -- the longest cell.

    That silently returns the SUBSTRATE whenever the substrate name is
    longer than the commentary, which is common. Found by running the
    invariants against the AChE turnover table cross-species: three real
    Mus musculus sub-rows with commentaries "wild-type enzyme",
    "A262C mutant" and "E81C mutant" (16, 12, 11 chars) all lost to
    "acetylthiocholine iodide" (24 chars).

    The consequence was not cosmetic. The three mutants became
    indistinguishable, and every assay condition on an aggregate sub-row
    was discarded -- the STRENDA data ADR 0010 exists to preserve.
    """

    def test_a_short_commentary_survives_a_long_substrate_name(self):
        entries = parse_brenda_turnover_html(
            html=KCAT_FIXTURE.read_text(encoding="utf-8"),
            ec_number="3.1.1.7",
            target_substrates=[],
            target_organism=None,
            require_substrate_match=False,
        )
        mutants = {
            e.conditions
            for e in entries
            if e.organism == "Mus musculus" and e.km_value == 2667.0
        }
        assert mutants == {"wild-type enzyme", "A262C mutant", "E81C mutant"}, mutants

    def test_the_commentary_is_never_the_substrate(self):
        entries = parse_brenda_turnover_html(
            html=KCAT_FIXTURE.read_text(encoding="utf-8"),
            ec_number="3.1.1.7",
            target_substrates=[],
            target_organism=None,
            require_substrate_match=False,
        )
        checked = 0
        for entry in entries:
            if entry.conditions is not None:
                checked += 1
                assert entry.conditions != entry.substrate, (
                    f"commentary equals substrate for kcat {entry.km_value} -- "
                    "the longest-cell heuristic is back"
                )

        # Without this the test passes when NO entry has commentary -- which
        # is precisely what a parser regression looks like. The defect it
        # names ("the longest-cell heuristic is back") and the state that
        # makes it vacuous are the same failure, so it would have gone green
        # exactly when it mattered.
        #
        # 71 of the fixture's 72 rows carry commentary today. The threshold
        # is 1 rather than 71: this test is about the substrate/commentary
        # confusion, and pinning the corpus size is another test's job.
        assert checked > 0, (
            f"none of the {len(entries)} parsed rows carried commentary, so "
            "this test checked nothing -- the parser has stopped capturing "
            "`conditions`"
        )

    def test_an_absent_commentary_is_none_not_the_organism(self):
        """Rows whose commentary cell is "-" must report None.

        The old heuristic filled them with whatever else was on the row --
        usually the organism. Two real LDH pyruvate rows came back with
        conditions="Homo sapiens", claiming a commentary that never existed.
        """
        ldh = FIXTURES / "brenda_ldh_fixture.html"
        assert ldh.exists()
        entries = parse_brenda_km_html(
            html=ldh.read_text(encoding="utf-8"),
            ec_number="1.1.1.27",
            target_substrates=["pyruvate"],
            target_organism=None,
            require_substrate_match=False,
        )
        assert entries
        for entry in entries:
            assert entry.conditions != entry.organism, (
                f"conditions leaked the organism for km {entry.km_value}"
            )


class TestTableScoping:
    def test_entries_are_table_scoped(self, kcat_entries):
        """A fixture holding only the container has no nav link to match, so
        the parser falls back to a whole-page scan and flags everything as
        unconfirmed. The capture script now saves the anchor too."""
        for entry in kcat_entries:
            assert getattr(entry, "table_scoped", True) is True

    def test_the_label_constant_matches_brendas_navigation_text(self):
        assert TURNOVER_TABLE_LABEL == "Turnover Numbers"
