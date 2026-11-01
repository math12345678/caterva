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
from fixture_lineages import fixture_lineage_provider
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
        allow_cross_species=True,
        lineage_provider=fixture_lineage_provider,
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
        allow_cross_species=True,
        lineage_provider=fixture_lineage_provider,
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

    def test_a_real_buffer_survives_to_the_result_and_the_frontier(
        self, ache_provider
    ):
        """AChE: 'in 0.1 M MOPS buffer (pH 7.4), at 37°C'. The buffer must
        reach the KineticResult AND every candidate dict the frontier emits
        (ADR 0175) -- the assay window re-selects from those dicts without
        a second parse, so dropping 'buffer' here would silently delete the
        only axis that can close a buffer mismatch."""
        result = resolve_kinetic_value(
            "3.1.1.7",
            "Homo sapiens",
            "acetylcholine",
            html_provider=ache_provider,
            uniprot_provider=fake_uniprot_provider,
            taxon_id_provider=fake_taxon_id_provider,
            search_literature=False,
        )
        assert result.found is True
        assert result.value == 0.0714
        assert result.assay_ph == 7.4
        assert result.assay_temperature_c == 37.0
        assert result.assay_buffer == "0.1 M MOPS buffer"
        frontier_buffers = [c.get("buffer") for c in result.ensemble_candidates]
        assert "0.1 M MOPS buffer" in frontier_buffers
        assert all(b is None or isinstance(b, str) for b in frontier_buffers)

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
            allow_cross_species=True,
            lineage_provider=fixture_lineage_provider,
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
        allow_cross_species=True,
        lineage_provider=fixture_lineage_provider,
    )
    assert result.found is True
    assert result.source == "brenda_cross_species"
    assert result.cross_species_flag is True

    # THIS ANSWER CHANGED, AND THE CHANGE IS THE POINT.
    #
    # The lowest gossypol Ki in the fixture is 0.0007 mM in Plasmodium
    # falciparum (ref 654758), and before the relatedness check that is
    # what a Mus musculus query returned -- an apicomplexan parasite's
    # inhibition constant offered as a mouse's. Cryptosporidium parvum was
    # in the running too.
    #
    # Both share only the domain Eukaryota with a mouse, so both are now
    # excluded, and the answer is the Homo sapiens value: still
    # cross-species, still flagged, but between two mammals sharing the
    # superorder Euarchontoglires.
    #
    # "min across all organisms" was never a scientific criterion. It was
    # an arbitrary tie-break that happened to be reproducible, and it
    # selected on the wrong axis entirely.
    assert result.value == 0.0014
    assert result.organism == "Homo sapiens"
    assert result.citation.reference_id == "711801"

    rejected = {v.candidate_organism for v in result.relatedness
                if v.status == "too_distant"}
    assert rejected == {"Plasmodium falciparum", "Cryptosporidium parvum"}


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


# ---------------------------------------------------------------------------
# Tier 2 is OPT-IN (ADR 0024, on Lisa Jeske's recommendation)
#
# The tests above pass allow_cross_species=True because they are testing what
# the cross-species tier DOES. These test whether it fires at all, which is a
# different question and the one that changed.
# ---------------------------------------------------------------------------

def test_cross_species_is_withheld_by_default(ldh_provider):
    """No mouse row exists in the LDH fixture, but human and pig rows do.

    The old behaviour returned the pig value with a warning flag. The
    behaviour Jeske recommended -- and this asserts -- is that nothing is
    returned unless the caller opted in."""
    result = resolve_kinetic_value(
        "1.1.1.27",
        "Mus musculus",
        "lactate",
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )
    assert result.found is False
    assert result.source == "cross_species_withheld"
    assert result.value is None
    assert result.citation is None
    assert result.cross_species_flag is False


def test_withheld_result_names_the_organisms_it_withheld(ldh_provider):
    """A refusal that cannot say what it refused is unactionable: the user
    cannot opt in to something they were never told existed.

    This is the assertion that distinguishes 'withheld' from 'not found',
    and it is the reason cross_species_withheld is a separate source value
    rather than a reuse of not_found."""
    result = resolve_kinetic_value(
        "1.1.1.27",
        "Mus musculus",
        "lactate",
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )
    assert result.cross_species_organisms_available, (
        "withheld result named no organisms, so the opt-in it demands "
        "cannot be exercised"
    )
    assert "Homo sapiens" in result.cross_species_organisms_available
    assert all(
        isinstance(o, str) and o.strip()
        for o in result.cross_species_organisms_available
    )


def test_withheld_is_distinct_from_genuinely_not_found(ldh_provider):
    """'BRENDA has nothing' and 'BRENDA has something you did not ask for'
    must not collapse into the same result, or the caller cannot tell a
    real gap in the literature from a policy decision this code made."""
    withheld = resolve_kinetic_value(
        "1.1.1.27", "Mus musculus", "lactate",
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )
    absent = resolve_kinetic_value(
        "1.1.1.27", "Mus musculus", "a-substrate-that-is-not-in-the-fixture",
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )
    assert withheld.found is absent.found is False
    assert withheld.source == "cross_species_withheld"
    assert absent.source == "not_found"
    assert absent.cross_species_organisms_available == []


def test_exact_match_is_unaffected_by_the_opt_in(ldh_provider):
    """The gate must sit on tier 2 only. If it leaked into tier 1, an exact
    same-organism match would start refusing -- which no one asked for and
    which the withheld tests above would not catch."""
    for flag in (False, True):
        result = resolve_kinetic_value(
            "1.1.1.27",
            "Homo sapiens",
            "lactate",
            html_provider=ldh_provider,
            uniprot_provider=fake_uniprot_provider,
            taxon_id_provider=fake_taxon_id_provider,
            search_literature=False,
            allow_cross_species=flag,
            lineage_provider=fixture_lineage_provider,
        )
        assert result.found is True, f"exact match broke with allow_cross_species={flag}"
        assert result.source == "brenda_exact"
        assert result.cross_species_flag is False


def test_search_log_records_the_withholding(ldh_provider):
    """The log is the audit trail. A value withheld silently is
    indistinguishable from a lookup that never ran."""
    result = resolve_kinetic_value(
        "1.1.1.27", "Mus musculus", "lactate",
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )
    joined = " | ".join(result.search_log)
    assert "withheld" in joined
    assert "allow_cross_species=False" in joined


# ---------------------------------------------------------------------------
# Protein variants are removed from selection BEFORE the minimum is taken
# (ADR 0029)
#
# The exact-match tier needs its own coverage, and it very nearly did not get
# any: the first mutation run disabled this tier's filter entirely and every
# test still passed. The cross-species golden case exercised the OTHER tier,
# and a filter no test can break is a filter someone deletes as dead code.
#
# Mus musculus in the AChE turnover fixture is the case that exercises it:
# 37 rows, 32 of them variants, all under one organism so the exact tier
# fires and never reaches the cross-species branch.
# ---------------------------------------------------------------------------

# `ache_kcat_provider` is defined once, near the top of this file. A second,
# identical copy sat here and silently shadowed it -- pytest takes the last
# fixture of a given name. Identical today, so nothing misbehaved; the hazard
# is the day one of them changes and only one is in effect, with no error
# anywhere. Found by ruff's F811, which is configured in pyproject.toml and
# was executed by nothing.


def _resolve_mouse_ache(provider, **kwargs):
    return resolve_kinetic_value(
        "3.1.1.7", "Mus musculus", "acetylthiocholine",
        html_provider=provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity="kcat",
        lineage_provider=fixture_lineage_provider,
        **kwargs,
    )


def test_exact_tier_excludes_variant_rows_from_selection(ache_kcat_provider):
    """32 of the 37 mouse rows are mutants, and selection is min().

    Without the filter the resolver reaches into a pool that is 86% point
    substitutions -- and substitutions are chosen precisely because they
    change the kinetics, so they populate the tail a minimum selects from.
    """
    withheld = _resolve_mouse_ache(ache_kcat_provider)
    allowed = _resolve_mouse_ache(ache_kcat_provider, allow_variants=True)

    assert withheld.found is True
    assert allowed.found is True

    # ORIGINALLY this asserted `withheld.value != allowed.value` -- that
    # excluding variants changes the answer. That premise died when ADR 0047
    # added the evidence frontier, which ranks a `wild_type` commentary above
    # a `variant` one on its own. Both paths now converge on the same
    # wild-type row, and the value stops distinguishing them.
    #
    # The assertion was rewritten rather than deleted, because the thing it
    # was protecting is still real: the exact-tier filter must reach the
    # selection. Two mechanisms agreeing is not the same as one of them being
    # unnecessary -- the frontier only prefers wild-type when nothing beats
    # that row on another axis, and the filter is what guarantees a variant
    # can never be returned by default.
    #
    # So it now asserts the PROPERTY rather than a difference in outcome.
    assert withheld.variant is not None
    assert withheld.variant.status != "variant", (
        "the default path returned a value measured on a protein variant"
    )
    assert any("protein variant" in line for line in withheld.search_log), (
        "the exact-tier filter left no trace; it is not reaching the selection"
    )
    # And with the opt-in, variants are genuinely back in the pool.
    assert not any(
        "protein variant" in line for line in allowed.search_log
    ), "allow_variants=True still excluded variant rows"


def test_exact_tier_says_what_it_excluded(ache_kcat_provider):
    """A silent filter is indistinguishable from no filter.

    The count has to reach the log, or a reader cannot tell whether the
    value they got was chosen from three rows or thirty-seven.
    """
    result = _resolve_mouse_ache(ache_kcat_provider)
    excluded = [line for line in result.search_log if "protein variant" in line]
    assert excluded, "nothing in the log records the exclusion"
    assert "exact-match" in excluded[0]


def test_the_opt_in_actually_re_admits_variants(ache_kcat_provider):
    """The opt-in must be a real switch, not a message about one.

    Same argument as allow_cross_species in ADR 0024: a flag that changes
    nothing is worse than no flag, because the user believes they made a
    choice.
    """
    result = _resolve_mouse_ache(ache_kcat_provider, allow_variants=True)
    assert result.found is True
    assert not any("protein variant" in line for line in result.search_log)


def test_variant_filter_does_not_fire_when_nothing_is_a_variant(ldh_provider):
    """The LDH human rows carry no variant markers.

    Without this, a filter that excluded EVERYTHING would pass the tests
    above -- they only assert that the two paths differ.
    """
    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "lactate",
        html_provider=ldh_provider,
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )
    assert result.found is True
    assert result.source == "brenda_exact"
    assert not any("protein variant" in line for line in result.search_log)
