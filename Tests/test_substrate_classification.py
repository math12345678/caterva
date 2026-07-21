"""
pytest suite for classify_substrate() in brenda_client.py.

Added after live data showed trypsin's lowest-Km row was an engineered
EGFP-T1 FRET reporter construct, not a classic small-molecule substrate.
Nothing gets excluded from results based on this classification - it's
metadata so downstream product code can choose to prioritize classic
substrates when picking a "representative" Km, without losing the
reporter-substrate data entirely.
"""

import pytest

from brenda_client import classify_substrate, parse_brenda_km_html
import os

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize(
    "substrate_name",
    [
        "enhanced green fluorescent protein-T1",
        "enhanced green fluorescent protein-T1nb",
        "EGFP-based reporter",
        "GFP fusion substrate",
        "firefly luciferase",
        "FRET peptide substrate",
    ],
)
def test_classifies_engineered_reporter_substrates(substrate_name):
    assert classify_substrate(substrate_name) == "engineered_reporter"


@pytest.mark.parametrize(
    "substrate_name",
    [
        "lactate",
        "acetyl thiocholine",
        "D-glucose",
        "benzoyl-DL-Arg-p-nitroanilide",
        "N-benzoyl-L-tyrosine ethyl ester",
        "pyruvate",
    ],
)
def test_classifies_classic_substrates(substrate_name):
    assert classify_substrate(substrate_name) == "classic"


def test_classification_is_case_insensitive():
    assert classify_substrate("Enhanced GREEN Fluorescent Protein-T1") == "engineered_reporter"
    assert classify_substrate("gfp") == "engineered_reporter"


LDH_SUBSTRATES = ["lactate", "L-lactate", "pyruvate", "NADH", "NAD+", "NAD"]
TRYPSIN_SUBSTRATES = [
    "benzoyl-DL-Arg-7-amido-4-methylcoumarin",
    "benzoyl-DL-Arg-p-nitroanilide",
    "Glu-Gly-Arg-4-nitroanilide",
    "tert-butoxycarbonyl-L-Gln-L-Ala-L-Arg-7-amido-4-methylcoumarin",
    "enhanced green fluorescent protein-T1",
]


def test_default_entry_substrate_type_is_classic():
    """BRENDAKmEntry's default (when substrate_type isn't explicitly set)
    should be 'classic' so any code path that forgets to classify doesn't
    silently mislabel a reporter substrate as safe."""
    entries = parse_brenda_km_html(
        load_fixture("brenda_ldh_fixture.html"), "1.1.1.27", LDH_SUBSTRATES
    )
    assert all(e.substrate_type == "classic" for e in entries)


def test_parsed_entries_are_classified_automatically():
    """End-to-end: parse_brenda_km_html must set substrate_type on every
    entry without the caller doing anything extra."""
    entries = parse_brenda_km_html(
        load_fixture("brenda_trypsin_fixture.html"), "3.4.21.4", TRYPSIN_SUBSTRATES
    )
    types_seen = {e.substrate_type for e in entries}
    assert "classic" in types_seen
    assert "engineered_reporter" in types_seen
