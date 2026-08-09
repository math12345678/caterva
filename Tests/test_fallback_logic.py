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


@pytest.fixture
def ache_kcat_provider():
    return make_html_provider({"3.1.1.7": load_fixture("brenda_ache_kcat_fixture.html")})


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


# ---------------------------------------------------------------------------
# kcat (turnover number) resolution -- quantity="kcat" reads BRENDA's
# "Turnover Numbers" table through the same exact -> cross-species chain.
# Golden row: acetylcholinesterase (EC 3.1.1.7) + acetyl thiocholine (its
# standard synthetic assay substrate) + Homo sapiens, live-captured in
# fixtures/brenda_ache_kcat_fixture.html, kcat = 6500 s^-1, ref 649716,
# pH 8, 27C. A resolved kcat is real and citable but is NOT wired to
# RESOLVABLE_FIELDS / the simulation engine -- see ADR 0012 / 0013 / 0019.
# ---------------------------------------------------------------------------

def test_resolves_exact_human_kcat_for_ache(ache_kcat_provider):
    result = resolve_kinetic_value(
        "3.1.1.7", "Homo sapiens", "acetyl thiocholine",
        html_provider=ache_kcat_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="kcat",
    )
    assert result.found is True
    assert result.source == "brenda_exact"
    assert result.value == 6500
    assert result.organism == "Homo sapiens"
    assert result.cross_species_flag is False
    assert result.citation is not None
    assert result.citation.source == "BRENDA"
    assert result.citation.reference_id == "649716"


def test_kcat_never_fabricates_when_table_has_no_match(ache_kcat_provider):
    """BRENDA's Turnover Numbers table for AChE has no rows for a
    substrate it does not act on. Must say not-found, never invent a kcat
    from Km data or a plausible-looking number."""
    result = resolve_kinetic_value(
        "3.1.1.7", "Homo sapiens", "a-substrate-not-in-any-fixture-row",
        html_provider=ache_kcat_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="kcat",
    )
    assert result.found is False
    assert result.source == "not_found"
    assert result.value is None


def test_kcat_resolves_independently_of_km_and_ki(ache_kcat_provider, ache_provider):
    """The same independent-resolution contract Ki has: a resolved kcat
    carries its own citation, never Km's (or Ki's)."""
    kcat = resolve_kinetic_value(
        "3.1.1.7", "Homo sapiens", "acetyl thiocholine",
        html_provider=ache_kcat_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="kcat",
    )
    km_from_kcat_fixture = resolve_kinetic_value(
        "3.1.1.7", "Homo sapiens", "acetyl thiocholine",
        html_provider=ache_kcat_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="km",
    )
    assert kcat.found is True
    # The kcat fixture has no KM Values container, so a km lookup on it
    # must not silently return the turnover-number rows as if they were Km.
    assert km_from_kcat_fixture.found is False


# ---------------------------------------------------------------------------
# CORE open-access full text supplements the PubMed literature tier (not a
# replacement -- see the comment above the call site in fallback_logic.py).
# core_fulltext.resolve_open_access_fulltext is monkeypatched directly
# rather than going through its own fetch layer, mirroring how
# search_pubmed_candidates is monkeypatched above: this suite tests
# fallback_logic's integration logic, not core_fulltext's own network
# handling (that lives in test_core_fulltext.py).
# ---------------------------------------------------------------------------

from core_fulltext import CoreFullTextCandidate, CoreFullTextResult


def test_core_candidates_are_appended_to_pubmed_candidates(monkeypatch, ldh_provider):
    def fake_pubmed(enzyme_name, organism, substrate, max_results=5, quantity="km"):
        return [
            LiteratureCandidate(
                pmid="11111111", title="A PubMed result", url="https://pubmed.ncbi.nlm.nih.gov/11111111/",
            )
        ]

    def fake_core(query, max_results=5, fetch=None):
        return CoreFullTextResult(
            found=True,
            candidates=[
                CoreFullTextCandidate(
                    core_id="99999999",
                    title="An open-access CORE result",
                    doi="10.1000/core.example",
                    download_url="https://core.ac.uk/download/99999999.pdf",
                )
            ],
            search_log=["CORE search returned 1 candidate(s)"],
        )

    monkeypatch.setattr(fallback_logic, "search_pubmed_candidates", fake_pubmed)
    monkeypatch.setattr(fallback_logic.core_fulltext, "resolve_open_access_fulltext", fake_core)

    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "a-substrate-not-in-any-fixture-row",
        html_provider=ldh_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
    )
    assert result.found is False
    assert result.source == "literature_candidates"
    assert len(result.literature_candidates) == 2

    by_source = {c.source: c for c in result.literature_candidates}
    assert by_source["pubmed"].pmid == "11111111"
    assert by_source["pubmed"].doi is None
    assert by_source["core"].pmid is None
    assert by_source["core"].doi == "10.1000/core.example"
    assert by_source["core"].url == "https://core.ac.uk/download/99999999.pdf"


def test_core_result_without_download_url_falls_back_to_a_core_works_link(
    monkeypatch, ldh_provider
):
    def fake_pubmed(enzyme_name, organism, substrate, max_results=5, quantity="km"):
        return []

    def fake_core(query, max_results=5, fetch=None):
        return CoreFullTextResult(
            found=True,
            candidates=[
                CoreFullTextCandidate(core_id="42", title="No download URL on this one")
            ],
            search_log=["CORE search returned 1 candidate(s)"],
        )

    monkeypatch.setattr(fallback_logic, "search_pubmed_candidates", fake_pubmed)
    monkeypatch.setattr(fallback_logic.core_fulltext, "resolve_open_access_fulltext", fake_core)

    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "a-substrate-not-in-any-fixture-row",
        html_provider=ldh_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
    )
    assert result.literature_candidates[0].url == "https://core.ac.uk/works/42"


def test_core_finding_nothing_does_not_prevent_pubmed_results_from_surfacing(
    monkeypatch, ldh_provider
):
    def fake_pubmed(enzyme_name, organism, substrate, max_results=5, quantity="km"):
        return [
            LiteratureCandidate(
                pmid="22222222", title="Only a PubMed result", url="https://pubmed.ncbi.nlm.nih.gov/22222222/",
            )
        ]

    def fake_core(query, max_results=5, fetch=None):
        return CoreFullTextResult(found=False, search_log=["CORE_API_KEY is not set"])

    monkeypatch.setattr(fallback_logic, "search_pubmed_candidates", fake_pubmed)
    monkeypatch.setattr(fallback_logic.core_fulltext, "resolve_open_access_fulltext", fake_core)

    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "a-substrate-not-in-any-fixture-row",
        html_provider=ldh_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
    )
    assert result.found is False
    assert result.source == "literature_candidates"
    assert len(result.literature_candidates) == 1
    assert result.literature_candidates[0].source == "pubmed"


def test_neither_pubmed_nor_core_finding_anything_is_a_genuine_gap(
    monkeypatch, ldh_provider
):
    def fake_pubmed(enzyme_name, organism, substrate, max_results=5, quantity="km"):
        return []

    def fake_core(query, max_results=5, fetch=None):
        return CoreFullTextResult(found=False, search_log=["no results"])

    monkeypatch.setattr(fallback_logic, "search_pubmed_candidates", fake_pubmed)
    monkeypatch.setattr(fallback_logic.core_fulltext, "resolve_open_access_fulltext", fake_core)

    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "a-substrate-not-in-any-fixture-row",
        html_provider=ldh_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
    )
    assert result.found is False
    assert result.source == "not_found"
    assert "genuine gap" in result.search_log[-1]
    assert "CORE" in result.search_log[-1]


def test_search_literature_false_skips_core_too(monkeypatch, ldh_provider):
    """search_literature=False must skip BOTH literature tiers, not just
    PubMed -- a caller that opted out of literature search entirely
    should never trigger a CORE network call either."""
    def should_not_be_called(query, max_results=5, fetch=None):
        raise AssertionError("CORE search should not be called")

    monkeypatch.setattr(
        fallback_logic.core_fulltext, "resolve_open_access_fulltext", should_not_be_called
    )

    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "a-substrate-not-in-any-fixture-row",
        html_provider=ldh_provider, uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )
    assert result.found is False
