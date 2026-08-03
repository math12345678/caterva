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
        assert 6500.0 > 1000.0  # i.e. it WOULD fail the Km bound


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


class TestTableScoping:
    def test_entries_are_table_scoped(self, kcat_entries):
        """A fixture holding only the container has no nav link to match, so
        the parser falls back to a whole-page scan and flags everything as
        unconfirmed. The capture script now saves the anchor too."""
        for entry in kcat_entries:
            assert getattr(entry, "table_scoped", True) is True

    def test_the_label_constant_matches_brendas_navigation_text(self):
        assert TURNOVER_TABLE_LABEL == "Turnover Numbers"
