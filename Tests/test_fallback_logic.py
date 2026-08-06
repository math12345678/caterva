"""
pytest suite for fallback_logic.py

Exercises the full exact -> cross-species -> literature resolution chain
entirely offline by injecting fixture HTML as the html_provider, a fake
uniprot_provider (standing in for the real UniProt API call), and by
monkeypatching the PubMed literature call. No network access required.
"""

import os

import pytest

import fallback_logic
from fallback_logic import LiteratureCandidate, resolve_kinetic_value

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Stand-in for enzyme_lookup.fetch_uniprot_accession in offline tests.
# Real accessions (previously verified against live BRENDA/UniProt), so
# tests still exercise meaningful values rather than placeholders.
FAKE_UNIPROT_BY_EC = {
    "1.1.1.27": "P00338",
    "3.1.1.7": "P22303",
}


def fake_uniprot_provider(ec_number: str, taxon_id: str):
    return FAKE_UNIPROT_BY_EC.get(ec_number)


# Stand-in for enzyme_lookup.fetch_taxon_id in offline tests - real NCBI
# taxon IDs (previously verified), so tests exercise meaningful values
# without a live network call.
FAKE_TAXON_IDS = {
    "Homo sapiens": "9606",
    "Sus scrofa": "9823",
    "Mus musculus": "10090",
}


def fake_taxon_id_provider(organism_name: str):
    return FAKE_TAXON_IDS.get(organism_name)


def load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return f.read()


def make_html_provider(html_by_ec: dict):
    """Build an html_provider function (matches HtmlProvider signature)
    that returns fixture HTML by EC number instead of hitting BRENDA."""

    def provider(ec_number: str) -> str:
        return html_by_ec[ec_number]

    return provider


@pytest.fixture
def ldh_provider():
    return make_html_provider({"1.1.1.27": load_fixture("brenda_ldh_fixture.html")})


@pytest.fixture
def ldh_ki_provider():
    return make_html_provider({"1.1.1.27": load_fixture("brenda_ldh_ki_fixture.html")})


@pytest.fixture
def ache_provider():
    return make_html_provider({"3.1.1.7": load_fixture("brenda_ache_fixture.html")})


# ---------------------------------------------------------------------------
# Tier 1: exact match
# ---------------------------------------------------------------------------

def test_resolves_exact_human_match_for_ldh(ldh_provider):
    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "lactate",
        html_provider=ldh_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
    )
    assert result.found is True
    assert result.source == "brenda_exact"
    # Two real (S)-lactate rows exist for Homo sapiens in the fixture
    # (10.73 healthy tissue, 21.78 cancer tissue, both ref 740253);
    # resolve_kinetic_value takes the minimum among exact matches.
    assert result.value == 10.73
    assert result.organism == "Homo sapiens"
    assert result.cross_species_flag is False


def test_exact_match_carries_a_real_citation(ldh_provider):
    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "lactate",
        html_provider=ldh_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
    )
    assert result.citation is not None
    assert result.citation.source == "BRENDA"
    assert result.citation.reference_id == "740253"
    assert result.citation.url is not None


def test_exact_match_search_log_records_the_attempt(ldh_provider):
    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "lactate",
        html_provider=ldh_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
    )
    assert any("BRENDA exact" in entry for entry in result.search_log)


# ---------------------------------------------------------------------------
# Tier 1 excludes flagged rows: the implausible AChE Kcat-as-Km row must
# never surface as a "found" exact-match result.
# ---------------------------------------------------------------------------

def test_flagged_brenda_row_is_not_returned_as_exact_match(ache_provider):
    result = resolve_kinetic_value(
        "3.1.1.7",
        "Homo sapiens",
        "acetyl thiocholine",
        html_provider=ache_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )
    # Two matching rows exist (0.09 genuine, 6500 flagged). Must pick the
    # genuine one and never the flagged one.
    assert result.found is True
    assert result.value == 0.09


# ---------------------------------------------------------------------------
# Tier 2: cross-species fallback
# ---------------------------------------------------------------------------

def test_falls_back_to_cross_species_when_no_human_row_matches(ldh_provider):
    # "L-lactate" isn't literally in the LDH fixture as its own substrate
    # string separate from "lactate", so instead exercise cross-species by
    # asking for an organism with no human row: use a substrate that only
    # appears on the non-human (Sus scrofa) row's condition text? The
    # fixture's Sus scrofa row uses "lactate" too, so query with a human
    # organism string that won't match human but will match pig via
    # cross-species by asking for a substrate present only there.
    result = resolve_kinetic_value(
        "1.1.1.27",
        "Mus musculus",  # no mouse row exists in the fixture at all
        "lactate",
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )
    assert result.found is True
    assert result.source == "brenda_cross_species"
    assert result.cross_species_flag is True
    assert result.organism in {"Homo sapiens", "Sus scrofa"}


def test_cross_species_result_still_has_citation(ldh_provider):
    result = resolve_kinetic_value(
        "1.1.1.27",
        "Mus musculus",
        "lactate",
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )
    assert result.citation is not None
    assert result.citation.source == "BRENDA"


# ---------------------------------------------------------------------------
# Tier 3: literature candidates (mocked, no real PubMed call)
# ---------------------------------------------------------------------------

def test_falls_back_to_literature_when_brenda_has_nothing(monkeypatch, ldh_provider):
    def fake_pubmed(enzyme_name, organism, substrate, max_results=5, quantity="km"):
        return [
            LiteratureCandidate(
                pmid="99999999",
                title="A fake but structurally valid candidate paper",
                url="https://pubmed.ncbi.nlm.nih.gov/99999999/",
            )
        ]

    monkeypatch.setattr(fallback_logic, "search_pubmed_candidates", fake_pubmed)

    result = resolve_kinetic_value(
        "1.1.1.27",
        "Homo sapiens",
        "a-substrate-not-in-any-fixture-row",
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
    )
    assert result.found is False
    assert result.source == "literature_candidates"
    assert len(result.literature_candidates) == 1
    assert result.literature_candidates[0].pmid == "99999999"


def test_literature_search_never_fabricates_a_numeric_value(monkeypatch, ldh_provider):
    """Regression guard for the original stub, which hardcoded a fake
    literature result (1.02 mM / Sus scrofa / PMID 34962677) regardless of
    input. The real implementation must never return found=True from the
    literature tier - only candidate references for human review."""

    def fake_pubmed(enzyme_name, organism, substrate, max_results=5, quantity="km"):
        return [
            LiteratureCandidate(
                pmid="34962677",
                title="Some paper that mentions Km somewhere in its abstract",
                url="https://pubmed.ncbi.nlm.nih.gov/34962677/",
            )
        ]

    monkeypatch.setattr(fallback_logic, "search_pubmed_candidates", fake_pubmed)

    result = resolve_kinetic_value(
        "1.1.1.27",
        "Homo sapiens",
        "a-substrate-not-in-any-fixture-row",
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
    )
    assert result.found is False
    assert result.value is None
    assert result.source == "literature_candidates"


def test_genuine_gap_when_nothing_found_anywhere(monkeypatch, ldh_provider):
    def empty_pubmed(enzyme_name, organism, substrate, max_results=5, quantity="km"):
        return []

    monkeypatch.setattr(fallback_logic, "search_pubmed_candidates", empty_pubmed)

    result = resolve_kinetic_value(
        "1.1.1.27",
        "Homo sapiens",
        "a-substrate-not-in-any-fixture-row",
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
    )
    assert result.found is False
    assert result.source == "not_found"
    assert "genuine gap" in result.search_log[-1]


class TestAssayConditionsReachTheResult:
    """The Km carries the conditions it was measured under (ADR 0010).

    STRENDA requires temperature and pH for all reported kinetic data.
    These tests assert the values survive the whole exact/cross-species
    chain rather than being dropped at the KineticResult boundary --
    which is exactly where they were silently lost before.
    """

    def test_ph_reaches_the_result_and_absent_temperature_is_reported(
        self, ldh_provider
    ):
        """The (S)-lactate rows read 'pH 8.0, temperature not specified
        in the publication'. BRENDA is stating the original authors did
        not report the temperature -- a fact about the literature. The
        pH must arrive; the temperature must stay absent and be named
        as unreported rather than guessed."""
        result = resolve_kinetic_value(
            "1.1.1.27",
            "Homo sapiens",
            "(S)-lactate",
            html_provider=ldh_provider,
            uniprot_provider=fake_uniprot_provider,
            taxon_id_provider=fake_taxon_id_provider,
            search_literature=False,
        )
        assert result.found is True
        assert result.assay_ph == 8.0
        assert result.assay_temperature_c is None
        assert "temperature" in result.assay_unreported

    def test_absent_conditions_are_absent_not_defaulted(self, ldh_provider):
        """The pyruvate rows have '-' as their comment: no conditions
        reported at all. Nothing may be invented to fill the gap."""
        result = resolve_kinetic_value(
            "1.1.1.27",
            "Homo sapiens",
            "pyruvate",
            html_provider=ldh_provider,
            uniprot_provider=fake_uniprot_provider,
            taxon_id_provider=fake_taxon_id_provider,
            search_literature=False,
        )
        assert result.found is True
        assert result.assay_ph is None
        assert result.assay_temperature_c is None

    def test_cross_species_result_also_carries_conditions(self, ldh_provider):
        """The cross-species path is a separate construction site, so it
        can drop the fields independently of the exact path. The Sus
        scrofa row reads 'pH 8.5, 25 C, isozyme H4' -- STRENDA-complete."""
        result = resolve_kinetic_value(
            "1.1.1.27",
            "Mus musculus",  # absent from the fixture -> forces cross-species
            "(S)-lactate",
            html_provider=ldh_provider,
            uniprot_provider=fake_uniprot_provider,
            taxon_id_provider=fake_taxon_id_provider,
            search_literature=False,
        )
        assert result.found is True
        assert result.cross_species_flag is True
        # Conditions must be present on this path too, whichever row won.
        assert result.assay_ph is not None


# ---------------------------------------------------------------------------
# Empty substrate ("we don't know it yet" -- the live UniProt/KEGG path hits
# this for peptidases, whose KEGG entries have no SUBSTRATE field).
#
# Regression test for a real bug found live-testing 'run kinetics trypsin':
# an empty-string substrate with the implicit require_substrate_match=True
# silently rejected every BRENDA row (an empty string is a substring of
# everything, so it "matches", but "" is itself falsy -- the strict branch
# saw `not matched_substrate` as True and continue'd past every row). Fixed
# in _brenda_entries by switching to permissive matching whenever substrate
# is empty, instead of passing an empty string into the strict matcher.
# ---------------------------------------------------------------------------

def test_empty_substrate_still_resolves_via_permissive_matching(ldh_provider):
    """Before the fix, this returned found=False for every enzyme resolved
    with no known substrate -- not just trypsin, ANY enzyme reached via the
    live UniProt/KEGG path when KEGG had no SUBSTRATE field. The real
    BRENDA data must still surface, correctly marked unverified."""
    result = resolve_kinetic_value(
        "1.1.1.27",
        "Homo sapiens",
        "",  # unknown substrate, exactly what science_agent_runner.py sends
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )
    assert result.found is True
    assert result.value is not None


def test_search_literature_false_skips_pubmed_entirely(monkeypatch, ldh_provider):
    def should_not_be_called(*args, **kwargs):
        raise AssertionError("search_pubmed_candidates should not be called")

    monkeypatch.setattr(fallback_logic, "search_pubmed_candidates", should_not_be_called)

    result = resolve_kinetic_value(
        "1.1.1.27",
        "Homo sapiens",
        "a-substrate-not-in-any-fixture-row",
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )
    assert result.found is False


# ---------------------------------------------------------------------------
# Ki (inhibition constant) resolution -- quantity="ki" reads BRENDA's
# "Ki Values" table through the same exact -> cross-species chain as Km,
# each with its own citation (see ADR 0008 / provenance.ts). The golden
# rows are the live-captured gossypol sub-rows in
# fixtures/brenda_ldh_ki_fixture.html (refs 711801 / 654758) -- gossypol
# is THE classic LDH inhibitor and appears only in the compound-name cell
# of its rows, never in a commentary, so the rows are unambiguous.
# ---------------------------------------------------------------------------

def test_resolves_exact_human_ki_for_ldh_gossypol(ldh_ki_provider):
    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "gossypol",
        html_provider=ldh_ki_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="ki",
    )
    assert result.found is True
    assert result.source == "brenda_exact"
    # Three real Homo sapiens gossypol sub-rows exist (LDH-B/A/C, 0.0014 /
    # 0.0019 / 0.0042, all ref 711801); the minimum is the LDH-B isozyme.
    assert result.value == 0.0014
    assert result.organism == "Homo sapiens"
    assert result.cross_species_flag is False
    assert result.citation is not None
    assert result.citation.source == "BRENDA"
    assert result.citation.reference_id == "711801"
    assert result.citation.url is not None
    # The gossypol rows carry "pH not specified ... temperature not
    # specified in the publication" -- parsed as explicitly unreported,
    # never guessed.
    assert "pH" in result.assay_unreported
    assert "temperature" in result.assay_unreported


def test_ki_cross_species_resolves_and_is_flagged(ldh_ki_provider):
    result = resolve_kinetic_value(
        "1.1.1.27", "Mus musculus", "gossypol",
        html_provider=ldh_ki_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="ki",
    )
    assert result.found is True
    assert result.source == "brenda_cross_species"
    assert result.cross_species_flag is True
    # Minimum gossypol Ki across organisms: 0.0007 mM Plasmodium
    # falciparum (Q27743), ref 654758 -- a real cross-species record.
    assert result.value == 0.0007
    assert result.organism == "Plasmodium falciparum"
    assert result.citation.reference_id == "654758"


def test_ki_never_fabricates_when_table_has_no_match(ldh_ki_provider):
    """lactate is LDH's real substrate but is NOT an inhibitor of it --
    BRENDA's Ki table has no lactate rows. The chain must say not-found,
    never invent a Ki from Km data or a plausible-looking number."""
    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "lactate",
        html_provider=ldh_ki_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="ki",
    )
    assert result.found is False
    assert result.source == "not_found"
    assert result.value is None


def test_quantity_selects_which_table_is_read(ldh_ki_provider, ldh_provider):
    """The same fixture must yield DIFFERENT results depending on quantity:
    quantity="ki" reads the Ki Values table, quantity="km" reads the KM
    Values table (or, with no KM container present, the whole-page
    fallback whose rows are all flagged and therefore excluded). This is
    the check that Ki and Km resolve independently rather than sharing a
    lookup."""
    # The Ki fixture has no KM Values container: a km lookup finds nothing
    # structurally, and every whole-page-fallback row is flagged and
    # excluded from "found" results.
    km_from_ki_fixture = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "gossypol",
        html_provider=ldh_ki_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="km",
    )
    assert km_from_ki_fixture.found is False

    # Conversely, the Km fixture has no Ki Values container: a ki lookup
    # on it must not return the lactate Km rows.
    ki_from_km_fixture = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "lactate",
        html_provider=ldh_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="ki",
    )
    assert ki_from_km_fixture.found is False

    # And the golden paths still work when quantity is explicit.
    ki_found = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "gossypol",
        html_provider=ldh_ki_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="ki",
    )
    assert ki_found.found is True
    assert ki_found.value == 0.0014


def test_ki_exact_row_does_not_borrow_km_provenance(ldh_ki_provider, ldh_provider):
    """The independent-resolution contract (staged provenance.ts comment):
    a resolved Ki carries its OWN citation (ref 711801), never the Km
    golden citation (740253). Both quantities resolve on the same enzyme
    page but from different tables with different refs."""
    km = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "(S)-lactate",
        html_provider=ldh_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="km",
    )
    ki = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "gossypol",
        html_provider=ldh_ki_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="ki",
    )
    assert km.found is True and ki.found is True
    assert km.citation.reference_id == "740253"
    assert ki.citation.reference_id == "711801"
    assert km.citation.reference_id != ki.citation.reference_id
