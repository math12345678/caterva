"""
epidemiology_resolver.py

Literature-backed disease-parameter resolver for the SIR/SEIR simulation
domains: given a disease name, returns its basic reproduction number (R0)
and a characteristic infectious period (mean serial interval), each with a
real citation -- the same relationship to epidemiology that brenda_client.py
has to enzyme kinetics, and popgen_resolver.py has to population genetics.

Design, deliberately narrow (see docs/adr/0017-epidemiology-parameter-
resolution.md):

- Unlike BRENDA (a queryable database covering any EC number) or stdpopsim
  (a bundled catalog covering dozens of species), there is no equivalent
  keyless, programmatically queryable database of matched (R0, infectious
  period) pairs for named diseases. Each entry below is therefore a
  hand-verified golden tuple, sourced from a single peer-reviewed paper (or
  a matched pair of papers using compatible methodology) -- the same rigor
  BRENDA's fixture-derived golden tuples get, just curated by hand instead
  of parsed from a live page. Every entry lists its PMID and DOI.
- R0 and infectious period MUST come from the same study or explicitly
  compatible methodology. Pairing a systematic review's R0 with an
  unrelated paper's infectious-period estimate risks silently combining
  incompatible modeling assumptions into a beta/gamma that neither source
  actually supports -- see the ADR for the COVID-19 case this was checked
  against directly.
- A disease not in this registry returns found=False. Nothing is
  extrapolated, interpolated, or guessed.
- This module resolves literature values. It does not decide whether they
  are simulable -- that bridge (beta = R0 * gamma) lives in
  Tellurium/core/validation.py::beta_gamma_from_r0, mirroring how
  fallback_logic.py resolves a kcat and vmax_from_kcat (a different module
  entirely) turns it into something the engine can run.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class EpidemiologyResult(BaseModel):
    found: bool
    disease: Optional[str] = None
    r0: Optional[float] = None
    r0_ci: Optional[str] = None
    infectious_period_days: Optional[float] = None
    infectious_period_ci: Optional[str] = None
    #: What the infectious_period_days figure actually measures. Kept
    #: explicit rather than assumed, since "infectious period" is used
    #: loosely across the epidemiology literature -- see the ADR.
    infectious_period_measure: Optional[str] = None
    source: Optional[str] = None
    citation: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    search_log: List[str] = []


# Hand-verified golden tuples. Each entry's R0 and infectious_period_days
# come from the SAME paper (or are explicitly noted otherwise), so beta/gamma
# derived from them reflects one internally-consistent set of modeling
# assumptions, not two studies' incompatible ones stitched together.
_DISEASE_REGISTRY: dict[str, dict] = {
    "covid-19": {
        "disease": "COVID-19 (SARS-CoV-2, ancestral strain)",
        "r0": 3.14,
        "r0_ci": "95% CI 2.69-3.59",
        "infectious_period_days": 5.45,
        "infectious_period_ci": "95% CI 4.23-6.66",
        "infectious_period_measure": (
            "mean serial interval (time between symptom onset in successive "
            "cases), used as the two-compartment SIR model's generation-time "
            "proxy for 1/gamma -- not a virological shedding-duration "
            "measurement. See docs/adr/0017 for why this is the standard "
            "simplification for a model with no separate exposed compartment."
        ),
        "source": "PubMed",
        "citation": (
            "Hussein M, Toraih E, Elshazli R, Fawzy M, Houghton A, Tatum D, "
            "Killackey M, Kandil E, Duchesne J. Meta-analysis on Serial "
            "Intervals and Reproductive Rates for SARS-CoV-2. Ann Surg. "
            "2021;273(3):416-423."
        ),
        "doi": "10.1097/SLA.0000000000004400",
        "pmid": "33214421",
    },
}

# Common alternate spellings/names a query might use, mapped to the
# canonical registry key. Deliberately small -- a name-normalisation table,
# not an attempt at general disease-name NLP.
_ALIASES: dict[str, str] = {
    "covid": "covid-19",
    "covid19": "covid-19",
    "covid 19": "covid-19",
    "sars-cov-2": "covid-19",
    "sars cov 2": "covid-19",
    "coronavirus": "covid-19",
}


def resolve_disease_parameters(disease: str) -> EpidemiologyResult:
    """Look up the (R0, infectious period) golden tuple for a named disease.

    Args:
        disease: Case-insensitive disease name (e.g. "COVID-19", "covid").

    Returns:
        EpidemiologyResult with found=True and both literature values (each
        carrying its own citation) when the disease is in the registry;
        found=False otherwise. Never raises, never fabricates a value for
        an unrecognised disease -- an unresolved lookup degrades to
        user-supplied input, exactly like every other resolver in this
        project.
    """
    log: List[str] = []
    key = disease.strip().lower()
    canonical = _ALIASES.get(key, key)

    entry = _DISEASE_REGISTRY.get(canonical)
    if entry is None:
        return EpidemiologyResult(
            found=False,
            search_log=[
                f"'{disease}' is not in the epidemiology parameter registry "
                f"(available: {sorted(_DISEASE_REGISTRY.keys())})"
            ],
        )

    log.append(
        f"Resolved R0={entry['r0']:g} and infectious_period="
        f"{entry['infectious_period_days']:g} days for '{entry['disease']}' "
        f"from PMID {entry['pmid']}"
    )

    return EpidemiologyResult(
        found=True,
        disease=entry["disease"],
        r0=entry["r0"],
        r0_ci=entry.get("r0_ci"),
        infectious_period_days=entry["infectious_period_days"],
        infectious_period_ci=entry.get("infectious_period_ci"),
        infectious_period_measure=entry.get("infectious_period_measure"),
        source=entry["source"],
        citation=entry["citation"],
        doi=entry["doi"],
        pmid=entry["pmid"],
        search_log=log,
    )
