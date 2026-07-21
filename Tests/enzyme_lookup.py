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

import re
from typing import Optional
from urllib.parse import quote

import httpx

UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
KEGG_GET_URL = "https://rest.kegg.jp/get/ec:{ec_number}"
PUBCHEM_SYNONYMS_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/synonyms/JSON"
)
NCBI_TAXONOMY_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

DEFAULT_TAXON_ID = "9606"  # Homo sapiens


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

def fetch_taxon_id(organism_name: str, timeout: float = 15) -> Optional[str]:
    """Fetch the NCBI taxon ID for an organism name via NCBI's taxonomy
    E-utilities. Returns None if nothing is found - never guesses.

    Uses the [Scientific Name] field qualifier rather than a bare term
    search - without it, NCBI's esearch matches against ANY indexed
    field (common names, synonyms, etc.), which risks resolving an
    organism string to the wrong taxon for ambiguous names. Restricting
    to Scientific Name is the precise, correct match for BRENDA's
    binomial-nomenclature organism strings (e.g. "Homo sapiens")."""
    params = {
        "db": "taxonomy",
        "term": f"{organism_name}[Scientific Name]",
        "retmode": "json",
    }
    r = httpx.get(NCBI_TAXONOMY_ESEARCH_URL, params=params, timeout=timeout)
    r.raise_for_status()
    return parse_taxon_id(r.json())


def parse_taxon_id(data: dict) -> Optional[str]:
    """Pure function: NCBI esearch JSON response in, taxon ID string out."""
    ids = data.get("esearchresult", {}).get("idlist", [])
    return ids[0] if ids else None


# ---------------------------------------------------------------------------
# UniProt: EC number -> canonical accession
# ---------------------------------------------------------------------------

def fetch_uniprot_accession(
    ec_number: str, taxon_id: str = DEFAULT_TAXON_ID, timeout: float = 15
) -> Optional[str]:
    """Fetch the canonical (reviewed/Swiss-Prot) UniProt accession for an
    EC number in a given organism. Returns None if nothing is found -
    never guesses or fabricates an accession."""
    params = {
        "query": f"ec:{ec_number} AND organism_id:{taxon_id} AND reviewed:true",
        "fields": "accession",
        "format": "json",
        "size": 1,
    }
    r = httpx.get(UNIPROT_SEARCH_URL, params=params, timeout=timeout)
    r.raise_for_status()
    return parse_uniprot_accession(r.json())


def parse_uniprot_accession(data: dict) -> Optional[str]:
    """Pure function: UniProt JSON response in, accession string out."""
    results = data.get("results", [])
    if not results:
        return None
    return results[0].get("primaryAccession")


# ---------------------------------------------------------------------------
# KEGG: EC number -> real reaction substrate name(s)
# ---------------------------------------------------------------------------

def fetch_kegg_enzyme_text(ec_number: str, timeout: float = 15) -> str:
    """Fetch the raw KEGG flat-file text for an EC number."""
    url = KEGG_GET_URL.format(ec_number=ec_number)
    r = httpx.get(url, timeout=timeout)
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
        r = httpx.get(url, timeout=timeout)
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


def resolve_enzyme(
    ec_number: str, taxon_id: str = DEFAULT_TAXON_ID
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
