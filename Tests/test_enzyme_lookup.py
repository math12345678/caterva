"""
pytest suite for enzyme_lookup.py

Runs entirely offline against saved fixture text/JSON - no network access.
The KEGG fixtures follow KEGG's documented flat-file format (field name
at column 0, continuation lines indented, entries separated by ';',
compound IDs in "[CPD:Cxxxxx]" tags). Both fixtures' SUBSTRATE fields (the only field
parse_kegg_substrates() reads) were re-verified live 2026-07 -
byte-for-byte identical to a fresh KEGG fetch for both EC numbers (see
kegg_fixtures_verify_debug.py / kegg_hexokinase_verify_debug.py). This
docstring previously claimed live output was unavailable to confirm the
format assumption; that's now been done for both fixtures and corrected
here. Other fields in both files (GENES, DBLINKS, PATHWAY, REFERENCE,
etc.) are intentionally abbreviated/stale relative to current live KEGG
- see the header comment in each fixture file for why that's fine (those
fields are never read by any code in this project).
"""

import os


from enzyme_lookup import (
    expand_substrates_with_synonyms,
    parse_ec_number_search,
    parse_kegg_substrates,
    parse_pubchem_synonyms,
    parse_taxon_id,
    parse_uniprot_accession,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# KEGG substrate parsing
# ---------------------------------------------------------------------------

def test_parses_ldh_substrates_from_kegg_text():
    text = load_fixture("kegg_ldh_fixture.txt")
    substrates = parse_kegg_substrates(text)
    assert "(S)-lactate" in substrates
    assert "NAD+" in substrates


def test_parses_hexokinase_substrates_from_kegg_text():
    text = load_fixture("kegg_hexokinase_fixture.txt")
    substrates = parse_kegg_substrates(text)
    assert "ATP" in substrates
    assert "D-hexose" in substrates


def test_kegg_compound_id_tags_are_stripped():
    text = load_fixture("kegg_ldh_fixture.txt")
    substrates = parse_kegg_substrates(text)
    assert all("[CPD:" not in s for s in substrates)


def test_kegg_parsing_stops_at_next_field():
    """PRODUCT and everything after it must never leak into the
    substrate list - this is the whole point of the field-boundary
    detection logic."""
    text = load_fixture("kegg_ldh_fixture.txt")
    substrates = parse_kegg_substrates(text)
    assert "pyruvate" not in substrates
    assert "NADH" not in substrates


def test_kegg_parsing_handles_missing_substrate_field():
    text = "ENTRY       EC 9.9.9.9\nNAME        made-up enzyme\n///\n"
    substrates = parse_kegg_substrates(text)
    assert substrates == []


def test_kegg_parsing_handles_empty_text():
    assert parse_kegg_substrates("") == []


# ---------------------------------------------------------------------------
# UniProt accession parsing
# ---------------------------------------------------------------------------

def test_parses_uniprot_accession_from_valid_response():
    data = {"results": [{"primaryAccession": "P00338", "entryType": "UniProtKB reviewed (Swiss-Prot)"}]}
    assert parse_uniprot_accession(data) == "P00338"


def test_parses_uniprot_accession_returns_none_for_empty_results():
    data = {"results": []}
    assert parse_uniprot_accession(data) is None


def test_parses_uniprot_accession_handles_missing_results_key():
    assert parse_uniprot_accession({}) is None


def test_parses_uniprot_accession_takes_first_result_only():
    data = {
        "results": [
            {"primaryAccession": "P00338"},
            {"primaryAccession": "Q99999"},
        ]
    }
    assert parse_uniprot_accession(data) == "P00338"


# ---------------------------------------------------------------------------
# UniProt name -> EC number parsing
#
# NOTE ON THIS FIXTURE'S PROVENANCE: unlike the KEGG fixtures above (whose
# docstring confirms they were re-verified byte-for-byte against a live
# fetch), this JSON shape was NOT captured from a live UniProt response --
# the sandbox this was written in has no network access to
# rest.uniprot.org. It is built from UniProt's documented REST JSON schema
# (proteinDescription.recommendedName.ecNumbers[].value), which is stable
# and used elsewhere in production UniProt tooling, but "documented" is not
# "verified against a real response" per this project's own rule (Rule 1).
# Run `python -c "import enzyme_lookup; print(enzyme_lookup.fetch_ec_number_by_name('alpha-amylase'))"`
# with real network access and confirm it returns "3.2.1.1" before trusting
# this fixture blindly.
# ---------------------------------------------------------------------------

UNIPROT_EC_SEARCH_FIXTURE = {
    "results": [
        {
            "primaryAccession": "P04746",
            "proteinDescription": {
                "recommendedName": {
                    "fullName": {"value": "Alpha-amylase"},
                    "ecNumbers": [{"value": "3.2.1.1"}],
                }
            },
        }
    ]
}


def test_parses_ec_number_from_recommended_name():
    assert parse_ec_number_search(UNIPROT_EC_SEARCH_FIXTURE) == "3.2.1.1"


def test_parses_ec_number_from_alternative_name_when_no_recommended_ec():
    data = {
        "results": [
            {
                "proteinDescription": {
                    "recommendedName": {"fullName": {"value": "Some enzyme"}},
                    "alternativeNames": [
                        {"ecNumbers": [{"value": "1.1.1.1"}]},
                    ],
                }
            }
        ]
    }
    assert parse_ec_number_search(data) == "1.1.1.1"


def test_parses_ec_number_returns_none_for_empty_results():
    assert parse_ec_number_search({"results": []}) is None


def test_parses_ec_number_returns_none_when_no_ec_present_at_all():
    data = {
        "results": [
            {"proteinDescription": {"recommendedName": {"fullName": {"value": "x"}}}}
        ]
    }
    assert parse_ec_number_search(data) is None


def test_parses_ec_number_handles_missing_results_key():
    assert parse_ec_number_search({}) is None


# ---------------------------------------------------------------------------
# PubChem synonym parsing
# ---------------------------------------------------------------------------

def test_parses_pubchem_synonyms_from_valid_response():
    data = {
        "InformationList": {
            "Information": [
                {
                    "CID": 5988,
                    "Synonym": ["D-glucose", "Dextrose", "Grape sugar", "D-Glucopyranose"],
                }
            ]
        }
    }
    synonyms = parse_pubchem_synonyms(data)
    assert "Dextrose" in synonyms
    assert "Grape sugar" in synonyms


def test_parses_pubchem_synonyms_handles_no_compound_found():
    """PubChem has no CID for generic substrate classes like 'primary
    alcohol' - must return an empty list, not error."""
    data = {"InformationList": {"Information": []}}
    assert parse_pubchem_synonyms(data) == []


def test_parses_pubchem_synonyms_handles_missing_key():
    assert parse_pubchem_synonyms({}) == []


def test_expand_substrates_with_synonyms_preserves_originals(monkeypatch):
    import enzyme_lookup

    def fake_fetch(name, timeout=15):
        if name == "D-glucose":
            return ["Dextrose", "Grape sugar"]
        return []

    monkeypatch.setattr(enzyme_lookup, "fetch_pubchem_synonyms", fake_fetch)

    expanded = expand_substrates_with_synonyms(["D-glucose", "ATP"])
    assert "D-glucose" in expanded
    assert "ATP" in expanded
    assert "Dextrose" in expanded
    assert "Grape sugar" in expanded


def test_expand_substrates_with_synonyms_deduplicates(monkeypatch):
    import enzyme_lookup

    def fake_fetch(name, timeout=15):
        return ["D-glucose"]  # same as the original, different case

    monkeypatch.setattr(enzyme_lookup, "fetch_pubchem_synonyms", fake_fetch)

    expanded = expand_substrates_with_synonyms(["D-glucose"])
    assert expanded.count("D-glucose") == 1


def test_expand_substrates_with_synonyms_respects_cap(monkeypatch):
    import enzyme_lookup

    def fake_fetch(name, timeout=15):
        return [f"synonym-{i}" for i in range(50)]

    monkeypatch.setattr(enzyme_lookup, "fetch_pubchem_synonyms", fake_fetch)

    expanded = expand_substrates_with_synonyms(["compound"], max_synonyms_per_substrate=3)
    # 1 original + at most 3 synonyms
    assert len(expanded) <= 4


def test_expand_substrates_handles_compound_with_no_pubchem_entry(monkeypatch):
    """Generic classes like 'primary alcohol' have no PubChem entry -
    expansion must not crash, and the original name is still present."""
    import enzyme_lookup

    def fake_fetch(name, timeout=15):
        return []

    monkeypatch.setattr(enzyme_lookup, "fetch_pubchem_synonyms", fake_fetch)

    expanded = expand_substrates_with_synonyms(["primary alcohol"])
    assert expanded == ["primary alcohol"]


# ---------------------------------------------------------------------------
# NCBI Taxonomy: organism name -> taxon ID parsing
#
# Replaces an earlier hardcoded dict of ~7 organisms in fallback_logic.py
# (ORGANISM_TAXON_IDS), which silently returned no taxon ID for any
# organism outside that list. This works for any organism name NCBI
# recognizes.
# ---------------------------------------------------------------------------

def test_parses_taxon_id_from_valid_response():
    # Real shape of an NCBI esearch response for "Homo sapiens[Scientific Name]"
    data = {"esearchresult": {"idlist": ["9606"], "count": "1"}}
    assert parse_taxon_id(data) == "9606"


def test_parses_taxon_id_returns_none_for_empty_idlist():
    data = {"esearchresult": {"idlist": [], "count": "0"}}
    assert parse_taxon_id(data) is None


def test_parses_taxon_id_handles_missing_esearchresult_key():
    assert parse_taxon_id({}) is None


def test_parses_taxon_id_takes_first_id_only():
    data = {"esearchresult": {"idlist": ["9823", "9825"], "count": "2"}}
    assert parse_taxon_id(data) == "9823"
