"""
Stage 5 Part 2: the golden set.

Rule 1 for provenance (Stage 4 close, question 3): the numeric side has
closed forms; the provenance side needs an equivalent — a golden set of
hand-verified enzyme/substrate/Km/citation tuples asserted end to end
(plus the Ki pairs added for the competitive-inhibition domain, which
carry their own quantity="ki" resolution and citation).

These tuples were hand-verified against primary literature through the
BRENDA fixture HTML (the fixture files were previously captured from live
BRENDA and verified row-by-row; see the *_realrows_debug.py scripts).

Every tuple is asserted in full: value, unit, organism, source tier,
citation reference id, citation URL, and the cross-species flag. If the
resolution chain ever returns a plausible-but-wrong value (wrong organism
row, wrong substrate, flagged row surfacing), this table fails.

The mutation proof (question 4) is documented in STAGE_05_PART_02.md:
mutating the row selection in fallback_logic.py makes this suite fail, and
reverting the mutation makes it pass again.
"""

import os

import pytest

from fallback_logic import KineticResult, resolve_kinetic_value

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Real UniProt accessions / NCBI taxon IDs, previously verified (mirrors
# test_fallback_logic.py).
FAKE_UNIPROT_BY_EC = {
    "1.1.1.27": "P00338",
    "3.1.1.7": "P22303",
}
FAKE_TAXON_IDS = {
    "Homo sapiens": "9606",
    "Mus musculus": "10090",
    "Sus scrofa": "9823",
}


def fake_uniprot_provider(ec_number: str, taxon_id: str):
    return FAKE_UNIPROT_BY_EC.get(ec_number)


def fake_taxon_id_provider(organism_name: str):
    return FAKE_TAXON_IDS.get(organism_name)


def make_html_provider(fixture_name: str):
    def provider(ec_number: str) -> str:
        with open(os.path.join(FIXTURES_DIR, fixture_name), encoding="utf-8") as f:
            return f.read()

    return provider


# ---------------------------------------------------------------------------
# The golden set. Fields: ec, substrate, organism, km, unit, source tier,
# citation ref, cross_species_flag. Hand-verified against the BRENDA
# fixtures (which are captures of real BRENDA rows).
# ---------------------------------------------------------------------------

GOLDEN = [
    {
        "id": "G1: LDH/lactate/Homo sapiens",
        "ec": "1.1.1.27",
        "substrate": "lactate",
        "organism": "Homo sapiens",
        "fixture": "brenda_ldh_fixture.html",
        "expected": {
            "km": 10.73,
            "unit": "mM",
            "organism": "Homo sapiens",
            "source": "brenda_exact",
            "ref": "740253",
            "cross_species_flag": False,
        },
    },
    {
        "id": "G2: AChE/acetyl thiocholine/Homo sapiens",
        "ec": "3.1.1.7",
        "substrate": "acetyl thiocholine",
        "organism": "Homo sapiens",
        "fixture": "brenda_ache_fixture.html",
        "expected": {
            "km": 0.09,
            "unit": "mM",
            "organism": "Homo sapiens",
            "source": "brenda_exact",
            "ref": "649716",
            "cross_species_flag": False,
        },
    },
    {
        "id": "G3: LDH/lactate/Mus musculus (cross-species fallback)",
        "ec": "1.1.1.27",
        "substrate": "lactate",
        "organism": "Mus musculus",
        "fixture": "brenda_ldh_fixture.html",
        "expected": {
            "km": 0.0026,
            "unit": "mM",
            "organism": "Sus scrofa",
            "source": "brenda_cross_species",
            "ref": "740001",
            "cross_species_flag": True,
        },
    },
    {
        "id": "G4: LDH/gossypol/Homo sapiens (Ki)",
        "ec": "1.1.1.27",
        "substrate": "gossypol",
        "organism": "Homo sapiens",
        "fixture": "brenda_ldh_ki_fixture.html",
        "quantity": "ki",
        "expected": {
            "km": 0.0014,
            "unit": "mM",
            "organism": "Homo sapiens",
            "source": "brenda_exact",
            "ref": "711801",
            "cross_species_flag": False,
        },
    },
    {
        "id": "G5: LDH/gossypol/Mus musculus (Ki cross-species fallback)",
        "ec": "1.1.1.27",
        "substrate": "gossypol",
        "organism": "Mus musculus",
        "fixture": "brenda_ldh_ki_fixture.html",
        "quantity": "ki",
        "expected": {
            "km": 0.0007,
            "unit": "mM",
            "organism": "Plasmodium falciparum",
            "source": "brenda_cross_species",
            "ref": "654758",
            "cross_species_flag": True,
        },
    },
]


def _resolve(entry) -> KineticResult:
    return resolve_kinetic_value(
        entry["ec"],
        entry["organism"],
        entry["substrate"],
        html_provider=make_html_provider(entry["fixture"]),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity=entry.get("quantity", "km"),
    )


@pytest.mark.parametrize("entry", GOLDEN, ids=lambda e: e["id"])
def test_golden_tuple_end_to_end(entry):
    expected = entry["expected"]
    result = _resolve(entry)

    assert result.found is True, f"{entry['id']}: not found"
    assert result.value == pytest.approx(expected["km"]), (
        f"{entry['id']}: value {result.value} != golden {expected['km']} — "
        "a plausible-but-wrong row may have been selected"
    )
    assert result.unit == expected["unit"]
    assert result.organism == expected["organism"]
    assert result.source == expected["source"]
    assert result.cross_species_flag is expected["cross_species_flag"]

    assert result.citation is not None, f"{entry['id']}: no citation"
    assert result.citation.source == "BRENDA"
    assert result.citation.reference_id == expected["ref"]
    assert result.citation.url is not None, f"{entry['id']}: no citation URL"


@pytest.mark.parametrize("entry", GOLDEN, ids=lambda e: e["id"])
def test_golden_citation_is_locatable(entry):
    result = _resolve(entry)
    assert result.citation is not None
    ref = result.citation.reference_id
    url = result.citation.url
    assert (ref is not None and ref != "n/a") or (url is not None), (
        f"{entry['id']}: citation has no locator"
    )
