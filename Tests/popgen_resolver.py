"""
popgen_resolver.py

Literature-backed mutation-rate resolver for population-genetics
simulation domains (wright_fisher, two_locus_wright_fisher).

Uses stdpopsim (PopSim Consortium), a keyless pip-installable Python package
that provides organism-specific mutation rates compiled from published
literature (pedigree studies, mutation-accumulation experiments).
The same relationship to population genetics that BRENDA has to enzymology:
a curated database of peer-reviewed parameter values, accessible
programmatically without an API key.

Human germline mutation rate: ~1.29e-8 per bp per generation
  Source: stdpopsim HomSap genome mean_mutation_rate
  Citations:
    - International Human Genome Sequencing Consortium (2001)
      Nature 409, 860-921. http://dx.doi.org/10.1038/35057062
    - Jónsson et al. (2017) Nature 549, 519-522.
    - and others bundled in the HomSap demographic model.

Design: a single pure function — organism name in, mutation_rate out.
No network access (stdpopsim bundles its data locally). Testable offline
by checking the returned value against the known golden tuple.
"""

from __future__ import annotations

from typing import Optional, List

from pydantic import BaseModel


class PopgenResult(BaseModel):
    found: bool
    value: Optional[float] = None
    unit: str = "per bp per generation"
    organism: Optional[str] = None
    source: str = "stdpopsim"
    citation: Optional[str] = None
    search_log: List[str] = []
    doi: Optional[str] = None


# Map common organism names (as they appear in Terrium queries) to
# stdpopsim species IDs. Deliberately small: this is a name-resolution
# table, not an enzyme registry. A name not in this map falls through
# to fuzzy matching against stdpopsim's species list.
_ORGANISM_TO_STDPSIM: dict[str, str] = {
    "homo sapiens": "HomSap",
    "human": "HomSap",
    "mus musculus": "MusMus",
    "mouse": "MusMus",
    "drosophila melanogaster": "DroMel",
    "fruit fly": "DroMel",
    "escherichia coli": "EscCol",
    "e. coli": "EscCol",
    "arabidopsis thaliana": "AraTha",
    "bos taurus": "BosTau",
    "cow": "BosTau",
    "cattle": "BosTau",
    "canis familiaris": "CanFam",
    "dog": "CanFam",
    "rattus norvegicus": "RatNor",
    "rat": "RatNor",
    "sus scrofa": "SusScr",
    "pig": "SusScr",
}


def _normalise_doi(value: str) -> Optional[str]:
    """Return the bare DOI from a stdpopsim citation record.

    stdpopsim bundles its reference DOIs in inconsistent shapes --
    sometimes a bare ``10.xxxx/...``, sometimes ``http://dx.doi.org/<doi>``,
    sometimes ``https://doi.org/<doi>``. This strips every prefix so the
    locator we emit is a real, resolvable DOI, never a double-prefixed
    ``https://doi.org/http://dx.doi.org/...`` string.
    """
    doi = (value or "").strip()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi if doi.startswith("10.") else None


def resolve_mutation_rate(
    organism: str,
    species_id: Optional[str] = None,
) -> PopgenResult:
    """Look up the germline mutation rate for a named organism via stdpopsim.

    Args:
        organism: Case-insensitive organism name (e.g. "Homo sapiens", "human").
        species_id: Optional stdpopsim species ID override. When omitted,
            the name is matched against the _ORGANISM_TO_STDPSIM map and
            then against stdpopsim's all_species() list.

    Returns:
        PopgenResult with found=True and the per-bp-per-generation mutation
        rate when the species is in stdpopsim's catalog; found=False
        otherwise. Never raises on missing species — an unresolved mutation
        rate degrades to user-supplied, not to a crash.
    """
    log: list[str] = []

    try:
        import stdpopsim
    except ImportError:
        return PopgenResult(
            found=False,
            search_log=["stdpopsim is not installed; mutation rate cannot be resolved"],
        )

    if species_id is not None:
        sid = species_id
    else:
        key = organism.strip().lower()
        sid = _ORGANISM_TO_STDPSIM.get(key)
        if sid is None:
            # Fuzzy match against stdpopsim's species list.
            for sp in stdpopsim.all_species():
                if sp.name.lower() == key or sp.common_name.lower() == key:
                    sid = sp.id
                    log.append(
                        f"Matched '{organism}' → {sp.id} ({sp.name}) via stdpopsim catalog"
                    )
                    break

    if sid is None:
        return PopgenResult(
            found=False,
            search_log=log
            + [
                f"Organism '{organism}' is not in stdpopsim's species catalog "
                f"(available: {[s.id for s in stdpopsim.all_species()]})"
            ],
        )

    try:
        species = stdpopsim.get_species(sid)
    except ValueError:
        return PopgenResult(
            found=False,
            search_log=log + [f"stdpopsim species ID '{sid}' not found"],
        )

    rate = species.genome.mean_mutation_rate

    # Build a citation from stdpopsim's bundled references. Each DOI is
    # normalised to its bare form so the emitted URL is a single resolvable
    # locator; the first real DOI is surfaced separately for structured
    # citation handling downstream (science_agent_runner.py).
    citations = []
    doi = None
    for c in species.genome.citations[:3]:
        if hasattr(c, "doi") and c.doi:
            clean_doi = _normalise_doi(c.doi)
            if clean_doi:
                if doi is None:
                    doi = clean_doi
                citations.append(f"https://doi.org/{clean_doi}")
        elif hasattr(c, "author") and c.author:
            citations.append(c.author)
    citation_str = "; ".join(citations) if citations else "stdpopsim catalog"

    log.append(
        f"Resolved mutation_rate={rate:.4e} per bp/gen for "
        f"{species.name} ({species.common_name}) via stdpopsim"
    )

    return PopgenResult(
        found=True,
        value=rate,
        unit="per bp per generation",
        organism=species.name,
        source="stdpopsim",
        citation=citation_str,
        search_log=log,
        doi=doi,
    )
