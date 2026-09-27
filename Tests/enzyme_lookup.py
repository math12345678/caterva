"""
enzyme_lookup.py

Resolves enzyme metadata dynamically for ANY EC number, no hardcoded
per-enzyme registry. Two sources, both free public APIs, no key required:

- UniProt REST API: EC number + organism -> canonical UniProt accession.
- KEGG REST API: EC number -> the enzyme's real reaction substrate
  name(s), straight from the "SUBSTRATE" field of its KEGG ENZYME entry.

Why the substrate lookup matters (and can't just be dropped): a BRENDA
enzyme page lists Km/Ki/IC50 data for every compound anyone has ever
tested against that enzyme, including inhibitors and random screened
drugs - not just the enzyme's actual physiological substrate. Without a
real substrate name to filter on, results are dominated by that noise
(see the raw, unfiltered AChE dump earlier in this project: hundreds of
inhibitor compounds for one real substrate). KEGG's SUBSTRATE field gives
that real substrate name for any EC number dynamically, replacing what
used to be a hardcoded per-enzyme list.

Same pattern as brenda_client.py throughout: fetch_* functions are the
only ones that touch the network; parse_* functions are pure and are
what the test suite exercises against saved fixture text.
"""

from __future__ import annotations

import os
import re
from urllib.parse import quote

import httpx

from http_retry import retry_get

#: Optional NCBI API key (free, from https://www.ncbi.nlm.nih.gov/account/
#: settings/ -> "API Key Management"). Without one, E-utilities caps
#: requests at 3/sec per IP; with one, 10/sec. Read once at import time
#: like the rest of this module's constants -- every NCBI call below
#: attaches it when present and omits it when absent, so this remains
#: fully functional (just more rate-limited) with no key configured at
#: all, exactly like every other resolver in this project degrading
#: gracefully rather than requiring configuration to run.
NCBI_API_KEY = os.environ.get("NCBI_API_KEY")


def _ncbi_params(**params: str | int) -> dict[str, str | int]:
    """Merge caller params with the NCBI API key, when configured."""
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    return params

UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
KEGG_GET_URL = "https://rest.kegg.jp/get/ec:{ec_number}"
PUBCHEM_SYNONYMS_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/synonyms/JSON"
)
NCBI_TAXONOMY_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

# DEFAULT_TAXON_ID used to live here, set to "9606" (Homo sapiens), and was
# the default argument of three network functions.
#
# It is deleted rather than moved. A default organism is the same defect as
# a default pH: "physiological" means something different for every
# organism (ADR 0012/0013), and so does "the organism". The failure mode was
# worse here, because it fired on a NETWORK FAILURE rather than on a missing
# argument:
#
#     taxon_id = fetch_taxon_id(organism) or DEFAULT_TAXON_ID
#
# fetch_taxon_id returns None when NCBI is unreachable, rate-limited, or does
# not recognise the name. Ask about Thermus aquaticus while NCBI is down and
# the next line fetched the *human* UniProt accession and attached it to a
# thermophile's measurement. The "could not look" outcome was collapsed into
# a confident wrong answer -- in the codebase whose headline behaviour is
# refusing to substitute one organism's value for another's.
#
# Every caller already passed a taxon explicitly, so nothing depended on it.
# It was a latent hazard one omitted argument away from firing.
#
# The correct handling is in fallback_logic._resolve_fallback_uniprot, which
# has always said `if not taxon_id: return None`. Two implementations of one
# step; they disagreed, and the wrong one was the one with a default.


# ---------------------------------------------------------------------------
# NCBI Taxonomy: organism name -> NCBI taxon ID
#
# Replaces an earlier hardcoded dict (ORGANISM_TAXON_IDS in
# fallback_logic.py) covering only ~7 common lab organisms, which
# silently returned no taxon ID - and therefore no UniProt fallback
# accession - for any organism outside that list. This resolves any
# organism name dynamically via NCBI's taxonomy database, the same
# approach used for substrates (KEGG) and accessions (UniProt) elsewhere
# in this module.
# ---------------------------------------------------------------------------

def fetch_taxon_id(organism_name: str, timeout: float = 15) -> str | None:
    """Fetch the NCBI taxon ID for an organism name via NCBI's taxonomy
    E-utilities. Returns None if nothing is found - never guesses.

    Uses the [Scientific Name] field qualifier rather than a bare term
    search - without it, NCBI's esearch matches against ANY indexed
    field (common names, synonyms, etc.), which risks resolving an
    organism string to the wrong taxon for ambiguous names. Restricting
    to Scientific Name is the precise, correct match for BRENDA's
    binomial-nomenclature organism strings (e.g. "Homo sapiens")."""
    params = _ncbi_params(
        db="taxonomy",
        term=f"{organism_name}[Scientific Name]",
        retmode="json",
    )
    r = retry_get(NCBI_TAXONOMY_ESEARCH_URL, params=params, timeout=timeout)
    r.raise_for_status()
    return parse_taxon_id(r.json())


def parse_taxon_id(data: dict) -> str | None:
    """Pure function: NCBI esearch JSON response in, taxon ID string out."""
    ids = data.get("esearchresult", {}).get("idlist", [])
    return ids[0] if ids else None


# ---------------------------------------------------------------------------
# UniProt: EC number -> canonical accession
# ---------------------------------------------------------------------------

def fetch_uniprot_accession(
    ec_number: str, taxon_id: str, timeout: float = 15
) -> str | None:
    """Fetch the canonical (reviewed/Swiss-Prot) UniProt accession for an
    EC number in a given organism. Returns None if nothing is found -
    never guesses or fabricates an accession.

    `taxon_id` is REQUIRED. It carried a default of 9606 until 2026-08-15,
    which made that docstring's last clause false in the way that mattered
    most: it did not fabricate an accession, it fabricated the *organism*,
    then returned a real human accession for whatever species the caller
    was actually asking about."""
    params: dict[str, str | int] = {
        "query": f"ec:{ec_number} AND organism_id:{taxon_id} AND reviewed:true",
        "fields": "accession",
        "format": "json",
        "size": 1,
    }
    r = retry_get(UNIPROT_SEARCH_URL, params=params, timeout=timeout)
    r.raise_for_status()
    return parse_uniprot_accession(r.json())


def parse_uniprot_accession(data: dict) -> str | None:
    """Pure function: UniProt JSON response in, accession string out."""
    results = data.get("results", [])
    if not results:
        return None
    return results[0].get("primaryAccession")


# ---------------------------------------------------------------------------
# KEGG: EC number -> real reaction substrate name(s)
# ---------------------------------------------------------------------------

class KeggLicenceNotConfigured(RuntimeError):
    """KEGG is reachable but Caterva has no licence position for it.

    A distinct type rather than a bare RuntimeError so a caller can tell
    "we chose not to ask KEGG" from "KEGG did not answer". Those are the
    same distinction the resolver keeps everywhere else, and collapsing
    them here would report a deliberate abstention as a network failure.
    """


#: Opt-in switch for the KEGG lookup. OFF unless explicitly set.
#:
#: WHY THIS EXISTS
#: ---------------
#: KEGG's terms (https://www.kegg.jp/kegg/legal.html, 1 October 2024) say
#: KEGG "is not a public database, nor is it a publicly funded database",
#: that non-academic use "requires a commercial license", and that even
#: academic users "who utilize KEGG for providing services are requested to
#: obtain an academic service provider license".
#:
#: Caterva provides a service, and this repository contains an incorporation
#: checklist, a cap table and a fundraising tracker. On either reading a
#: licence from Pathway Solutions (https://www.pathway.jp/) is indicated,
#: and nobody has obtained one.
#:
#: The project's own precedent settles what to do. SABIO-RK was evaluated
#: and DECLINED for having non-commercial-only terms; stdpopsim was moved
#: out of the default install when its GPL-3.0 licence turned out to sit
#: awkwardly with an Apache-2.0 project (ADR 0061). KEGG's terms are
#: comparable to SABIO-RK's and KEGG was integrated anyway -- not after
#: weighing them, but before anyone read them (ADR 0068, NOTICE).
#:
#: So the default is now OFF. Caterva makes no KEGG request unless an
#: operator sets this, and setting it is the operator stating that their own
#: licence position permits it. That is the same shape as CORE, which
#: already refuses to run without CORE_API_KEY -- obtaining the key IS
#: engaging CORE's licensing process.
#:
#: This does NOT assert that using KEGG would be unlawful. It asserts that
#: Caterva does not currently know that it is lawful, and that a tool whose
#: central claim is traceability should not make an unexamined request on a
#: user's behalf.
KEGG_OPT_IN_ENV = "CATERVA_ENABLE_KEGG"


def kegg_enabled() -> bool:
    """Whether the operator has opted in to KEGG lookups."""
    return os.environ.get(KEGG_OPT_IN_ENV, "").strip().lower() in {"1", "true", "yes"}


def fetch_kegg_enzyme_text(ec_number: str, timeout: float = 15) -> str:
    """Fetch the raw KEGG flat-file text for an EC number.

    Raises KeggLicenceNotConfigured unless CATERVA_ENABLE_KEGG is set. See
    KEGG_OPT_IN_ENV above for why the default is off.
    """
    if not kegg_enabled():
        raise KeggLicenceNotConfigured(
            "KEGG lookup is disabled by default. KEGG is not a public database: "
            "non-academic use requires a commercial licence, and academic users "
            "providing a service are asked to obtain an academic service-provider "
            "licence (https://www.kegg.jp/kegg/legal.html). Caterva has not "
            f"obtained one. Set {KEGG_OPT_IN_ENV}=1 to enable this lookup, which "
            "is you stating that your own licence position permits it. "
            "See NOTICE and docs/LICENSING.md."
        )
    url = KEGG_GET_URL.format(ec_number=ec_number)
    r = retry_get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def parse_kegg_substrates(text: str) -> list:
    """Pure function: raw KEGG flat-file text in, list of substrate names
    out. Extracts the SUBSTRATE field, which KEGG formats as:

        SUBSTRATE   (S)-lactate [CPD:C00256];
                    NAD+ [CPD:C00003]
        PRODUCT     pyruvate [CPD:C00022];
                    ...

    KEGG's flat-file convention: a field starts at column 0 with an
    uppercase field name; continuation lines are indented and belong to
    the field above them. So the SUBSTRATE block runs from the line
    starting with "SUBSTRATE" until the next line that does NOT start
    with whitespace.
    """
    lines = text.splitlines()
    block_lines = []
    in_block = False

    for line in lines:
        if line.startswith("SUBSTRATE"):
            in_block = True
            block_lines.append(line[len("SUBSTRATE"):])
            continue
        if in_block:
            if line.startswith((" ", "\t")):
                block_lines.append(line)
                continue
            else:
                break  # next field (or "///") ends the SUBSTRATE block

    joined = " ".join(block_lines)
    raw_entries = [p.strip() for p in joined.split(";") if p.strip()]

    substrates = []
    for entry in raw_entries:
        # strip trailing KEGG compound-ID tags like "[CPD:C00256]"
        cleaned = re.sub(r"\[CPD:[^\]]+\]", "", entry).strip()
        if cleaned:
            substrates.append(cleaned)

    return substrates


# ---------------------------------------------------------------------------
# PubChem: compound name -> alternate names for the SAME molecule
#
# Important limitation, found by testing against live data: this only
# helps when BRENDA's substrate name and KEGG's substrate name refer to
# the identical chemical entity under a different name (e.g. "D-glucose"
# vs "dextrose"). It does NOT help when:
#   - BRENDA reports kinetics on a different-but-related assay surrogate
#     molecule (e.g. acetylcholinesterase measured on "acetylthiocholine",
#     a synthetic sulfur analog, rather than KEGG's "acetylcholine" - these
#     are chemically distinct compounds, not synonyms)
#   - KEGG's substrate is a generic class rather than a specific compound
#     (e.g. alcohol dehydrogenase's "primary alcohol"/"secondary alcohol" -
#     PubChem has no CID for a class, only for specific molecules like
#     ethanol)
# Both of those real cases are handled instead by the unfiltered fallback
# in fetch_and_parse_brenda_km (see brenda_client.py).
# ---------------------------------------------------------------------------

def fetch_pubchem_synonyms(compound_name: str, timeout: float = 15) -> list:
    """Fetch alternate names for a compound from PubChem. Returns an empty
    list (not an error) if PubChem has no entry for this name - that's an
    expected, common outcome for generic substrate classes or names
    PubChem doesn't recognize, not a failure worth surfacing."""
    url = PUBCHEM_SYNONYMS_URL.format(name=quote(compound_name, safe=""))
    try:
        r = retry_get(url, timeout=timeout)
        if r.status_code == 404:
            return []
        r.raise_for_status()
    except httpx.HTTPStatusError:
        return []
    return parse_pubchem_synonyms(r.json())


def parse_pubchem_synonyms(data: dict) -> list:
    """Pure function: PubChem synonyms JSON response in, list of alternate
    names out."""
    info_list = data.get("InformationList", {}).get("Information", [])
    if not info_list:
        return []
    return info_list[0].get("Synonym", [])


def expand_substrates_with_synonyms(
    substrates: list, max_synonyms_per_substrate: int = 8
) -> list:
    """Given a list of substrate names, return the original list plus
    PubChem synonyms for each (deduplicated, original order preserved,
    original names first). Network-dependent - each substrate name costs
    one PubChem request. Failures for individual names are swallowed
    (see fetch_pubchem_synonyms) since a missing PubChem entry for one
    substrate shouldn't block the others."""
    expanded = list(substrates)
    seen = {s.lower() for s in expanded}

    for substrate in substrates:
        synonyms = fetch_pubchem_synonyms(substrate)
        for syn in synonyms[:max_synonyms_per_substrate]:
            if syn.lower() not in seen:
                expanded.append(syn)
                seen.add(syn.lower())

    return expanded


# ---------------------------------------------------------------------------
# UniProt: enzyme NAME -> EC number
#
# This is the live counterpart to the small hardcoded name->EC pattern list
# that used to be the only way (Science-Agent-Pipeline .../lib/enzymes.ts)
# to get from a query like "run kinetics amylase" to a real BRENDA lookup.
# That list covered ~30 enzymes; anything else silently never reached the
# network at all. UniProt's REST search indexes protein names as free text,
# so this resolves an EC number for any enzyme name UniProt has indexed,
# not just a fixed list, with no key required.
# ---------------------------------------------------------------------------

def fetch_ec_number_by_name(
    enzyme_name: str, taxon_id: str | None, timeout: float = 15
) -> str | None:
    """Fetch an EC number for an enzyme by its common/protein name via
    UniProt's REST search. Returns None if nothing is found - never
    guesses or fabricates an EC number.

    taxon_id is REQUIRED and explicit: pass an id to narrow to one organism,
    or pass None to search UniProt without an organism filter. There is no
    default, because a default here silently answers about a species the
    caller never named. `None` is a deliberate statement ("any organism");
    an omitted argument is not.

    Passing None narrows nothing and (the caller's second attempt
    when a species-restricted search finds nothing, mirroring the
    exact-then-cross-species pattern in fallback_logic.py)."""
    query = f'protein_name:"{enzyme_name}" AND reviewed:true'
    if taxon_id:
        query += f" AND organism_id:{taxon_id}"
    params: dict[str, str | int] = {
        "query": query,
        "fields": "accession,ec",
        "format": "json",
        "size": 1,
    }
    r = retry_get(UNIPROT_SEARCH_URL, params=params, timeout=timeout)
    r.raise_for_status()
    return parse_ec_number_search(r.json())


def parse_ec_number_candidates(data: dict) -> list[str]:
    """EVERY distinct EC number in a UniProt search response.

    WHY THE PLURAL MATTERS
    ----------------------
    `parse_ec_number_search` below takes `results[0]` and then
    `ec_numbers[0]`. Two silent picks, on the FIRST step of the workflow --
    and an EC number is not a parameter, it is the identity of the protein
    everything downstream is about. A wrong Km is a wrong number; a wrong
    EC is a citation for a different enzyme.

    Both shapes are real:

    * one protein carrying several EC numbers (bifunctional enzymes);
    * several proteins matching one name -- "lactate dehydrogenase" is
      EC 1.1.1.27 (L-lactate dehydrogenase) AND EC 1.1.1.28 (D-lactate
      dehydrogenase), which are different enzymes acting on different
      stereoisomers.

    Measured before this existed: both collapsed to "1.1.1.27" with
    nothing anywhere saying a choice had been made.

    Order is preserved -- UniProt's relevance order is information, and
    sorting would throw it away -- and duplicates are dropped, because the
    same EC appearing on two entries is one candidate, not two.
    """
    candidates: list[str] = []
    for result in data.get("results", []):
        description = result.get("proteinDescription", {})
        groups = [description.get("recommendedName", {}).get("ecNumbers", [])]
        groups.extend(
            alt.get("ecNumbers", []) for alt in description.get("alternativeNames", [])
        )
        for group in groups:
            for entry in group or []:
                value = entry.get("value")
                if value and value not in candidates:
                    candidates.append(value)
    return candidates


def fetch_ec_numbers_by_name(
    enzyme_name: str, taxon_id: str | None, timeout: float = 15
) -> list[str]:
    """Every EC number UniProt indexes under this name, most relevant first.

    `size` is 25 rather than 1. The single-result query could not see an
    ambiguity even in principle: asking for one answer and getting one
    answer says nothing about whether there was a second.

    Same one request as before -- a larger page, not more calls.
    """
    query = f'protein_name:"{enzyme_name}" AND reviewed:true'
    if taxon_id:
        query += f" AND organism_id:{taxon_id}"
    r = retry_get(
        UNIPROT_SEARCH_URL,
        params={
            "query": query,
            "fields": "accession,ec",
            "format": "json",
            "size": 25,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return parse_ec_number_candidates(r.json())


class EnzymeNameNotResolved(ValueError):
    """A name did not identify exactly one enzyme.

    Carries the candidates so a caller can render them. A refusal that
    cannot say what it refused leaves the choice unexercisable, which is the
    shape every other refusal in this project has (ADR 0024, ADR 0118).
    """

    def __init__(self, message: str, candidates: list[str] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


def ec_number_for_name(
    enzyme_name: str,
    taxon_id: str | None = None,
    *,
    fetch=None,
) -> str:
    """The ONE EC number this name identifies, or a refusal naming the rest.

    WHY THIS IS A FUNCTION AND NOT AN `if` IN EACH COMMAND
    -----------------------------------------------------
    A NAME IS NOT AN ENZYME. "lactate dehydrogenase" is EC 1.1.1.27
    (L-lactate dehydrogenase) AND EC 1.1.1.28 (D-lactate dehydrogenase) --
    different proteins acting on different stereoisomers, one common name,
    and the example in this repository's own help text (ADR 0126).

    An EC number is not a parameter; it is the IDENTITY OF THE PROTEIN
    everything downstream is about. A wrong Km is a wrong number. A wrong EC
    is a real, correctly formatted citation for a different enzyme -- the
    failure this project exists to prevent, arriving before any of the
    machinery that prevents it gets to run.

    ADR 0126 built this decision inside `report_enzyme_catalog.py`, where
    only `catalog` could reach it. `report` then shipped requiring `--ec`,
    so a student who knew the name and not the number was refused by a
    message that began "report needs an enzyme". Copying the block would
    have made two implementations of one policy, which is the defect this
    repository has found in a plausibility table (ADR 0003), a reliability
    score (ADR 0027), a codegen probe (ADR 0036) and a request validator
    (ADR 0086). So it moved here, and both commands call it.

    `fetch` is injectable for tests ONLY. It defaults to the real UniProt
    call; a test that had to reach the network to check a refusal message
    would fail for reasons unrelated to the refusal.
    """
    lookup = fetch or fetch_ec_numbers_by_name
    try:
        candidates = lookup(str(enzyme_name), taxon_id)
    except EnzymeNameNotResolved:
        raise
    except Exception as exc:  # noqa: BLE001 - reported, never a traceback
        raise EnzymeNameNotResolved(
            f"Could not look up {enzyme_name!r} in UniProt: {exc}"
        ) from exc

    if not candidates:
        raise EnzymeNameNotResolved(
            f"UniProt indexes no reviewed enzyme named {enzyme_name!r} with "
            "an EC number. Check the spelling, or pass the EC number "
            "directly if you know it."
        )
    if len(candidates) > 1:
        raise EnzymeNameNotResolved(
            f"{enzyme_name!r} names more than one enzyme: "
            + ", ".join(candidates)
            + ". These are different proteins, so Caterva will not pick one "
            "for you — a wrong EC number is a citation for the wrong enzyme, "
            "not merely a wrong value. Re-run with the one you meant.",
            candidates,
        )
    return candidates[0]


def parse_ec_number_search(data: dict) -> str | None:
    """Pure function: UniProt JSON response (fields=accession,ec) in, the
    first EC number string out, or None.

    UniProt's documented response shape nests EC numbers under
    proteinDescription.recommendedName.ecNumbers[].value; some entries
    carry them only under an alternativeNames entry instead. Both are
    checked. Returns None (never guesses) if neither is present -- e.g. a
    matched protein with no assigned EC number, or an empty result set."""
    # Built on `parse_ec_number_candidates` so the two cannot disagree
    # about what UniProt's response contains. Two parsers of one document
    # drift, and this project has the scars (ADR 0003).
    #
    # It still returns the FIRST candidate, so callers keep their current
    # behaviour. That is a silent pick when there is more than one, and it
    # is a known gap rather than a solved problem -- `catalog` refuses and
    # names the candidates instead, and the runner path does not yet.
    candidates = parse_ec_number_candidates(data)
    return candidates[0] if candidates else None


def resolve_enzyme(
    ec_number: str, taxon_id: str
) -> dict:
    """Convenience wrapper: resolve both UniProt accession and substrate
    names for an EC number in one call. Network-dependent; use
    fetch_kegg_enzyme_text + parse_kegg_substrates / fetch_uniprot_accession
    directly in tests."""
    uniprot = fetch_uniprot_accession(ec_number, taxon_id)
    kegg_text = fetch_kegg_enzyme_text(ec_number)
    substrates = parse_kegg_substrates(kegg_text)
    return {"ec_number": ec_number, "uniprot": uniprot, "substrates": substrates}


if __name__ == "__main__":
    import sys

    ec = sys.argv[1] if len(sys.argv) > 1 else "1.1.1.27"
    result = resolve_enzyme(ec)
    print(f"EC {result['ec_number']}")
    print(f"  UniProt: {result['uniprot']}")
    print(f"  Substrates: {result['substrates']}")
