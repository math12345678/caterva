"""Fixture-backed NCBI lineages, for testing the relatedness policy offline.

Shared by test_fallback_logic.py and test_golden_set.py so the two cannot
drift into disagreeing about what "closely related" means -- which would be
the worst kind of drift here, since the golden set is supposed to be the
record of what the whole chain does end to end.

An organism with no fixture resolves to None, which taxonomy.py treats as
"unknown" and therefore as a refusal. That is the correct default for a
test double: an unlisted organism must not accidentally be treated as a
relative.
"""
from __future__ import annotations

import pathlib

from taxonomy import Lineage, parse_taxon_lineage

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "taxonomy"

#: Organism scientific name -> fixture slug. Names are exactly as BRENDA
#: writes them, because that is what reaches the resolver.
_SLUGS = {
    "Homo sapiens": "homo_sapiens",
    "Sus scrofa": "sus_scrofa",
    "Mus musculus": "mus_musculus",
    "Oryctolagus cuniculus": "oryctolagus_cuniculus",
    "Plasmodium falciparum": "plasmodium_falciparum",
    "Cryptosporidium parvum": "cryptosporidium_parvum",
    "Danio rerio": "danio_rerio",
    "Thermus thermophilus": "thermus_thermophilus",
}


def fixture_lineage_provider(organism: str) -> Lineage | None:
    """A LineageProvider backed by captured NCBI XML. No network."""
    slug = _SLUGS.get(organism)
    if slug is None:
        return None
    matches = sorted(FIXTURE_DIR.glob(f"taxonomy_{slug}_*.xml"))
    if not matches:
        return None
    return parse_taxon_lineage(matches[0].read_text(encoding="utf-8"))


def unresolvable_lineage_provider(organism: str) -> Lineage | None:
    """Every lookup fails -- simulates NCBI being unreachable.

    Exists so a test can assert that a failed relatedness lookup refuses
    rather than permits. That distinction is the entire reason
    taxonomy.Relatedness has three states instead of a boolean.
    """
    return None
