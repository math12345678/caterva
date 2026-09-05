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
  The bundled citation FOR THE RATE (stdpopsim tags each reference with
  the reason it is bundled; this one's reason is 'mutation rate'):
    - Tian X, Browning BL, Browning SR (2019). Estimating the Genome-wide
      Mutation Rate with Three-Way Identity by Descent.
      Am J Hum Genet 105(5):883-893. https://doi.org/10.1016/j.ajhg.2019.09.012

  The HomSap genome also bundles IHGSC (2001) for the GENOME ASSEMBLY and
  the HapMap Consortium (2007) for the RECOMBINATION rate. Neither reports
  a mutation rate, and neither may be surfaced as this value's locator --
  an earlier version of this file named IHGSC 2001 and Jónsson et al.
  (2017) as the rate's citations. Verified against stdpopsim 0.3.0 on
  2026-09-05: IHGSC 2001 is bundled for the assembly, and Jónsson et al.
  is not bundled in the HomSap catalog at all.

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

    # Build a citation from stdpopsim's bundled references.
    #
    # THE STRUCTURED DOI MUST BE THE MUTATION-RATE PAPER, NOT THE FIRST ONE.
    #
    # stdpopsim tags every bundled citation with the REASON it is bundled.
    # For HomSap (stdpopsim 0.3.0, verified by running it) the genome
    # carries three, in this order:
    #
    #   IHGSC 2001                     10.1038/35057062    'genome assembly'
    #   Tian, Browning & Browning 2019 10.1016/j.ajhg...   'mutation rate'
    #   HapMap Consortium 2007         10.1038/nature06258 'recombination rate'
    #
    # This loop used to keep the FIRST DOI it saw, which is the 2001 human
    # genome assembly paper. That DOI became the structured locator for
    # `mutation_rate` -- the link a reader clicks to check 1.29e-8 -- and
    # that paper reports no such rate. A real reference for a number it
    # does not report is the precise defect ADR 0162 is named after; this
    # is the same defect in a second module, and it is worse here because
    # the correct paper WAS bundled all along, one entry further down.
    #
    # So the DOI is chosen by stdpopsim's own `reasons`, never by position.
    # If no bundled citation claims the mutation rate, none is surfaced:
    # an absent locator degrades honestly (locatableCitation downstream
    # then declines to mark the value resolved), whereas a confidently
    # wrong one does not.
    citations = []
    doi = None
    for c in species.genome.citations[:3]:
        if hasattr(c, "doi") and c.doi:
            clean_doi = _normalise_doi(c.doi)
            if clean_doi:
                reasons = " ".join(str(r).lower() for r in getattr(c, "reasons", []))
                if doi is None and "mutation rate" in reasons:
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
