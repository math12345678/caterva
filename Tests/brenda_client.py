"""
brenda_client.py

Importable client for pulling Km kinetics data out of BRENDA
(https://www.brenda-enzymes.org) enzyme pages.

Design notes:
- `fetch_brenda_html()` is the only function that touches the network for
  BRENDA itself.
- `parse_brenda_km_html()` is a pure function: HTML string in, list of
  BRENDAKmEntry out. It has NO built-in knowledge of any specific enzyme -
  it needs the target substrate names (and optionally a UniProt fallback)
  passed in explicitly. This means it can be unit tested against saved
  fixture HTML with zero network dependency, and it works for any EC
  number, not just a fixed set baked into this module.
- `fetch_and_parse_brenda_km()` is the orchestrator: given just an EC
  number, it resolves the real substrate name(s) via KEGG and the
  canonical UniProt accession via the UniProt API (see enzyme_lookup.py),
  then fetches and parses the BRENDA page. This is what removed the
  original hardcoded ENZYME_REGISTRY - nothing enzyme-specific is baked
  into this file anymore; every enzyme is resolved dynamically.

Why a substrate filter is needed at all (not just "return everything"): a
BRENDA enzyme page lists Km/Ki/IC50 data for every compound anyone has
ever tested against that enzyme, not just its real physiological
substrate - see the raw unfiltered AChE dump earlier in this project,
which was mostly inhibitor compounds. Filtering to the real substrate
name(s) is what makes the difference between real kinetics data and drug-
screening noise. What changed is where that substrate name comes from:
it used to be a hardcoded per-enzyme list in this file; now it's resolved
live from KEGG for any EC number, so nothing needs to be added by hand
to support a new enzyme.

History: the original version of this parser (brenda_structured.py)
silently returned 0 results for AChE because BRENDA renders the
substrate name as "acetyl thiocholine" (two words) while the substrate
whitelist checked for "acetylthiocholine" (one word) as a substring.
Substring matching is fragile for exactly this reason - matching here is
intentionally permissive (case-insensitive substring), and callers should
pass every known spelling variant for a substrate name when they have one.
"""

import re
from typing import List

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

import enzyme_lookup
from assay_conditions import parse_assay_conditions


class BRENDAKmEntry(BaseModel):
    km_value: float
    unit: str = "mM"
    substrate: str
    organism: str
    uniprot: str | None = None
    #: Raw commentary cell from BRENDA, e.g. "pH 8.5, 25°C, isozyme H4".
    conditions: str | None = None
    # --- Structured assay conditions, parsed from `conditions` -------------
    #
    # STRENDA requires temperature and pH for all reported kinetic data
    # ("...MUST always be included, even if previously published",
    # Guidelines v1.4.0). Km is a property of an enzyme *measured under
    # conditions* and moves with both, so a Km without them cannot be
    # reproduced or compared. BRENDA supplies them in the commentary; before
    # this they were captured as raw text and never read. See ADR 0010.
    #
    # None means "not available", never a default. Nothing here is guessed.
    assay_ph: float | None = None
    assay_temperature_c: float | None = None
    assay_buffer: str | None = None
    #: Fields BRENDA explicitly states the original publication did not
    #: report -- a fact about the literature, distinct from a parse failure.
    assay_unreported: List[str] = Field(default_factory=list)
    reference_id: str | None = None
    ec_number: str | None = None
    flagged: bool = False
    flag_reason: str | None = None
    # False when this row was NOT matched against a known substrate name
    # (or synonym) and was instead included via the unfiltered fallback -
    # see fetch_and_parse_brenda_km. When False, `substrate` is a
    # best-effort label straight from BRENDA's page, not a confirmed
    # match, and the row could be an inhibitor/off-target compound rather
    # than the enzyme's real substrate. Always True for rows matched the
    # normal way.
    substrate_verified: bool = True
    # True when this row was found inside BRENDA's actual "KM Values"
    # table container (structurally, via _find_table_container), rather
    # than a whole-page fallback scan. When True, Ki/Turnover Number/
    # IC50/Inhibitor rows have already been structurally excluded, not
    # just guessed at by the numeric-range heuristic - a much stronger
    # correctness guarantee. When False, the row-selection step couldn't
    # locate the KM Values container in this HTML at all (unusual page
    # layout, or a fixture without the nav sidebar), and only the numeric-
    # range/"mentions Kcat" heuristics stand between this entry and a
    # genuinely different kind of value.
    table_scoped: bool = True
    # "classic" (small-molecule/chromogenic substrate a bench scientist
    # would recognize, e.g. lactate, BAPNA-style compounds) vs
    # "engineered_reporter" (protein/FRET reporter constructs like
    # "enhanced green fluorescent protein-T1" - real BRENDA data, but not
    # what someone asking "what's the Km for trypsin" usually expects).
    # See classify_substrate() below. Nothing is excluded based on this -
    # it's metadata for downstream filtering/ranking decisions, not a
    # parsing-stage filter.
    substrate_type: str = "classic"


# Keywords that mark a substrate as an engineered/reporter construct rather
# than a classic small-molecule or peptide substrate. This is a generic
# heuristic, not enzyme-specific data, so it stays here rather than in
# enzyme_lookup.py. Matched case-insensitively as a substring.
ENGINEERED_REPORTER_KEYWORDS = [
    "fluorescent protein",
    "gfp",
    "egfp",
    "fret",
    "luciferase",
]


def classify_substrate(substrate_name: str) -> str:
    """Classify a substrate name as 'classic' or 'engineered_reporter'."""
    name_lower = substrate_name.lower()
    for keyword in ENGINEERED_REPORTER_KEYWORDS:
        if keyword in name_lower:
            return "engineered_reporter"
    return "classic"


# Plausible Km range in mM. Values outside this are almost always a
# mislabeled Kcat, Ki, IC50, or a unit/table-parsing artifact from BRENDA,
# not a genuine Michaelis constant. Generic heuristic, not enzyme-specific.
KM_PLAUSIBLE_MIN_MM = 0.0000001
KM_PLAUSIBLE_MAX_MM = 1000

# kcat (turnover number), s^-1. Must match Tellurium/core/data_structures.py
# exactly -- ADR 0003 makes these a cross-layer contract, and
# scripts/check_plausibility_constants.py enforces the agreement.
#
# Anchored to Bar-Even et al. (2011), Biochemistry 50(21), 4402-4410
# (median kcat ~10 s^-1 across several thousand enzymes); catalase, the
# fastest known enzyme, is ~4e7 s^-1; the diffusion-limited ceiling is
# ~1e8-1e9 s^-1. Above that a number cannot be a turnover rate at all.
KCAT_PLAUSIBLE_MIN_PER_S = 0.000001
KCAT_PLAUSIBLE_MAX_PER_S = 1000000000

#: BRENDA's navigation label for the turnover-number table.
TURNOVER_TABLE_LABEL = "Turnover Numbers"

BRENDA_ENZYME_URL = "https://www.brenda-enzymes.org/enzyme.php"


def fetch_brenda_html(ec_number: str, timeout: float = 15) -> str:
    """Fetch the raw HTML for a BRENDA enzyme page. The only network call
    in this module - keep it isolated so parsing stays testable offline."""
    r = httpx.get(BRENDA_ENZYME_URL, params={"ecno": ec_number}, timeout=timeout)
    r.raise_for_status()
    return r.text


# Generic binomial-nomenclature pattern ("Genus species", optionally
# "Genus species subspecies") used to *recognize* an organism cell when
# searching across all species (target_organism=None) or picking a
# fallback substrate label. This replaced an earlier enumerated list of
# ~10 organism names, which silently missed any organism outside that
# list - confirmed live: Cryptosporidium parvum and Epidalea calamita
# (real BRENDA LDH data) were invisible to the old pattern. Matched with
# fullmatch() against a single cell's text (never substring-searched
# across a whole row), which keeps it from misfiring on capitalized
# condition-text fragments like "Wild type" while still working for any
# organism BRENDA reports, not a fixed list.
GENERIC_ORGANISM_PATTERN = re.compile(r"[A-Z][a-z]{2,}(?:\s[a-z]{2,}){1,2}")

# Real UniProt accession syntax (from UniProt's own documentation), not
# the narrower "one letter + 5 digits" pattern used earlier. That
# narrower pattern (^[A-Z]\d{5}$) matched simple accessions like
# "P17538" or "P07864" but silently missed real accessions that mix
# letters into the middle positions, e.g. "Q6GPI1" (confirmed live on a
# real chymotrypsin row: "Q6GPI1,P17538") - caught by
# test_chymotrypsin_uniprot_present_on_every_real_row failing against
# real captured data. Two accession shapes are valid:
#   - starts with O, P, or Q:      [OPQ][0-9][A-Z0-9]{3}[0-9]
#   - starts with any other letter: [A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}
_UNIPROT_ACCESSION = (
    r"(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})"
)
# A cell can carry multiple comma-separated accessions (isozyme subunits
# sharing one BRENDA row, e.g. LDH's "P00339,P00336" or chymotrypsin's
# "Q6GPI1,P17538") - matched and kept whole, not truncated to one.
UNIPROT_CELL_PATTERN = re.compile(rf"^{_UNIPROT_ACCESSION}(?:,{_UNIPROT_ACCESSION})*$")

# Regex to pull a tab id (e.g. "tab12") out of a BRENDA nav link's href,
# which looks like: javascript:showTable('tab12')
_SHOW_TABLE_HREF_PATTERN = re.compile(r"showTable\('(tab\d+)'\)")


def _find_table_container(soup: BeautifulSoup, label: str):
    """Find the HTML container for a specific BRENDA data table by its
    navigation label (e.g. "KM Values", "Ki Values", "Turnover Numbers").

    Every BRENDA enzyme page reuses the same generic row/cell div classes
    for EVERY table on the page - Synonyms, Reactions, Substrates,
    Inhibitors, Km Values, Turnover Numbers, Ki Values, IC50 Values, etc.
    all look identical at the row/cell level. Scanning the whole page for
    "div.row" therefore mixes genuinely different kinds of data together:
    a row from the Ki Values table looks structurally identical to a row
    from the Km Values table. This is why the numeric-range/"mentions
    Kcat" heuristics existed - they were trying to guess, after the fact,
    which table a mixed-in row actually came from.

    BRENDA's navigation sidebar links each table to a specific container
    via a "javascript:showTable('tabN')" href, where N is a page-specific
    numeric id (NOT stable across enzymes or even across page loads) but
    the link TEXT ("KM Values" etc.) is always the same. This function
    finds the container the same way a person clicking that link would -
    by label text, not a hardcoded tab number - so it works for any
    enzyme's page.

    Returns the container Tag if found, else None (caller should fall
    back to whole-page scanning and treat results as less trustworthy).
    """
    for a in soup.find_all("a", href=True):
        if a.get_text(strip=True).strip().lower() != label.lower():
            continue
        href = a["href"]
        if isinstance(href, list):
            href = href[0] if href else ""
        match = _SHOW_TABLE_HREF_PATTERN.search(str(href))
        if not match:
            continue
        tab_id = match.group(1)
        container = soup.find(id=tab_id)
        if container is not None:
            return container
    return None


def parse_brenda_km_html(
    html: str,
    ec_number: str,
    target_substrates: list,
    target_organism: str | None = "Homo sapiens",
    fallback_uniprot: str | None = None,
    require_substrate_match: bool = True,
    table_label: str = "KM Values",
) -> list[BRENDAKmEntry]:
    """Pure parsing function: HTML string in, structured Km entries out.
    No network access, no built-in knowledge of any specific enzyme.

    target_substrates must be the real substrate name(s) for this EC
    number (e.g. resolved via enzyme_lookup.parse_kegg_substrates, possibly
    expanded with enzyme_lookup.expand_substrates_with_synonyms). This
    function does not know or guess what a valid substrate looks like for
    a given enzyme - that knowledge has to come from the caller.

    fallback_uniprot is used only when a row doesn't carry its own UniProt
    accession cell. Pass None if you don't have one; rows will just have
    uniprot=None in that case rather than a guessed value.

    target_organism=None switches to cross-species mode: every organism is
    accepted, and the organism label is extracted per-row from a known
    binomial-name list rather than filtered against a fixed string. Used
    by the cross-species fallback tier in fallback_logic.py.

    require_substrate_match=False switches to permissive mode: rows that
    don't match any name in target_substrates are still included, with
    substrate set to a best-effort label (the row's compound-name cell)
    and substrate_verified=False, instead of being dropped. This exists
    because substrate-name matching genuinely cannot succeed for every
    enzyme - e.g. broad-specificity enzymes where KEGG reports a generic
    class ("primary alcohol") rather than a specific compound, or enzymes
    whose real BRENDA data is reported on a synthetic assay surrogate
    unrelated by name to the canonical substrate (acetylcholinesterase on
    "acetylthiocholine" rather than "acetylcholine"). Rather than silently
    returning zero results in those cases, permissive mode returns the
    real data with an explicit "unverified" marker so a human or
    downstream code can decide whether to trust it.
    """

    # Plausibility bounds and labelling depend on which table is parsed.
    # Km is in mM; kcat is a turnover number in s^-1, so the Km range is
    # meaningless for it -- a kcat of 6500 is ordinary, a Km of 6500 mM is a
    # unit error. Sharing the Km bounds would flag every fast enzyme.
    if table_label == TURNOVER_TABLE_LABEL:
        _quantity, _unit = "kcat", "1/s"
        _min_value, _max_value = KCAT_PLAUSIBLE_MIN_PER_S, KCAT_PLAUSIBLE_MAX_PER_S
    else:
        _quantity, _unit = "Km", "mM"
        _min_value, _max_value = KM_PLAUSIBLE_MIN_MM, KM_PLAUSIBLE_MAX_MM

    soup = BeautifulSoup(html, "lxml")

    km_table = _find_table_container(soup, table_label)
    if km_table is not None:
        search_root = km_table
        table_scoped = True
    else:
        # Couldn't find the "KM Values" nav link/container (e.g. a fixture
        # without the nav sidebar, or a genuinely different page layout).
        # Fall back to scanning the whole page like before, but every
        # resulting entry gets table_scoped=False so callers know rows
        # from other tables (Ki, Turnover Number, IC50, Inhibitors, etc.)
        # were NOT structurally excluded here - only the numeric-range and
        # "mentions Kcat" heuristics are catching anything in that case.
        search_root = soup
        table_scoped = False

    rows = search_root.find_all("div", class_=re.compile(r"row"))

    # BRENDA collapses substrates with many measurements into an aggregate
    # summary row (e.g. "0.0018 - 1100 | (S)-lactate | 50 entries") whose
    # own first cell is a RANGE, not a single value - that already fails
    # the numeric km_match check below and is correctly skipped rather
    # than fabricating a point value from a range. The individual
    # measurements behind it are real, already-present in the static HTML
    # as hidden sibling rows (id pattern "{row_id}sr{N}"), unhidden
    # client-side by BRENDA's showRows() JS - no extra network request
    # needed. Confirmed live (2026-07): sub-row cell layout matches
    # regular rows exactly (value, substrate, organism, uniprot,
    # conditions, ref id). Pull them in so aggregate substrates aren't
    # silently dropped.
    subrows = search_root.find_all("div", id=re.compile(r"sr\d+$"))

    # Deduplicate by identity. A sub-row that ALSO carries a "row" class is
    # matched by both selectors, and plain concatenation then parsed it
    # twice -- the same measurement returned as two entries. The Km fixtures
    # never tripped this; the AChE Turnover Numbers capture has 11 such rows.
    _seen: dict = {}
    for _row in rows + subrows:
        _seen.setdefault(id(_row), _row)
    rows = list(_seen.values())

    results = []
    for row in rows:
        cells = row.find_all("div", class_="cell")
        if len(cells) < 3:
            continue
        cell_texts = [c.get_text(strip=True) for c in cells]
        full_text = " | ".join(cell_texts)

        if target_organism is not None:
            if target_organism not in full_text:
                continue
            row_organism = target_organism
        else:
            row_organism = None
            for cell in cell_texts:
                cell_clean = cell.strip()
                if GENERIC_ORGANISM_PATTERN.fullmatch(cell_clean):
                    row_organism = cell_clean
                    break
            if row_organism is None:
                continue

        km_match = re.match(r"^(\d+\.?\d*)$", cell_texts[0].strip())
        if not km_match:
            continue
        km_value = float(km_match.group(1))

        matched_substrate = None
        for sub in target_substrates:
            if sub.lower() in full_text.lower():
                matched_substrate = sub
                break

        substrate_verified = True
        if not matched_substrate:
            if not require_substrate_match:
                # Best-effort label only. Usually the compound/substrate
                # name lives in cell index 1, but some real BRENDA rows put
                # the organism there instead (confirmed live: EC 3.1.1.7
                # has rows like "0.0146 | Homo sapiens | - | hemolysate...").
                # Scan cells after the Km value and skip anything that's
                # clearly not a compound name - organism names, the target
                # organism string itself, UniProt-accession-shaped cells,
                # placeholders, and bare numbers (reference IDs) - before
                # falling back to "unknown compound" rather than mislabeling
                # a row with an organism name.
                candidate = None
                for cell in cell_texts[1:]:
                    cell_clean = cell.strip()
                    if not cell_clean or cell_clean == "-":
                        continue
                    if GENERIC_ORGANISM_PATTERN.fullmatch(cell_clean):
                        continue
                    if target_organism is not None and cell_clean == target_organism:
                        continue
                    if UNIPROT_CELL_PATTERN.match(cell_clean):
                        continue
                    if re.match(r"^\d+\.?\d*$", cell_clean):
                        continue
                    candidate = cell_clean
                    break

                matched_substrate = candidate or "unknown compound"
                substrate_verified = False
            else:
                continue

        uniprot = None
        for cell in cell_texts:
            # Some rows (e.g. multi-isozyme entries like LDH's sub-rows)
            # carry more than one accession in a single comma-separated
            # cell, e.g. "P00339,P00336" - both are real, keep the cell
            # as-is rather than picking just one.
            if UNIPROT_CELL_PATTERN.match(cell.strip()):
                uniprot = cell.strip()
                break
        if uniprot is None:
            uniprot = fallback_uniprot

        # The commentary cell, by POSITION rather than by length.
        #
        # BRENDA's row layout is fixed:
        #   value | substrate | organism | uniprot | commentary | reference id
        # so the commentary is the cell after the organism and before the
        # six-digit reference id.
        #
        # This was `max(cell_texts, key=len)` -- pick the longest cell -- which
        # silently returns the SUBSTRATE whenever the substrate name happens to
        # be longer than the commentary. Real case from the AChE turnover
        # table: three Mus musculus sub-rows whose commentaries are
        # "wild-type enzyme", "A262C mutant" and "E81C mutant" (16, 12 and 11
        # characters) all lost to "acetylthiocholine iodide" (24). The three
        # became indistinguishable, and every assay condition on an aggregate
        # sub-row was discarded -- exactly the STRENDA data ADR 0010 exists to
        # preserve.
        conditions = None
        if cell_texts:
            ref_index = None
            for idx in range(len(cell_texts) - 1, -1, -1):
                if re.match(r"^\d{6}$", cell_texts[idx].strip()):
                    ref_index = idx
                    break
            if ref_index is not None and ref_index >= 1:
                candidate = cell_texts[ref_index - 1].strip()
                # Guard against a row missing its commentary entirely, where
                # cell[ref-1] would be the uniprot or a placeholder.
                if (
                    candidate
                    and candidate != "-"
                    and not UNIPROT_CELL_PATTERN.match(candidate)
                ):
                    conditions = candidate
            if conditions is None and ref_index is None:
                # Layout did not match at all (unusual page, or a fixture
                # without a reference cell). Fall back to the old heuristic
                # rather than dropping the commentary altogether.
                conditions = max(cell_texts, key=len)
            # When the layout DID match and the commentary cell was empty or
            # "-", conditions stays None. That is the honest answer: BRENDA
            # reported no commentary for this row.
            #
            # Previously the longest-cell heuristic filled it with whatever
            # else was on the row -- usually the ORGANISM. Two real LDH
            # pyruvate rows came back with conditions="Homo sapiens", which
            # parse_assay_conditions then dutifully searched for a pH and a
            # temperature. It found none, so nothing was fabricated, but the
            # field claimed a commentary that did not exist.

        ref_id = None
        for cell in reversed(cell_texts):
            if re.match(r"^\d{6}$", cell.strip()):
                ref_id = cell.strip()
                break

        flagged = False
        flag_reason = None
        scope_note = (
            "row is inside BRENDA's actual KM Values table"
            if table_scoped
            else "row-selection could not confirm this came from the KM "
                 "Values table specifically (whole-page fallback scan) - "
                 "this may genuinely be a Ki/Turnover Number/IC50 value"
        )
        if km_value > _max_value or km_value < _min_value:
            flagged = True
            flag_reason = (
                f"{_quantity} value {km_value} {_unit} is outside plausible range "
                f"({_min_value}-{_max_value} {_unit}); "
                f"likely a unit error or an anomalous entry ({scope_note})"
            )
        elif (
            _quantity == "Km"
            and conditions
            and re.search(r"\bkcat\b", conditions, re.IGNORECASE)
        ):
            flagged = True
            flag_reason = (
                "conditions text mentions Kcat; row may report a turnover "
                f"number rather than a true Km ({scope_note})"
            )
        elif not table_scoped:
            # Even when nothing else looks wrong, whole-page fallback rows
            # never had Ki/Turnover Number/IC50 tables structurally
            # excluded - flag as a lower-confidence signal, not a hard
            # "something's wrong" the way the two checks above are.
            flagged = True
            flag_reason = (
                "row-selection fell back to a whole-page scan (BRENDA's "
                f"'{table_label}' table container could not be located in this "
                "HTML), so rows from other tables (Ki, Turnover Number, "
                "IC50, Inhibitors) were not structurally excluded - this "
                f"value has not been confirmed to be a true {_quantity}"
            )

        # Parse the commentary into structured assay conditions (ADR 0010).
        # Never raises; absent fields stay None rather than being defaulted.
        parsed_conditions = parse_assay_conditions(conditions)

        results.append(
            BRENDAKmEntry(
                km_value=km_value,
                unit="mM",
                substrate=matched_substrate,
                organism=row_organism,
                uniprot=uniprot,
                conditions=conditions,
                assay_ph=parsed_conditions.ph,
                assay_temperature_c=parsed_conditions.temperature_c,
                assay_buffer=parsed_conditions.buffer,
                assay_unreported=parsed_conditions.explicitly_unreported,
                reference_id=ref_id,
                ec_number=ec_number,
                flagged=flagged,
                flag_reason=flag_reason,
                substrate_type=classify_substrate(matched_substrate),
                substrate_verified=substrate_verified,
                table_scoped=table_scoped,
            )
        )

    return results


def parse_brenda_turnover_html(
    html: str,
    ec_number: str,
    target_substrates: list,
    target_organism: str | None = "Homo sapiens",
    fallback_uniprot: str | None = None,
    require_substrate_match: bool = True,
) -> list[BRENDAKmEntry]:
    """Parse BRENDA's "Turnover Numbers" table into structured entries.

    kcat is a turnover number in s^-1, not a concentration -- but BRENDA
    serves it with the identical six-cell row layout as KM Values (value,
    substrate, organism, uniprot, commentary, reference id), including the
    same aggregate "N entries" summary rows and the same free-text
    commentary carrying pH and temperature.

    So this delegates to the Km parser with a different table label and
    different plausibility bounds, rather than duplicating ~250 lines of
    row-scoping, aggregate expansion and assay-condition logic that would
    then drift out of sync.

    ``km_value`` on the returned entries carries the kcat in s^-1. The field
    name is inherited from the shared row model; the unit is NOT mM.

    STRENDA governs kcat exactly as it governs Km (ADR 0010): a turnover
    number measured at an unreported pH or temperature cannot be reproduced
    or compared, so assay conditions are parsed here too and travel with
    the value.
    """
    return parse_brenda_km_html(
        html=html,
        ec_number=ec_number,
        target_substrates=target_substrates,
        target_organism=target_organism,
        fallback_uniprot=fallback_uniprot,
        require_substrate_match=require_substrate_match,
        table_label=TURNOVER_TABLE_LABEL,
    )


def fetch_and_parse_brenda_km(
    ec_number: str,
    target_organism: str | None = "Homo sapiens",
    target_substrates: list | None = None,
    taxon_id: str = enzyme_lookup.DEFAULT_TAXON_ID,
    expand_synonyms: bool = True,
    allow_unverified_fallback: bool = True,
    table_label: str = "KM Values",
) -> list[BRENDAKmEntry]:
    """Orchestrator: given just an EC number, dynamically resolve its real
    substrate name(s) (via KEGG) and canonical UniProt accession (via the
    UniProt API) if they weren't supplied explicitly, then fetch and parse
    the BRENDA page. Works for any EC number - nothing enzyme-specific is
    hardcoded in this module.

    Pass target_substrates explicitly to skip the KEGG lookup (e.g. if you
    already know the substrate names, or KEGG doesn't have an entry for an
    unusual EC number).

    Three-tier matching strategy, tried in order until one returns results:
      1. Strict match against the KEGG substrate name(s) as-is.
      2. If that returns nothing and expand_synonyms=True: retry with
         PubChem synonyms added (catches cases where BRENDA and KEGG use
         different names for the identical molecule).
      3. If that STILL returns nothing and allow_unverified_fallback=True:
         return every human numeric-Km row for this EC number, unfiltered,
         with substrate_verified=False on every entry. This exists because
         some real, common cases can't be solved by name-matching at all -
         broad-specificity enzymes where KEGG only has a generic class
         name, or enzymes whose real assay substrate is a synthetic
         surrogate unrelated by name to the canonical one. Rather than
         silently returning nothing in those cases, the real data comes
         back explicitly marked as unconfirmed.
    """
    if target_substrates is None:
        kegg_text = enzyme_lookup.fetch_kegg_enzyme_text(ec_number)
        target_substrates = enzyme_lookup.parse_kegg_substrates(kegg_text)
        if not target_substrates:
            # KEGG has no SUBSTRATE field at all for this EC number - a
            # real, structural gap for peptidases (EC 3.4.x.x), whose KEGG
            # entries only list gene orthologs and cleavage-specificity
            # comments (e.g. "Preferential cleavage: Arg-|-Xaa"), never a
            # compound-based SUBSTRATE list, since they act on protein
            # substrates rather than named small molecules. Confirmed live
            # for trypsin (3.4.21.4) and chymotrypsin (3.4.21.1) - both
            # have zero SUBSTRATE lines in KEGG's flat text. This is not
            # fixable by better parsing; there's nothing there to parse.
            #
            # Previously this raised and aborted before ever touching
            # BRENDA - but BRENDA still has real Km data for these
            # enzymes. Instead, proceed with an empty substrate list: name
            # matching can't succeed (nothing to match against), so this
            # falls straight through to the unfiltered/flagged fallback
            # tier below, which surfaces the real BRENDA data with
            # substrate_verified=False rather than hiding it entirely.
            target_substrates = []

    fallback_uniprot = enzyme_lookup.fetch_uniprot_accession(ec_number, taxon_id)
    html = fetch_brenda_html(ec_number)

    entries = parse_brenda_km_html(
        html, ec_number, target_substrates, target_organism, fallback_uniprot,
        table_label=table_label,
    )
    if entries:
        return entries

    if expand_synonyms:
        expanded_substrates = enzyme_lookup.expand_substrates_with_synonyms(
            target_substrates
        )
        entries = parse_brenda_km_html(
            html, ec_number, expanded_substrates, target_organism, fallback_uniprot,
            table_label=table_label,
        )
        if entries:
            return entries

    if allow_unverified_fallback:
        return parse_brenda_km_html(
            html,
            ec_number,
            target_substrates,
            target_organism,
            fallback_uniprot,
            require_substrate_match=False,
            table_label=table_label,
        )

    return []


def fetch_and_parse_brenda_kcat(
    ec_number: str,
    target_organism: str | None = "Homo sapiens",
    target_substrates: list | None = None,
    taxon_id: str = enzyme_lookup.DEFAULT_TAXON_ID,
    expand_synonyms: bool = True,
    allow_unverified_fallback: bool = True,
) -> list[BRENDAKmEntry]:
    """Orchestrator for turnover numbers: EC number in, kcat entries out.

    The kcat counterpart of ``fetch_and_parse_brenda_km``. Identical
    strategy -- KEGG substrate resolution, UniProt fallback accession, then
    the three-tier match (strict -> synonym-expanded -> unverified
    fallback) -- pointed at BRENDA's "Turnover Numbers" table instead of
    "KM Values".

    Implemented by delegation rather than duplication: the two differ only
    in which table is read and which plausibility bounds apply, and an
    80-line copy would drift the moment either strategy changed.

    ``km_value`` on the returned entries carries the kcat in **s^-1**, not
    mM -- the field name is inherited from the shared row model. Assay
    conditions travel with each entry, because STRENDA governs kcat exactly
    as it governs Km (ADR 0010).

    Note this returns literature values; it does NOT feed the simulation
    engine. Vmax = kcat * [E]0 needs an enzyme concentration Terrium does
    not have, so kcat is deliberately absent from RESOLVABLE_FIELDS.
    See ADR 0012.
    """
    return fetch_and_parse_brenda_km(
        ec_number=ec_number,
        target_organism=target_organism,
        target_substrates=target_substrates,
        taxon_id=taxon_id,
        expand_synonyms=expand_synonyms,
        allow_unverified_fallback=allow_unverified_fallback,
        table_label=TURNOVER_TABLE_LABEL,
    )


if __name__ == "__main__":
    import sys

    ec_numbers = sys.argv[1:] or ["1.1.1.27", "3.1.1.7"]
    for ec in ec_numbers:
        print(f"=== Human enzyme, EC {ec} ===")
        try:
            entries = fetch_and_parse_brenda_km(ec)
        except Exception as exc:  # noqa: BLE001 - surface any failure, don't crash the loop
            print(f"  ERROR: {exc}\n")
            continue
        for e in entries:
            flag = "  [FLAGGED]" if e.flagged else ""
            unverified = "  [UNVERIFIED SUBSTRATE]" if not e.substrate_verified else ""
            print(
                f"  Km={e.km_value} {e.unit} | substrate={e.substrate} | "
                f"uniprot={e.uniprot} | ref={e.reference_id}{flag}{unverified}"
            )
            if e.flag_reason:
                print(f"    flag_reason: {e.flag_reason}")
        flagged_count = sum(1 for e in entries if e.flagged)
        unverified_count = sum(1 for e in entries if not e.substrate_verified)
        print(
            f"\n  Total: {len(entries)} entries "
            f"({flagged_count} flagged, {unverified_count} substrate-unverified)\n"
        )
