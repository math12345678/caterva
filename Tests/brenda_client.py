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
Substring matching is fragile for exactly this reason. It was then made
permissive (case-insensitive substring), which over-matched instead:
"D-glucose" took 2-deoxy-D-glucose rows and "pyruvate" phenylpyruvate ones,
each relabelled with the target. Since 2026-11-11 the WHOLE compound cell is
compared (`substrate_matches`), ignoring case, spaces ("acetyl thiocholine")
and a counter-ion, and the organism is matched on the organism cell
(`organism_matches`), never as a substring of the row. Callers should still
pass every known spelling variant for a substrate name when they have one.
"""

from __future__ import annotations

import re
from typing import List

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

import enzyme_lookup
from effector import Effector, extract_effectors
from protein_variant import VariantVerdict, classify as classify_variant
from assay_conditions import parse_assay_conditions
from http_retry import retry_get


class BRENDAKmEntry(BaseModel):
    km_value: float
    unit: str = "mM"
    substrate: str
    organism: str
    uniprot: str | None = None
    #: True when `uniprot` is not the row's own cell but the caller's
    #: `fallback_uniprot` (UniProt's accession for the EC in the organism):
    #: a guess about the row, which says nothing about which isoform it
    #: measured. LDH's human pyruvate rows have no accession cell and were
    #: stamped P07864 (LDHC), and read as LDH-C rows (2026-11-12).
    uniprot_guessed: bool = False
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
    #: Cofactors and allosteric effectors named in the commentary, with
    #: their presence state. The same string that yields pH, temperature and
    #: buffer also says "in absence of fructose 1,6-bisphosphate", and that
    #: clause was discarded until ADR 0032.
    effectors: "list[Effector]" = Field(default_factory=list)
    #: Which protein this row measured: the enzyme, or a variant of it.
    #:
    #: The same commentary cell that yields pH and temperature also says
    #: "Y124C mutant" or "isozyme H4", and that half of it used to be
    #: discarded. See protein_variant.py and ADR 0029.
    variant: "VariantVerdict | None" = None
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

# kcat (turnover number), s^-1. Must match caterva/core/data_structures.py
# exactly -- ADR 0003 makes these a cross-layer contract, and
# scripts/check_plausibility_constants.py enforces the agreement.
#
# Anchored to Bar-Even et al. (2011), Biochemistry 50(21), 4402-4410
# (median kcat ~10 s^-1 across several thousand enzymes); catalase, the
# fastest known enzyme, is ~4e7 s^-1; the diffusion-limited ceiling is
# ~1e8-1e9 s^-1. Above that a number cannot be a turnover rate at all.
KCAT_PLAUSIBLE_MIN_PER_S = 0.000001
KCAT_PLAUSIBLE_MAX_PER_S = 1000000000

#: BRENDA's navigation label for the Michaelis constant table.
KM_TABLE_LABEL = "KM Values"

#: BRENDA's navigation label for the turnover-number table.
TURNOVER_TABLE_LABEL = "Turnover Numbers"

#: BRENDA's navigation label for the inhibition-constant table.
KI_TABLE_LABEL = "Ki Values"

BRENDA_ENZYME_URL = "https://www.brenda-enzymes.org/enzyme.php"


def fetch_brenda_html(ec_number: str, timeout: float = 15) -> str:
    """Fetch the raw HTML for a BRENDA enzyme page. The only network call
    in this module - keep it isolated so parsing stays testable offline.

    When CATERVA_BRENDA_RECORDED names a directory holding
    brenda_<ec>.html.gz, that recorded real page is returned instead (see
    Tests/fixtures/recorded/README.md). Only test configurations set it;
    an EC with no recording there is still fetched live.
    """
    import os
    recorded = os.environ.get("CATERVA_BRENDA_RECORDED")
    if recorded:
        import gzip
        from pathlib import Path
        page = Path(recorded) / f"brenda_{ec_number}.html.gz"
        if page.is_file():
            html = gzip.decompress(page.read_bytes()).decode("utf-8")
            _observed(ec_number, html, str(page))
            return html
    r = retry_get(BRENDA_ENZYME_URL, params={"ecno": ec_number}, timeout=timeout)
    r.raise_for_status()
    _observed(ec_number, r.text, None)
    return r.text


#: Observers called with (ec_number, html, served_from) after every page fetch_brenda_html
#: returns, live or recorded. The evidence layer registers one to pin what the resolver
#: read (ADR 0179). Nothing else reads this.
PAGE_OBSERVERS: list = []


def _observed(ec_number: str, html: str, served_from: str | None) -> None:
    """Tell each observer what was just fetched. An observer that raises stops
    the fetch: a page the evidence layer could not pin must not be used as
    though it had been, and nothing registers an observer unless it was asked
    to pin (`caterva compose --claims`)."""
    for observer in list(PAGE_OBSERVERS):  # noqa: PERF101 - a snapshot: a Recorder may deregister while a scout thread is notifying
        observer(ec_number, html, served_from)


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


def has_data_table(html: str, table_label: str) -> bool:
    """Whether this page actually carries the named table.

    WHY A CALLER WOULD NEED TO ASK
    ------------------------------
    `_find_table_container` returns None when the label is absent, and its
    docstring tells the caller to "fall back to whole-page scanning and
    treat results as less trustworthy". `parse_brenda_km_html` did exactly
    that until 2026-11-11; it now returns no rows when the page's navigation
    lists other tables but not this one (`_has_table_navigation`), and scans
    the whole page only when there is no navigation at all.

    The whole-page scan was not right for a caller running in permissive
    mode, where nothing filters, nor for the resolver: a Km row for the
    target substrate and organism read as a turnover number is still the
    wrong quantity. Measured: `parse_brenda_km_html(..., table_label="Ki Values",
    target_substrates=[], target_organism=None,
    require_substrate_match=False)` on an LDH page that has only a "KM
    Values" table returns 8 rows -- the Km table's -- and a caller that
    reports them as Ki data is describing measurements that do not exist.

    "This enzyme has no Ki table" is also a better answer than a corrected
    list would be: it diagnoses the QUANTITY rather than the substrate
    name, which is what the reader actually got wrong.
    """
    return _find_table_container(BeautifulSoup(html, "html.parser"), table_label) is not None


def _has_table_navigation(soup: BeautifulSoup) -> bool:
    """Whether this page carries BRENDA's table navigation at all.

    The distinction `parse_brenda_km_html` needs. A page WITH the navigation
    but without the label asked for is a page that has no such table: EC
    2.7.10.1 (receptor protein-tyrosine kinase) has no "Turnover Numbers"
    link, and the whole-page fallback scan then returned ~580 rows from the
    Km, IC50 and inhibitor tables as turnover numbers (measured 2026-11-11).
    A page WITHOUT any navigation is a cut-down fixture or an unfamiliar
    layout, where the whole-page scan is the only option and its rows are
    marked `table_scoped=False`."""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if isinstance(href, list):
            href = href[0] if href else ""
        if _SHOW_TABLE_HREF_PATTERN.search(str(href)):
            return True
    return False


#: What may follow the binomial in an organism cell and still be the same
#: organism as BRENDA names it: a strain, subspecies or variety ("Escherichia
#: coli K-12", "Brassica rapa subsp. oleifera"). Short, and none of the
#: punctuation a commentary is written with.
_ORGANISM_SUFFIX_MAX = 40
_NOT_AN_ORGANISM_SUFFIX = re.compile(r"[,;:°]|\bpH\b|\bmutant\b", re.IGNORECASE)


def organism_matches(cell: str, target: str) -> bool:
    """Whether one organism cell names the target organism.

    EXACT ON THE BINOMIAL, case-insensitive, at a word boundary. The parser
    used a substring test over the WHOLE ROW (`target in full_text`) and then
    relabelled the row with the target string. Two real failures came from
    that:

    - A partial name matched every row it was a prefix of. `--organism "Homo
      S"` was normalised to "Homo s", which is a substring of "Homo sapiens":
      all 159 human Km rows of hexokinase matched, and every report printed
      them as measured in "Homo s".
    - A name in the COMMENTARY matched too. "recombinant enzyme expressed in
      Escherichia coli" is in the commentary of human, yeast and plant rows
      alike, and a search for E. coli then carried those rows relabelled
      "Escherichia coli".

    A strain or subspecies suffix after the binomial still matches
    ("Escherichia coli K-12" for "Escherichia coli"), because that is the
    organism asked for, written more precisely. A one-word target (a genus,
    or "Mammalia") matches only a cell that is exactly that word: it is not
    a binomial, and a genus is not a species.
    """
    c = " ".join((cell or "").split())
    t = " ".join((target or "").split())
    if not c or not t:
        return False
    if c.lower() == t.lower():
        return True
    if len(t.split()) < 2 or not c.lower().startswith(t.lower()):
        return False
    rest = c[len(t):]
    if not rest[:1].isspace():
        # "Homo sapiens" for "Homo s": the target ends inside a word.
        return False
    rest = rest.strip()
    return len(rest) <= _ORGANISM_SUFFIX_MAX and not _NOT_AN_ORGANISM_SUFFIX.search(rest)


def _row_organism_cell(cell_texts: list, target_organism: str) -> str | None:
    """The row's organism cell, as BRENDA writes it, when it names the target.

    BRENDA's layout puts the organism in cell 2 (value | compound | organism
    | uniprot | commentary | reference). Some rows have no compound cell and
    put it in cell 1 (EC 3.1.1.7: "0.0146 | Homo sapiens | - | hemolysate").
    Cell 1 is read only when cell 2 is not itself an organism, so a compound
    whose name begins with an organism's cannot be mistaken for one. The
    commentary is never read for the organism: it names expression hosts
    and source organisms that are not the row's."""
    cells = [c.strip() for c in cell_texts]
    if len(cells) > 2 and organism_matches(cells[2], target_organism):
        return " ".join(cells[2].split())
    if len(cells) > 1 and organism_matches(cells[1], target_organism):
        if len(cells) <= 2 or not GENERIC_ORGANISM_PATTERN.fullmatch(cells[2]):
            return " ".join(cells[1].split())
    return None


#: Counter-ions BRENDA writes after a substrate's name. "acetylthiocholine
#: iodide" is acetylthiocholine as far as the enzyme is concerned.
_COUNTER_ION = re.compile(
    r"\s+(?:iodide|chloride|bromide|perchlorate|hydrochloride|sulfate|"
    r"(?:mono|di|tri)?sodium salt|potassium salt|lithium salt)$",
    re.IGNORECASE,
)
#: Stereo and anomer descriptors that may precede a name: "(S)-", "L-",
#: "DL-", "beta-D-", "(2R,3S)-".
_STEREO_PREFIX = re.compile(
    r"^(?:(?:\([0-9A-Za-z,+\-]+\)|[DL]{1,2}|alpha|beta|cis|trans|[αβ])-)+",
    re.IGNORECASE,
)


def _substrate_key(name: str) -> str:
    """A compound name compared: lower case, no whitespace, no counter-ion."""
    text = _COUNTER_ION.sub("", " ".join((name or "").split()))
    return re.sub(r"\s+", "", text).lower()


def substrate_matches(compound: str, target: str) -> bool:
    """Whether a row's compound cell is the target compound.

    Equal names match, ignoring case, spaces ("acetyl thiocholine") and a
    counter-ion ("acetylthiocholine iodide"). A stereo or anomer descriptor
    before the target matches only when the target carries none itself:
    "lactate" asks for no particular form, so "(S)-lactate" is a form of
    it; "D-glucose" does, so "beta-D-glucose" and "L-glucose" are not it.
    Nothing else matches: "2-deoxy-D-glucose" is not D-glucose and
    "phenylpyruvate" is not pyruvate, though each contains the other's name.
    """
    if not compound or not target:
        return False
    c, t = _substrate_key(compound), _substrate_key(target)
    if not t:
        return False
    if c == t:
        return True
    if _STEREO_PREFIX.match(t):
        return False
    prefix = _STEREO_PREFIX.match(c)
    return bool(prefix) and c[prefix.end():] == t


#: `_STEREO_PREFIX` without its start anchor, for finding a compound inside
#: running text rather than at the start of a cell.
_STEREO_RUN = r"(?:(?:\([0-9A-Za-z,+\-]+\)|[DL]{1,2}|alpha|beta|cis|trans|[αβ])-)+"


def substrate_named_in(text: str, target: str) -> str | None:
    """The target compound as `text` names it, or None when it names it
    only as part of another compound.

    For a row with no compound cell (EC 3.1.1.7 writes "0.0146 | Homo
    sapiens | - | hemolysate ..."), the whole row is the only text there is,
    and the match used to be a substring of it: a commentary reading "with
    2-deoxy-D-glucose as substrate" made the row a "D-glucose" row, and
    "phenylpyruvate" a "pyruvate" one -- the miscitation `substrate_matches`
    closed for rows WITH a compound cell, left open for rows without one
    (found in review, 2026-11-11). The same rules apply here as there: the
    name must stand as a whole word (not after a letter, digit or hyphen,
    not before one), spaces inside it are ignored ("acetyl thiocholine"),
    and a stereo descriptor before it is accepted only when the target
    carries none itself. The span returned is the text's own spelling, so a
    row matched through a descriptor is labelled "(S)-lactate", not
    "lactate"."""
    if not text or not target:
        return None
    t = _substrate_key(target)
    if not t:
        return None
    body = r"\s*".join(re.escape(ch) for ch in t)
    stereo = "" if _STEREO_PREFIX.match(t) else f"(?:{_STEREO_RUN})?"
    m = re.search(rf"(?<![\w\-]){stereo}{body}(?![\w\-])", text, re.IGNORECASE)
    return " ".join(m.group(0).split()) if m else None


#: A reference cell: one BRENDA reference id or several, comma-separated
#: ("697525,701131"). Group 1 is the first.
_REFERENCE_CELL = re.compile(r"(\d{1,7})(?:\s*,\s*\d{1,7})*")


def _reference_index(cell_texts: list) -> int | None:
    """The index of the row's reference cell: the last cell from index 3 on
    (after value, compound and organism) that is a reference id or a list of
    them.

    This was "the last cell of exactly six digits, anywhere", which failed
    two ways on the live carbonic anhydrase page (2026-11-11). BRENDA's older
    references have five digits ("33572"), so 27 human CO2 turnover rows came
    back with no reference at all; and a six-digit VALUE was taken for the
    reference when the real one was not six digits: "130000 | CO2 | Homo
    sapiens | - | - | 33536" was cited as BRENDA ref 130000, a reference that
    is not this row's. Index 0 is the value and is never read as one now."""
    for idx in range(len(cell_texts) - 1, 2, -1):
        if _REFERENCE_CELL.fullmatch(cell_texts[idx].strip()):
            return idx
    return None


def _compound_cell(cell_texts: list, target_organism: str | None) -> str | None:
    """The compound named by a data row: the first cell after the value that
    is not an organism, an accession, a placeholder or a bare number. None
    when the row has no such cell before its commentary would begin."""
    for cell in cell_texts[1:3]:
        c = cell.strip()
        if not c or c == "-":
            continue
        if GENERIC_ORGANISM_PATTERN.fullmatch(c) or (target_organism and c == target_organism):
            return None
        if UNIPROT_CELL_PATTERN.match(c) or re.match(r"^\d+\.?\d*$", c):
            continue
        return c
    return None


def parse_brenda_km_html(
    html: str,
    ec_number: str,
    target_substrates: list,
    target_organism: str | None = "Homo sapiens",
    fallback_uniprot: str | None = None,
    require_substrate_match: bool = True,
    table_label: str = KM_TABLE_LABEL,
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
    # Km and Ki are both concentrations in mM; kcat is a turnover number in
    # s^-1, so the Km range is meaningless for it -- a kcat of 6500 is
    # ordinary, a Km of 6500 mM is a unit error. Sharing the Km bounds
    # across all three would flag every fast enzyme.
    if table_label == TURNOVER_TABLE_LABEL:
        _quantity, _unit = "kcat", "1/s"
        _min_value, _max_value = KCAT_PLAUSIBLE_MIN_PER_S, KCAT_PLAUSIBLE_MAX_PER_S
    elif table_label == KI_TABLE_LABEL:
        _quantity, _unit = "Ki", "mM"
        _min_value, _max_value = KM_PLAUSIBLE_MIN_MM, KM_PLAUSIBLE_MAX_MM
    else:
        _quantity, _unit = "Km", "mM"
        _min_value, _max_value = KM_PLAUSIBLE_MIN_MM, KM_PLAUSIBLE_MAX_MM

    soup = BeautifulSoup(html, "lxml")

    km_table = _find_table_container(soup, table_label)
    if km_table is not None:
        search_root = km_table
        table_scoped = True
    elif _has_table_navigation(soup):
        # The page has BRENDA's table navigation and no link for this
        # table: the enzyme has no such table. Nothing from another table
        # may stand in for it. Before this returned, the whole-page scan
        # below ran here too, and EC 2.7.10.1 (no "Turnover Numbers" table)
        # gave ~580 "turnover numbers" read out of its Km, IC50 and
        # inhibitor tables.
        return []
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

        # A falsy target_organism is "any organism", exactly like None. An
        # empty string MUST NOT be treated as a filter: "" is a substring of
        # every row, so `if target_organism not in full_text` would match
        # everything, and then assigning `row_organism = target_organism`
        # would overwrite every row's real organism label with "" -- the
        # empty-organism call into `resolve_kinetic_value` returned a
        # cross-species minimum wearing a brenda_exact badge and no
        # organism. This is the organism twin of the documented "" substrate
        # pitfall below ("require_substrate_match = bool(substrate)").
        # Deeper rationale: ADR 0174.
        #
        # The match is on the row's ORGANISM CELL, exact on the binomial,
        # and the row keeps the organism as BRENDA wrote it
        # (`organism_matches`). This was `target_organism in full_text` and
        # `row_organism = target_organism`: "Homo s" matched every human
        # row and printed them as "Homo s", and a commentary reading
        # "expressed in Escherichia coli" made any organism's row an E. coli
        # one.
        if target_organism:
            row_organism = _row_organism_cell(cell_texts, target_organism)
            if row_organism is None:
                continue
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

        # Match the target against the row's COMPOUND cell, not the whole
        # row. The commentary names other molecules too: BRENDA's LDH Ki row
        # "0.00059 | 3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-
        # 4-yl]aminobenzoic acid | Homo sapiens | P00338 | competitive versus
        # NADH, ..." was matched on "NADH" in its commentary and relabelled
        # the Ki OF NADH. It is the Ki of the quinoline, measured against
        # NADH -- a different molecule and a different claim, and the
        # website then called it oxamate. Only a row with no identifiable
        # compound cell (organism in cell 1, as on EC 3.1.1.7) falls back to
        # the whole row, which is the only text it has.
        compound_cell = _compound_cell(cell_texts, row_organism)
        #
        # And against the WHOLE compound, not a substring of it. "D-glucose"
        # is a substring of "2-deoxy-D-glucose", "pyruvate" of
        # "phenylpyruvate": on the recorded hexokinase page a human
        # "D-glucose" Km pool held five 2-deoxy-D-glucose rows, and the
        # kcat pool sixteen beta-D-glucose rows and one 2-deoxy-D-glucose
        # row, every one labelled "D-glucose". A professor reading the
        # citation finds a different molecule. `substrate_matches` takes
        # the same compound spelled with or without spaces, a counter-ion
        # ("acetylthiocholine iodide"), and -- only when the target names
        # no stereochemistry itself -- a stereo descriptor ("(S)-lactate"
        # for "lactate"); a row matched that last way keeps BRENDA's own
        # name, so the label says which form it measured. A row with no
        # compound cell still falls back to the whole row, the only text
        # it has.
        matched_substrate = None
        if compound_cell is not None:
            for sub in target_substrates:
                if substrate_matches(compound_cell, sub):
                    matched_substrate = (
                        sub if _substrate_key(compound_cell) == _substrate_key(sub)
                        else compound_cell
                    )
                    break
        else:
            # No compound cell: the row's text is all there is, and the
            # compound must stand in it as a whole name, by the same rules
            # (`substrate_named_in`). This was `sub.lower() in full_text`,
            # which still read "2-deoxy-D-glucose" in a commentary as
            # D-glucose.
            for sub in target_substrates:
                named = substrate_named_in(full_text, sub)
                if named is not None:
                    matched_substrate = (
                        sub if _substrate_key(named) == _substrate_key(sub) else named
                    )
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
                    if cell_clean == row_organism:
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
        uniprot_guessed = uniprot is None and fallback_uniprot is not None
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
            ref_index = _reference_index(cell_texts)
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

        _ref_at = _reference_index(cell_texts)
        ref_id = (
            _REFERENCE_CELL.fullmatch(cell_texts[_ref_at].strip()).group(1)
            if _ref_at is not None else None
        )

        flagged = False
        flag_reason = None
        scope_note = (
            f"row is inside BRENDA's actual {table_label} table"
            if table_scoped
            else f"row-selection could not confirm this came from the {table_label} table "
                 "specifically (whole-page fallback scan) - this may genuinely be a "
                 "different kind of value (Km/Ki/Turnover Number/IC50)"
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
                # `_unit`, not a hardcoded "mM". This read `unit="mM"`
                # unconditionally, while `_unit` -- correctly derived above
                # as "1/s" for the Turnover Numbers table and "mM" for
                # Km/Ki -- reached only the plausibility-flag message.
                #
                # So every kcat parsed from BRENDA was labelled a
                # millimolar concentration: the real AChE turnover number
                # 6500 s^-1 was emitted as `6500 mM`. The wrong unit then
                # travelled through KineticResult.unit and
                # science_agent_runner.py into the API response, and any
                # downstream unit check reading `.unit` was structurally
                # incapable of failing because the field was a constant.
                unit=_unit,
                substrate=matched_substrate,
                organism=row_organism,
                uniprot=uniprot,
                uniprot_guessed=uniprot_guessed,
                conditions=conditions,
                assay_ph=parsed_conditions.ph,
                assay_temperature_c=parsed_conditions.temperature_c,
                assay_buffer=parsed_conditions.buffer,
                assay_unreported=parsed_conditions.explicitly_unreported,
                variant=classify_variant(conditions),
                # Extraction only. Identity resolution needs PubChem and is
                # done by the runner, so parsing a fixture stays offline.
                effectors=extract_effectors(conditions),
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


def parse_brenda_ki_html(
    html: str,
    ec_number: str,
    target_substrates: list,
    target_organism: str | None = "Homo sapiens",
    fallback_uniprot: str | None = None,
    require_substrate_match: bool = True,
) -> list[BRENDAKmEntry]:
    """Parse BRENDA's "Ki Values" table into structured entries.

    Ki (the inhibition constant) is a concentration in mM, and BRENDA
    serves the Ki table with the same six-cell row layout as KM Values
    (value, substrate, organism, uniprot, commentary, reference id) --
    confirmed live 2026-08 against the LDH page (1.1.1.27, "Ki Values"
    nav tab): the rows are identical in shape to Km rows, including the
    same aggregate "N entries" summary rows (whose range in cell 1 the
    numeric matcher already skips) and the same free-text commentary
    carrying pH and temperature. The only structural difference is a
    seventh icon cell on the aggregate rows, which the cell-position
    logic ignores.

    So this delegates to the Km parser with a different table label and
    the same mM plausibility bounds, rather than duplicating ~250 lines
    of row-scoping, aggregate expansion and assay-condition logic that
    would then drift out of sync.

    ``km_value`` on the returned entries carries the Ki in mM. The field
    name is inherited from the shared row model; the quantity is Ki.

    STRENDA governs Ki exactly as it governs Km (ADR 0010): an inhibition
    constant measured at an unreported pH or temperature cannot be
    reproduced or compared, so assay conditions are parsed here too and
    travel with the value.
    """
    return parse_brenda_km_html(
        html=html,
        ec_number=ec_number,
        target_substrates=target_substrates,
        target_organism=target_organism,
        fallback_uniprot=fallback_uniprot,
        require_substrate_match=require_substrate_match,
        table_label=KI_TABLE_LABEL,
    )


def fetch_and_parse_brenda_km(
    ec_number: str,
    target_organism: str | None = "Homo sapiens",
    target_substrates: list | None = None,
    taxon_id: str | None = None,
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

    # `taxon_id` used to default to 9606 (Homo sapiens) independently of
    # `target_organism`. Two defaults for one fact, and they could disagree:
    # a caller passing target_organism="Thermus aquaticus" and omitting
    # taxon_id got a thermophile's rows stamped with the human accession.
    #
    # The organism is now the single source of truth and the taxon is
    # derived from it. When it cannot be derived there is NO fallback
    # accession -- rows carry uniprot=None, which is true, rather than a
    # confident accession for a species nobody asked about.
    if taxon_id is None and target_organism:
        try:
            taxon_id = enzyme_lookup.fetch_taxon_id(target_organism)
        except Exception:
            taxon_id = None

    fallback_uniprot = (
        enzyme_lookup.fetch_uniprot_accession(ec_number, taxon_id)
        if taxon_id
        else None
    )
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
    taxon_id: str | None = None,
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
    engine. Vmax = kcat * [E]0 needs an enzyme concentration Caterva does
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


def fetch_and_parse_brenda_ki(
    ec_number: str,
    target_organism: str | None = "Homo sapiens",
    target_substrates: list | None = None,
    taxon_id: str | None = None,
    expand_synonyms: bool = True,
    allow_unverified_fallback: bool = True,
) -> list[BRENDAKmEntry]:
    """Orchestrator for inhibition constants: EC number in, Ki entries out.

    The Ki counterpart of ``fetch_and_parse_brenda_km``. Identical
    strategy -- KEGG substrate resolution, UniProt fallback accession, then
    the three-tier match (strict -> synonym-expanded -> unverified
    fallback) -- pointed at BRENDA's "Ki Values" table instead of
    "KM Values". Ki is the inhibition constant for the same enzyme, and
    the substrate filter matters just as much here: BRENDA's Ki table
    lists every compound anyone has ever tested as an inhibitor, most of
    which are drug-screening noise rather than the enzyme's real
    substrate. Filtering to the substrate name(s) keeps the "what does it
    bind" signal.

    ``km_value`` on the returned entries carries the Ki in **mM** -- the
    field name is inherited from the shared row model. Assay conditions
    travel with each entry, because STRENDA governs Ki exactly as it
    governs Km (ADR 0010).

    Unlike kcat (excluded per ADR 0012), Ki IS resolvable in the product:
    competitive-inhibition simulations need a real inhibition constant,
    so this feeds RESOLVABLE_FIELDS.mm_competitive_inhibition via
    quantity="ki" (fallback_logic.py -> science_agent_runner.py).
    """
    return fetch_and_parse_brenda_km(
        ec_number=ec_number,
        target_organism=target_organism,
        target_substrates=target_substrates,
        taxon_id=taxon_id,
        expand_synonyms=expand_synonyms,
        allow_unverified_fallback=allow_unverified_fallback,
        table_label=KI_TABLE_LABEL,
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
