"""
fallback_logic.py

The kinetic-value resolution chain: for a given (enzyme, organism, substrate)
triple, try progressively broader sources until something is found, and
record exactly what was tried so a "not found" result is provably a real
gap rather than a lookup that gave up early.

Tiers, in order:
  1. BRENDA, exact organism match
  2. BRENDA, any organism (cross-species) - flagged as such
  3. PubMed literature search - returns *candidate papers*, not a
     fabricated numeric value. Extracting a reliable Km from free-text
     abstracts needs real NLP/human review; this module will not guess.

Every found value carries a real Citation (see citation.py) instead of a
bare string, and BRENDA rows that brenda_client flagged as implausible
(e.g. mislabeled Kcat) are excluded from "found" results by default -
they're surfaced in search_log instead, so nothing dubious flows into the
product silently.

This replaces the earlier stubbed version, which called fake search_brenda /
search_literature_with_patience functions that always returned canned data
(including a hardcoded, non-real "1.02 mM, PMID 34962677" literature
result). That stub was fine for sketching the shape of KineticResult but
was never wired to anything real - this version is.
"""
from __future__ import annotations

import os
from typing import Callable

import httpx
from pydantic import BaseModel

import core_fulltext
import enzyme_lookup
from http_retry import retry_get

#: Optional NCBI API key -- see enzyme_lookup.py's NCBI_API_KEY for the
#: full rationale (free key, raises E-utilities from 3 to 10 req/sec,
#: fully optional). Read separately here rather than importing
#: enzyme_lookup.NCBI_API_KEY so this module has no import-time
#: dependency on enzyme_lookup just for a constant.
NCBI_API_KEY = os.environ.get("NCBI_API_KEY")
from brenda_client import (
    BRENDAKmEntry,
    KI_TABLE_LABEL,
    KM_TABLE_LABEL,
    fetch_brenda_html,
    parse_brenda_km_html,
)
from citation import Citation, citation_from_brenda_entry, pubmed_url

PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

# Which BRENDA table a quantity resolves from. Km and Ki are both
# concentrations in mM served by their own table ("KM Values" / "Ki
# Values"); the mapping is what lets one resolution chain serve both.
QUANTITY_TABLE_LABELS = {
    "km": KM_TABLE_LABEL,
    "ki": KI_TABLE_LABEL,
}


class LiteratureCandidate(BaseModel):
    title: str
    url: str
    #: "pubmed" (default, unchanged from before CORE was added) or "core"
    #: (open-access full text via Tests/core_fulltext.py). Kept explicit
    #: rather than inferred from which ID field is set, since a CORE
    #: result can itself carry a pmid-shaped-looking numeric ID that is
    #: NOT a PMID -- collapsing the two would let a CORE result silently
    #: masquerade as a PubMed one.
    source: str = "pubmed"
    #: Set for source="pubmed"; None for source="core".
    pmid: str | None = None
    #: Set when known for either source; CORE search results commonly
    #: carry a DOI, PubMed's esummary response does not.
    doi: str | None = None


class KineticResult(BaseModel):
    found: bool
    value: float | None = None
    unit: str | None = None
    organism: str | None = None
    source: str  # "brenda_exact" | "brenda_cross_species" | "literature_candidates" | "not_found"
    citation: Citation | None = None
    cross_species_flag: bool = False

    #: Assay conditions the Km was measured under, parsed from the BRENDA
    #: commentary. STRENDA requires temperature and pH for all reported
    #: kinetic data, and Km moves with both -- a Km without them cannot be
    #: reproduced or compared. Absent when the source did not report them;
    #: never guessed. See ADR 0010.
    assay_ph: float | None = None
    assay_temperature_c: float | None = None
    assay_buffer: str | None = None

    #: Fields BRENDA explicitly states the original publication did not
    #: report. A fact about the literature, distinct from a parse failure.
    assay_unreported: list[str] = []

    literature_candidates: list[LiteratureCandidate] = []
    search_log: list[str] = []


HtmlProvider = Callable[[str], str]
UniprotProvider = Callable[[str, str], str | None]
TaxonIdProvider = Callable[[str], str | None]


def _resolve_fallback_uniprot(
    ec_number: str,
    organism: str | None,
    uniprot_provider: UniprotProvider,
    taxon_id_provider: TaxonIdProvider = enzyme_lookup.fetch_taxon_id,
) -> str | None:
    """Resolve a UniProt fallback accession for a specific organism. Only
    attempted when the organism is known (exact-match tier); for
    cross-species results there's no single correct accession to guess,
    so this returns None and per-row accessions (if any) are used as-is.

    The organism -> taxon ID step is resolved dynamically via NCBI's
    taxonomy database (enzyme_lookup.fetch_taxon_id), not a fixed dict -
    an earlier version covered only ~7 hardcoded organisms and silently
    returned no fallback accession for anything else. taxon_id_provider
    is injectable so this stays testable offline."""
    if organism is None:
        return None
    taxon_id = taxon_id_provider(organism)
    if not taxon_id:
        return None
    return uniprot_provider(ec_number, taxon_id)


def _brenda_entries(
    ec_number: str,
    organism: str | None,
    substrate: str,
    html_provider: HtmlProvider,
    uniprot_provider: UniprotProvider,
    taxon_id_provider: TaxonIdProvider = enzyme_lookup.fetch_taxon_id,
    table_label: str = KM_TABLE_LABEL,
) -> list[BRENDAKmEntry]:
    html = html_provider(ec_number)
    fallback_uniprot = _resolve_fallback_uniprot(
        ec_number, organism, uniprot_provider, taxon_id_provider
    )

    # A real, confirmed bug (found live testing 'trypsin', a peptidase):
    # passing target_substrates=[""] with require_substrate_match=True
    # (the implicit default below) rejects EVERY row. parse_brenda_km_html's
    # matching loop treats "" as matching any text (an empty string is a
    # substring of everything), but "" is itself falsy, so
    # `if not matched_substrate` is still True and, with strict matching on,
    # every row hits its `else: continue` -- the strict path silently
    # returns zero results instead of running the permissive fallback that
    # already exists for exactly this case (best-effort compound label,
    # substrate_verified=False). This happens for any enzyme resolved via
    # the live UniProt/KEGG path (queryResolver.ts's guess -> science_agent_runner.py)
    # when KEGG has no SUBSTRATE field to resolve one from -- a documented,
    # common gap for peptidases (EC 3.4.x.x), not a rare edge case.
    #
    # A caller-supplied enzymes.ts-style substrate is never empty, so this
    # was never reachable before that live path existed.
    require_substrate_match = bool(substrate)
    target_substrates = [substrate] if substrate else []

    entries = parse_brenda_km_html(
        html,
        ec_number,
        target_substrates=target_substrates,
        target_organism=organism,
        fallback_uniprot=fallback_uniprot,
        require_substrate_match=require_substrate_match,
        table_label=table_label,
    )
    # Never surface flagged (implausible) rows as a "found" result -
    # they're data-quality problems, not answers.
    return [e for e in entries if not e.flagged]


def search_pubmed_candidates(
    enzyme_name: str,
    organism: str,
    substrate: str,
    max_results: int = 5,
    quantity: str = "km",
) -> list[LiteratureCandidate]:
    """Search PubMed for candidate papers. Returns titles/links only -
    does not attempt to extract a numeric Km/Ki from abstract text, since
    that requires human judgment to do reliably and safely."""
    quantity_term = "inhibition constant" if quantity == "ki" else "Km kinetics"
    query = f"{enzyme_name} {organism} {substrate} {quantity_term}"
    esearch_params = {
        "db": "pubmed", "term": query, "retmax": max_results, "retmode": "json",
    }
    if NCBI_API_KEY:
        esearch_params["api_key"] = NCBI_API_KEY
    r = retry_get(PUBMED_ESEARCH_URL, params=esearch_params, timeout=15)
    r.raise_for_status()
    ids = r.json()["esearchresult"]["idlist"]
    if not ids:
        return []

    esummary_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
    if NCBI_API_KEY:
        esummary_params["api_key"] = NCBI_API_KEY
    r2 = retry_get(
        PUBMED_ESUMMARY_URL,
        params=esummary_params,
        timeout=15,
    )
    r2.raise_for_status()
    result = r2.json()["result"]

    candidates = []
    for uid in result.get("uids", []):
        title = result[uid].get("title", "")
        candidates.append(
            LiteratureCandidate(pmid=uid, title=title, url=pubmed_url(uid))
        )
    return candidates


def resolve_kinetic_value(
    enzyme_ec: str,
    organism: str,
    substrate: str,
    enzyme_name: str | None = None,
    html_provider: HtmlProvider = fetch_brenda_html,
    uniprot_provider: UniprotProvider = enzyme_lookup.fetch_uniprot_accession,
    taxon_id_provider: TaxonIdProvider = enzyme_lookup.fetch_taxon_id,
    search_literature: bool = True,
    quantity: str = "km",
) -> KineticResult:
    """Resolve a kinetic value for (enzyme, organism, substrate) by trying
    BRENDA exact match, then BRENDA cross-species, then PubMed literature
    (candidates only, no fabricated numbers).

    ``quantity`` selects which BRENDA table is read ("km" -> KM Values,
    "ki" -> Ki Values) and which term the PubMed search uses. Km and Ki
    resolve through the same chain, and a call resolves exactly one
    quantity: a cross-species Ki must never borrow a verified Km's
    provenance, which the runner enforces by calling this once per
    quantity with its own citation (see ADR 0008 / provenance.ts).

    html_provider, uniprot_provider, and taxon_id_provider are injectable
    so this can be tested offline: pass functions that return fixture
    data instead of hitting the network.
    """
    table_label = QUANTITY_TABLE_LABELS.get(quantity, KM_TABLE_LABEL)
    quantity_upper = "Ki" if quantity == "ki" else "Km"
    log = []

    log.append(f"BRENDA exact: {enzyme_ec}, {organism}, {substrate} ({quantity})")
    exact = _brenda_entries(
        enzyme_ec, organism, substrate, html_provider, uniprot_provider,
        taxon_id_provider, table_label=table_label,
    )
    if exact:
        best = min(exact, key=lambda e: e.km_value)
        return KineticResult(
            found=True,
            value=best.km_value,
            unit=best.unit,
            organism=best.organism,
            source="brenda_exact",
            citation=citation_from_brenda_entry(best),
            assay_ph=best.assay_ph,
            assay_temperature_c=best.assay_temperature_c,
            assay_buffer=best.assay_buffer,
            assay_unreported=list(best.assay_unreported),
            search_log=log,
        )

    log.append(f"BRENDA any organism: {enzyme_ec}, {substrate} ({quantity})")
    broad = _brenda_entries(
        enzyme_ec, None, substrate, html_provider, uniprot_provider,
        taxon_id_provider, table_label=table_label,
    )
    if broad:
        best = min(broad, key=lambda e: e.km_value)
        return KineticResult(
            found=True,
            value=best.km_value,
            unit=best.unit,
            organism=best.organism,
            source="brenda_cross_species",
            citation=citation_from_brenda_entry(best),
            cross_species_flag=True,
            assay_ph=best.assay_ph,
            assay_temperature_c=best.assay_temperature_c,
            assay_buffer=best.assay_buffer,
            assay_unreported=list(best.assay_unreported),
            search_log=log,
        )

    if not search_literature:
        log.append("Literature search skipped (search_literature=False)")
        return KineticResult(found=False, source="not_found", search_log=log)

    log.append(f"PubMed literature search: {enzyme_name or enzyme_ec}, {organism}, {substrate}")
    candidates = search_pubmed_candidates(
        enzyme_name or enzyme_ec, organism, substrate, quantity=quantity
    )

    # CORE supplements PubMed rather than replacing it: PubMed indexes far
    # more biomedical literature overall, but a fraction of what it finds
    # has no open-access full text (see ADR 0017 -- Guerra et al. 2017's
    # measles R0 review, PMID 28757186, is exactly this case: indexed by
    # PubMed, but its full stratified R0 table was unreachable without a
    # subscription). Appending CORE candidates rather than branching on
    # "PubMed found nothing" means a query that DOES have PubMed hits
    # still benefits if CORE surfaces an open-access source for the same
    # topic that PubMed's metadata-only search didn't fully capture.
    # core_fulltext.resolve_open_access_fulltext() already degrades to
    # found=False with no exception when CORE_API_KEY is unset or the
    # request fails, so this is safe to call unconditionally.
    core_query = f"{enzyme_name or enzyme_ec} {organism} {substrate} {quantity_upper}"
    core_result = core_fulltext.resolve_open_access_fulltext(core_query)
    if core_result.found:
        log.append(
            f"CORE open-access search added {len(core_result.candidates)} "
            f"candidate(s): {'; '.join(core_result.search_log)}"
        )
        for c in core_result.candidates:
            candidates.append(
                LiteratureCandidate(
                    title=c.title,
                    url=c.download_url or f"https://core.ac.uk/works/{c.core_id}",
                    source="core",
                    doi=c.doi,
                )
            )
    elif core_fulltext.CORE_API_KEY:
        # Only log a CORE miss when a key was actually configured -- an
        # unconfigured key already has its own "skipped" log entry inside
        # resolve_open_access_fulltext, and duplicating it here would be
        # noise on every single call for anyone who never set CORE_API_KEY.
        log.append(f"CORE open-access search: {'; '.join(core_result.search_log)}")

    if candidates:
        log.append(
            f"Found {len(candidates)} candidate paper(s) total; numeric "
            f"{quantity_upper} NOT auto-extracted, needs manual review"
        )
        return KineticResult(
            found=False,
            source="literature_candidates",
            literature_candidates=candidates,
            search_log=log,
        )

    log.append(
        "Exhausted BRENDA (exact + cross-species), PubMed, and CORE - genuine gap"
    )
    return KineticResult(found=False, source="not_found", search_log=log)


if __name__ == "__main__":
    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "lactate", enzyme_name="lactate dehydrogenase"
    )
    print(result.model_dump_json(indent=2))
