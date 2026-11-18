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
  caterva/core/validation.py::beta_gamma_from_r0, mirroring how
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
    #: ADR 0169: True when R0 and the serial interval come from two
    #: different systematic reviews rather than one paper. A composite
    #: entry must surface as citationStatus "flagged" downstream -- never
    #: "verified" -- with composite_note naming exactly what was combined.
    cross_study_composite: bool = False
    composite_note: Optional[str] = None
    #: The serial-interval half's own citation, when it differs from the
    #: R0 half's. Both sources must reach provenance; dropping either
    #: would present a two-paper number as if one paper supported it.
    secondary_citation: Optional[str] = None
    secondary_doi: Optional[str] = None
    secondary_pmid: Optional[str] = None
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
    # ---- ADR 0169: cross-study composites -------------------------------
    #
    # Both influenza entries pair Biggerstaff et al. (2014)'s meta-analytic
    # R0 with Vink et al. (2014)'s serial intervals. ADR 0017 rejected an
    # influenza entry in August because the period source found then (Cori
    # et al. 2012) measured an SEIR-style latent/infectious decomposition --
    # a different quantity. Vink is the matched quantity: a MEAN SERIAL
    # INTERVAL, the same measure the COVID-19 entry above uses for 1/gamma,
    # re-estimated from raw household-outbreak data with one common method.
    # Carrat et al. 2008 (mean shedding 4.80 days) was considered and
    # rejected: shedding is a virological duration, roughly twice the
    # serial interval for influenza, and using it would have silently
    # redefined what gamma means mid-registry.
    #
    # All four abstracts re-fetched from PubMed on 2026-09-04 and the
    # numbers transcribed from them, not from memory. See ADR 0169.
    "influenza-a-h1n1pdm09": {
        "disease": "Influenza A(H1N1)pdm09 (2009 pandemic)",
        "r0": 1.46,
        "r0_ci": "IQR 1.30-1.70 (median of 78 estimates)",
        "infectious_period_days": 2.8,
        "infectious_period_ci": None,
        "infectious_period_measure": (
            "mean serial interval for A(H1N1)pdm09 (Vink et al. 2014), the "
            "same generation-time proxy for 1/gamma the COVID-19 entry uses."
        ),
        "cross_study_composite": True,
        "composite_note": (
            "R0 and serial interval come from two different systematic "
            "reviews (cross-study composite, ADR 0169). Both halves "
            "describe the same strain, A(H1N1)pdm09, so the combination is "
            "strain-matched; it is still weaker than a single-source pair "
            "and is flagged, not verified."
        ),
        "source": "PubMed",
        "citation": (
            "Biggerstaff M, Cauchemez S, Reed C, Gambhir M, Finelli L. "
            "Estimates of the reproduction number for seasonal, pandemic, "
            "and zoonotic influenza: a systematic review of the literature. "
            "BMC Infect Dis. 2014;14:480."
        ),
        "doi": "10.1186/1471-2334-14-480",
        "pmid": "25186370",
        "secondary_citation": (
            "Vink MA, Bootsma MCJ, Wallinga J. Serial intervals of "
            "respiratory infectious diseases: a systematic review and "
            "analysis. Am J Epidemiol. 2014;180(9):865-875."
        ),
        "secondary_doi": "10.1093/aje/kwu209",
        "secondary_pmid": "25294601",
    },
    "influenza-seasonal": {
        "disease": "Seasonal influenza",
        "r0": 1.28,
        "r0_ci": "IQR 1.19-1.37 (median of 47 estimates)",
        "infectious_period_days": 2.2,
        "infectious_period_ci": None,
        "infectious_period_measure": (
            "mean serial interval for influenza A(H3N2) (Vink et al. 2014), "
            "used as the generation-time proxy for 1/gamma."
        ),
        "cross_study_composite": True,
        "composite_note": (
            "Composite on TWO axes, both stated (ADR 0169): cross-study "
            "(R0 from Biggerstaff et al. 2014, serial interval from Vink "
            "et al. 2014) and cross-strain (Biggerstaff's 'seasonal' pools "
            "H3N2/H1N1/B, while Vink's 2.2-day serial interval is "
            "H3N2-specific). Flagged, not verified. For a strain-matched "
            "pair, ask about the 2009 H1N1 pandemic instead."
        ),
        "source": "PubMed",
        "citation": (
            "Biggerstaff M, Cauchemez S, Reed C, Gambhir M, Finelli L. "
            "Estimates of the reproduction number for seasonal, pandemic, "
            "and zoonotic influenza: a systematic review of the literature. "
            "BMC Infect Dis. 2014;14:480."
        ),
        "doi": "10.1186/1471-2334-14-480",
        "pmid": "25186370",
        "secondary_citation": (
            "Vink MA, Bootsma MCJ, Wallinga J. Serial intervals of "
            "respiratory infectious diseases: a systematic review and "
            "analysis. Am J Epidemiol. 2014;180(9):865-875."
        ),
        "secondary_doi": "10.1093/aje/kwu209",
        "secondary_pmid": "25294601",
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
    # Bare "flu"/"influenza" means the seasonal disease -- that is the
    # question a teaching lab asks by default. The pandemic strain must be
    # named to be meant.
    "flu": "influenza-seasonal",
    "influenza": "influenza-seasonal",
    "seasonal flu": "influenza-seasonal",
    "seasonal influenza": "influenza-seasonal",
    "h1n1": "influenza-a-h1n1pdm09",
    "swine flu": "influenza-a-h1n1pdm09",
    "influenza a(h1n1)pdm09": "influenza-a-h1n1pdm09",
    "influenza a (h1n1)": "influenza-a-h1n1pdm09",
    "2009 pandemic influenza": "influenza-a-h1n1pdm09",
    "pandemic influenza": "influenza-a-h1n1pdm09",
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
        cross_study_composite=entry.get("cross_study_composite", False),
        composite_note=entry.get("composite_note"),
        secondary_citation=entry.get("secondary_citation"),
        secondary_doi=entry.get("secondary_doi"),
        secondary_pmid=entry.get("secondary_pmid"),
        search_log=log,
    )
