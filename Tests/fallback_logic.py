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
import enzyme_preparation
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
    TURNOVER_TABLE_LABEL,
    fetch_brenda_html,
    has_data_table,
    parse_brenda_km_html,
)
from citation import Citation, citation_from_brenda_entry, pubmed_url
from effector import Effector
from effector_presence import EffectorContrast, find_contrasts
from form_mixture import (
    FormMixture,
    SelectedForm,
    find_form_mixtures,
    name_selected_form,
)
from source_context import (
    OrganismDiscrepancy,
    SourceCheckUnavailable,
    SourceMixture,
    find_organism_discrepancies,
    find_source_mixtures,
    source_check_status,
)
import evidence_rank
from protein_variant import VariantVerdict
from enzyme_preparation import PreparationVerdict
from selection_tie import SelectionTie, TiedCandidate, find_tie
from taxonomy import (
    Lineage,
    Relatedness,
    assess_relatedness,
    fetch_taxon_lineage_xml,
    parse_taxon_lineage,
)

PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

# Which BRENDA table a quantity resolves from. Km and Ki are both
# concentrations in mM served by their own table ("KM Values" / "Ki
# Values"); the mapping is what lets one resolution chain serve both.
#
# "kcat" resolves the same way (BRENDA "Turnover Numbers" table, same
# three-tier match, same STRENDA assay-condition capture) but is
# deliberately NOT reachable through RESOLVABLE_FIELDS / the simulation
# engine -- ADR 0012 found Vmax = kcat * [E]0 needs a caller-supplied
# enzyme concentration Caterva has no source for, and ADR 0013 declined to
# default or infer it. Exposing quantity="kcat" here makes a real,
# citable turnover number resolvable and displayable (e.g. for a student
# comparing catalytic efficiency across enzymes) without pretending it can
# feed a simulation on its own -- see ADR 0019 for the still-open question
# of how a caller-supplied [E]0 combines with this into a provenance chain
# a simulation could actually use.
QUANTITY_TABLE_LABELS = {
    "km": KM_TABLE_LABEL,
    "ki": KI_TABLE_LABEL,
    "kcat": TURNOVER_TABLE_LABEL,
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


class MechanismEvidence(BaseModel):
    """A row that is evidence against the model's mechanism, for the Ki
    returned (`caterva.compose.ki_mode.evidence_against`).

    BRENDA ref 739793 gives human LDH and one quinoline sulfonamide 0.00059
    mM "competitive versus NADH" and 0.00252 mM "noncompetitive versus
    pyruvate". A competitive model of pyruvate gets the first, correctly:
    it is the only row stating the model's mode. The second says that,
    measured against pyruvate, the inhibitor is not competitive. `caterva
    compose` says so in its report's notes; the API and the TypeScript CLI,
    which choose the same row by the same ranking, said nothing, so a reader
    of either was handed the competitive constant with the one row that
    contradicts the model left out of view.

    The fields are the contradicting row's, as BRENDA gives it, and the
    model's mode and substrate, which it contradicts, as the caller gave
    them.
    Everything a sentence needs, so neither front end has to re-derive any
    of it (ADR 0027); the decision is made once, in Python.
    """
    #: The row's value, in `unit`, as BRENDA lists it.
    value: float
    unit: str | None = None
    organism: str | None = None
    #: The BRENDA reference the row cites.
    reference_id: str | None = None
    #: The mode the row states ("noncompetitive"), read by
    #: caterva.bind.core, as `rowScope.inhibitionMode` is read.
    inhibition_mode: str
    #: What the row was measured versus, in the row's words ("pyruvate").
    versus: str
    #: The row's commentary, verbatim, so the reader can check the words.
    conditions: str | None = None
    #: The mode of the model the Ki was asked for ("competitive").
    model_mode: str
    #: The model's substrate, as the caller named it.
    model_substrate: str


class KineticResult(BaseModel):
    found: bool
    value: float | None = None
    unit: str | None = None
    organism: str | None = None
    source: str  # "brenda_exact" | "brenda_cross_species" | "cross_species_withheld"
                 # | "cross_species_too_distant" | "variant_withheld" | "isoform_withheld"
                 # | "mode_withheld" | "literature_candidates" | "not_found"
    citation: Citation | None = None
    cross_species_flag: bool = False

    #: Per-organism relatedness verdicts, populated when cross-species use
    #: was opted into. Every candidate organism appears here, whether it
    #: passed or failed -- a filter that only reports what survived it is
    #: unauditable, and the organisms it silently dropped are exactly the
    #: ones a reader would want to argue with.
    relatedness: list[Relatedness] = []

    #: Organisms that DO have a value for this (enzyme, substrate, quantity)
    #: when the requested organism does not, and cross-species use was not
    #: opted into. Populated only for source="cross_species_withheld".
    #:
    #: This exists so a refusal can say what it refused. "Not found" and
    #: "found, in a rabbit, and you did not ask for rabbit data" are
    #: different facts, and collapsing them into one would make the miss
    #: unactionable -- the student cannot opt in to something they were
    #: never told existed.
    cross_species_organisms_available: list[str] = []

    #: Every cross-species row WITH its value, when the requested organism
    #: had none.
    #:
    #: WHY THE VALUES AND NOT JUST THE NAMES
    #: -------------------------------------
    #: Herbert Sauro, asked whether to default a missing value or refuse,
    #: replied:
    #:
    #:     I thought you'd decided to build an ensemble when values are
    #:     unknown?
    #:
    #: That dissolves the question rather than answering it. Defaulting to
    #: 0.5 invents a number; refusing gives a student nothing; substituting
    #: a rabbit Km presents one organism's measurement as another's, which
    #: is what Jeske objected to. Running the model at EVERY organism's
    #: measured value is none of the three.
    #:
    #: `cross_species_organisms_available` already named the organisms, and
    #: `broad` — the rows those names came from — carried the values and
    #: was discarded. The refusal knew the numbers and threw them away.
    #:
    #: Shaped as `TiedCandidate` deliberately, so `spread_consequence`
    #: consumes these unchanged (ADR 0111). One ensemble mechanism, two
    #: sources of candidates; a second one would be a second place the
    #: reasoning could drift.
    cross_species_candidates: "list[TiedCandidate]" = []

    #: Variant descriptors ("Y124C", "isozyme H4") for rows that WERE found
    #: and were withheld because they measure a variant rather than the
    #: enzyme. Populated only for source="variant_withheld".
    #:
    #: Same reasoning as cross_species_organisms_available: a refusal that
    #: cannot say what it refused leaves the user unable to exercise the
    #: opt-in it just demanded of them.
    variant_candidates_available: list[str] = []

    #: The isoforms BRENDA's rows measured, when an isoform was asked for
    #: and no row measured it or named none. Populated only for
    #: source="isoform_withheld". A constant of another isoform is another
    #: protein's, so it is refused rather than returned; the refusal names
    #: what exists so the caller can ask for one of those instead.
    isoforms_available: list[str] = []

    #: What BRENDA's rows state, one clause per distinct statement
    #: ("competitive inhibition versus NADH"), when a Ki was asked for by
    #: the model's inhibition mode and every row states another. Populated
    #: only for source="mode_withheld". Each is a constant of a different
    #: mechanism, so none is returned in place of the model's; naming them
    #: tells the caller what does exist, and that the gap is the mechanism,
    #: not the literature.
    modes_available: list[str] = []

    #: A row that is evidence against the mechanism of the model a Ki was
    #: asked for: it states another inhibition mode, measured versus the
    #: model's substrate, while the row returned does not state the model's
    #: mode versus it. Set only on a found Ki asked for with
    #: `inhibition_mode` and `model_substrate`, and None when no row the
    #: mode step ranked is one. Found in `_mechanism_evidence` by
    #: `caterva compose`'s own function (caterva.compose.ki_mode's
    #: `evidence_against`), so compose's report and the API and CLI say it
    #: by one rule.
    mechanism_evidence: "MechanismEvidence | None" = None

    #: Cofactors and effectors reported for the row that WON selection,
    #: with presence state and PubChem identity where resolvable.
    #:
    #: Carried on found results because "in absence of X" is a deliberate
    #: experimental statement, and a reader who sees no effector field would
    #: reasonably assume none was reported -- which is a different fact.
    effectors: "list[Effector]" = []

    #: Set when the evidence ranked several rows equal and a tie-break chose
    #: among them (ADR 0048).
    #:
    #: On the LDH turnover table six non-dominated rows span 21.1 to 6467 --
    #: a 306-fold range, every one wild-type with pH and temperature
    #: reported. `min()` returns 21.1 and nothing else says that the
    #: evidence found 6467 equally credible.
    #:
    #: None means no tie was found, which is different from an empty tie:
    #: see `SelectionTie.is_tied`.
    selection_tie: "SelectionTie | None" = None
    #: The chosen row's BRENDA commentary, verbatim ("competitive versus
    #: NADH, pH 7.5, 37 C", "LDH-B, pH not specified ..."). It says which
    #: isoform and, for a Ki, which inhibition mode the value measured, and
    #: a caller building a model with one mechanism needs both.
    commentary: str | None = None

    #: Every row on the non-dominated frontier, with the reliability score
    #: each was graded by -- Bakker's weights, before they are sampled.
    #:
    #: WHY THE SCORES ARE HERE AND NOT RECOMPUTED LATER
    #: ------------------------------------------------
    #: `science_agent_runner` grades exactly one value: the winner. That is
    #: all a single-value answer needs, and it is why the scoring shipped
    #: while the sampling did not -- there was never a per-candidate score
    #: for the sampling to weight anything with.
    #:
    #: The rows carry `assay_ph`, `assay_temperature_c`, `assay_unreported`
    #: and `organism`, which is exactly what `score_reliability` reads. They
    #: exist only inside the selection function; rebuilding them downstream
    #: would mean resolving the same query twice.
    #:
    #: The candidate DICTS below keep the winner's whole pool, so a caller
    #: that holds a KineticResult has everything needed to re-select among
    #: the rows by assay condition (the agent architecture's `assay_window`
    #: constraint) without re-parsing BRENDA. Each dict therefore carries
    #: `ph` and `temperature_c` as well as the raw `conditions` string,
    #: both taken from the same parsed entry that graded the row.
    #:
    #: Empty when nothing was resolved. An empty list is "no ensemble to
    #: draw", which the caller must report as a resolution failure rather
    #: than as a band with no members.
    ensemble_candidates: list = []

    #: What this call would have returned had it not been asked for an
    #: isoform or an inhibition mode: the row the evidence alone chooses,
    #: FIRST, then the rest of that evidence frontier, as the dicts
    #: `ensemble_candidates` holds. Set on found results when `isoform`, or
    #: `inhibition_mode` for a Ki, was applied; empty otherwise, and empty
    #: when that call would have returned nothing (every row a variant).
    #:
    #: WHY A SECOND ANSWER RIDES ON THE FIRST
    #: --------------------------------------
    #: `caterva compose` asks this resolver for each constant with the
    #: model's isoform and mode, so the isoform and the mode are ranked
    #: before the evidence frontier, over every row, and compose carries the
    #: same row the API and the TypeScript CLI get. Until 2026-09-30 compose
    #: asked without them and chose among `ensemble_candidates` afterwards,
    #: and the two could disagree: Trypanosoma cruzi hexokinase and ADP,
    #: competitive model, 1.3 mM (a row stating no mode, alone on the
    #: frontier) in compose and 1.5 mM ("competitive to ATP") here.
    #:
    #: Compose's report says which row the choice replaced and why ("the
    #: resolver's pick (0.00059 mM) measured competitive inhibition ..."),
    #: and whether a row of another mode, measured against the model's own
    #: substrate, is evidence against the model's mechanism. Both need the
    #: rows this call set aside, which `ensemble_candidates`, the frontier
    #: of what was kept, no longer holds. Asking twice would fetch and parse
    #: BRENDA's page twice (the monoamine oxidase page takes about two
    #: seconds to parse, per call); these rows are already here.
    #:
    #: Not emitted by the runner: the API and the TypeScript CLI say what the
    #: returned row measured (`rowScope`) and never show an answer the
    #: resolver was not asked for (docs/undelivered-fields-baseline.txt).
    evidence_only: list = []

    #: Set when the value returned IS one of the named forms the pool mixed.
    #:
    #: `FormMixture.reason` warns that "returning the lowest would pick a
    #: form rather than answer the question" -- conditionally, without saying
    #: whether it did. This says whether it did.
    #:
    #: None in every fixture today: the pipeline selects rows carrying no
    #: designator. That is luck rather than design, and it is pinned by
    #: `test_no_named_form_is_selected_today_and_that_is_the_finding`.
    selected_form: "SelectedForm | None" = None

    #: The variant verdict for the row that WON selection.
    #:
    #: Carried on found results, not only withheld ones. `unstated` is the
    #: majority case in BRENDA and it is not the same as wild-type -- a
    #: reader who sees no variant field at all would reasonably assume the
    #: row was the enzyme as found, which is the assumption this whole
    #: mechanism exists to stop being made silently.
    variant: "VariantVerdict | None" = None

    #: How the enzyme was PREPARED for the row that won selection --
    #: immobilised, affinity-tagged, covalently modified, native, or
    #: unstated.
    #:
    #: ADR 0029 removes rows measuring a protein VARIANT. None of these is a
    #: sequence change, so that filter cannot see them, and BRENDA records
    #: all of them in the same commentary cell.
    #:
    #: Carried as a FIELD, not a log line. `provenance.flags` is what the
    #: CLI and web UI render; the resolver's diagnostic log is not, and
    #: queryResolver.ts records four ADRs whose findings "reached only the
    #: logs, which is the same as reaching nobody". The first version of
    #: this change appended to the log and would have been the fifth.
    preparation: "PreparationVerdict | None" = None

    #: Compounds the candidate pool measured BOTH with and without.
    #:
    #: Populated on FOUND results, not withheld ones -- the point is that a
    #: value was returned while its counterpart existed unmentioned. In the
    #: LDH turnover table one paper reports 21.1 with fructose
    #: 1,6-bisphosphate and 327.2 without it, and `min()` takes the first.
    #:
    #: Reported rather than blocking: separating "allosteric effector someone
    #: added" from "cosubstrate the reaction requires" is a claim about the
    #: enzyme's mechanism that Caterva has no source for. See ADR 0032.
    effector_contrasts: "list[EffectorContrast]" = []

    #: Bases the candidate pool named with more than one form designator.
    #:
    #: The LDH turnover pool holds LDHB (142-350), LDH-1 (1500-1600) and
    #: LDH-2 (1300-1800); `min()` returns 142 and calls it the turnover
    #: number of lactate dehydrogenase. Detected without knowing what LDH
    #: stands for -- see ADR 0035.
    form_mixtures: "list[FormMixture]" = []

    #: Rows whose commentary names a different organism than their column.
    #:
    #: Three AChE rows carry organism="Drosophila melanogaster" while the
    #: commentary says the enzyme came from human and from eel. ADR 0024's
    #: cross-species gate reads the column, so those rows pass it as
    #: Drosophila measurements. See ADR 0037.
    organism_discrepancies: "list[OrganismDiscrepancy]" = []

    #: One organism measured from several biological sources in one pool.
    #:
    #: Gallus gallus LDH: heart 60.0, muscle 1.1-3.3. A factor of 54 that the
    #: organism gate cannot see, because every row IS the organism asked for.
    source_mixtures: "list[SourceMixture]" = []

    #: Substrate labels this EC number's table DOES carry, when the
    #: requested one matched nothing.
    #:
    #: Measured: `substrate="lactate"` resolves to 10.73 and
    #: `substrate="L-lactate"` returns not_found, because BRENDA's label is
    #: `(S)-lactate` — "lactate" matches as a substring and "L-lactate"
    #: does not. Without this the student is told the literature has
    #: nothing, which is false, and has no way to discover the string that
    #: would work.
    #:
    #: The same courtesy ADR 0024 extends to organisms, which a student is
    #: far LESS likely to get wrong: an organism has one binomial name, a
    #: metabolite has a dozen aliases.
    #:
    #: Empty on found results — computing it costs a second parse of the
    #: table and nobody needs it when the answer arrived.
    substrates_available: list[str] = []

    #: Set when source tokens were extracted and NONE could be classified.
    #:
    #: Without it, `source_mixtures == []` means both "the pool was clean"
    #: and "the classifier could not reach NCBI". Found by running the real
    #: resolution path with the network blocked: a pool holding heart 60.0
    #: and muscle 3.3 reported nothing at all. See ADR 0039.
    source_check_unavailable: "SourceCheckUnavailable | None" = None

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

#: organism name -> its NCBI lineage, or None when it cannot be resolved.
#: Injectable for the same reason every other provider here is: the test
#: suite must exercise the relatedness policy without a network.
LineageProvider = Callable[[str], "Lineage | None"]


def default_lineage_provider(
    organism: str,
    taxon_id_provider: TaxonIdProvider = enzyme_lookup.fetch_taxon_id,
) -> Lineage | None:
    """Resolve an organism name to an NCBI lineage. None on any failure.

    Returning None rather than raising is deliberate, and it is safe here
    only because None means "unknown", and taxonomy.assess_relatedness
    treats "unknown" as a refusal rather than a pass. If that ever changed,
    swallowing the error here would silently convert every network blip
    into permission to substitute a thermophile's enzyme for a human one.
    """
    try:
        taxon_id = taxon_id_provider(organism)
        if not taxon_id:
            return None
        return parse_taxon_lineage(fetch_taxon_lineage_xml(taxon_id))
    except (httpx.HTTPError, ValueError):
        return None


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


def substrates_present(
    ec_number: str,
    html_provider: HtmlProvider,
    table_label: str = KM_TABLE_LABEL,
) -> list[str]:
    """Every substrate label this EC number's table actually carries.

    WHY THIS EXISTS
    ---------------
    Measured through the real resolver, on the LDH fixture:

        substrate="lactate"    -> found, 10.73
        substrate="L-lactate"  -> found=False, source="not_found"

    Both name the same compound. `fallback_logic` passes
    `target_substrates=[substrate]` -- the one string the user typed -- so a
    reasonable synonym returns nothing, and a student reasonably concludes
    BRENDA has no data for this enzyme. The data is right there under a
    different string.

    ADR 0024 already solved the same problem for ORGANISMS: a withheld
    cross-species result names which organisms held values, "so the opt-in
    can actually be exercised". Nobody applied it to substrates, which is
    the field a student is far more likely to get wrong -- an organism has
    one binomial name, a metabolite has a dozen aliases.

    WHY NOT SYNONYM EXPANSION
    -------------------------
    `enzyme_lookup.expand_substrates_with_synonyms` exists and is called by
    nothing but its own test. It could have been wired here, and
    deliberately was not:

    * it costs a PubChem request per name, on the hot path of every lookup;
    * PubChem synonyms are not substrate identity. "lactate" and "lactic
      acid" are the same compound; a synonym list can also carry a salt, a
      stereoisomer or a related ester, and silently matching one of those
      returns a measurement of a DIFFERENT MOLECULE under the name the
      student asked for. That is ADR 0024's cross-species error wearing
      another costume, and this project refuses the substitution rather
      than making it quietly.

    So: no network, no guessing, no substitution. The table is already
    fetched and already parsed; this reports what is in it and lets the
    reader choose. A list of real labels is more useful than a guessed
    match and cannot be wrong.
    """
    html = html_provider(ec_number)

    # THE TABLE HAS TO BE THE ONE ASKED ABOUT.
    #
    # `parse_brenda_km_html` falls back to scanning the whole page when the
    # labelled container is missing, which is safe for the resolver -- a
    # target substrate and organism filter the foreign rows out -- and not
    # safe here, where nothing filters. Measured on the LDH fixture, which
    # carries a "KM Values" table and no "Ki Values" table: asking for the
    # Ki table returned the Km table's eight rows, so a student asking for
    # a Ki was told the enzyme "reports" four substrates that have no Ki
    # data at all. They re-run, fail again, and now believe Ki data exists.
    #
    # Shipped in ADR 0118 and found the next day while building on it.
    if not has_data_table(html, table_label):
        return []

    entries = parse_brenda_km_html(
        html,
        ec_number,
        # No substrate filter, and no organism filter: the question is what
        # this ENZYME has data for, which is what a reader needs in order to
        # ask again. `require_substrate_match=False` is the permissive mode
        # that already exists for rows whose compound name does not match a
        # requested one -- exactly the rows wanted here.
        target_substrates=[],
        target_organism=None,
        require_substrate_match=False,
        table_label=table_label,
    )
    labels = {
        (getattr(entry, "substrate", None) or "").strip()
        for entry in entries
    }
    return sorted(label for label in labels if label)


def _nothing_matched(
    ec_number: str,
    substrate: str,
    html_provider,
    table_label: str,
    log: list,
) -> list:
    """The substrates this enzyme does have, for a refusal that teaches.

    Guarded so the list is only built when it can help: if the requested
    substrate IS one of the labels present, the miss was about the organism
    or the quantity and naming the substrate list would point a reader at
    the wrong thing entirely -- the cry-wolf shape ADR 0028 describes,
    where a suggestion that fires on the wrong case gets ignored on the
    right one.

    Never raises. This runs on a path that has already failed, and a
    diagnostic that turns a "no value found" into a stack trace has made
    things worse.
    """
    try:
        if not has_data_table(html_provider(ec_number), table_label):
            # A better diagnosis than any substrate list: the reader got the
            # QUANTITY wrong, not the substrate name, and telling them about
            # substrates would send them round the same loop.
            log.append(
                f"BRENDA's page for {ec_number} carries no {table_label!r} "
                "table at all, so no substrate has a value of this kind here. "
                "The substrate name is not what went wrong."
            )
            return []
        available = substrates_present(ec_number, html_provider, table_label)
    except Exception as exc:  # noqa: BLE001 - a hint, never a new failure
        log.append(f"Could not list the substrates present: {exc}")
        return []

    asked = (substrate or "").strip().lower()
    if any(asked == label.lower() for label in available):
        return []

    if available:
        log.append(
            f"No {substrate!r} row, but this EC number reports: "
            + ", ".join(available)
            + ". Caterva does not substitute one substrate for another, so "
            "re-run with the name you meant."
        )
    return available


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
    if quantity == "ki":
        quantity_term = "inhibition constant"
    elif quantity == "kcat":
        quantity_term = "turnover number kcat"
    else:
        quantity_term = "Km kinetics"
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


def _best_evidenced(
    entries, log, tier, requested_organism=None, relatedness_by_organism=None,
    quantity=None,
):
    """Narrow to the non-dominated rows, then take the minimum of those.

    Bakker's advice was to let reliability drive the choice. Until now the
    score was computed, emitted, displayed -- and ignored here, where the
    only decision that consumes it is made. Selection was
    `min(key=km_value)`: take the smallest number.

    That is not neutral. A poorly-described measurement is more likely to
    sit in the tail, and a minimum seeks the tail. On human LDH it discarded
    the pool's only STRENDA-complete row (0.045, pH 7.4 and 37 C) for one
    where BRENDA reported no commentary whatsoever (0.03).

    Dominance needs no weights: a row is dropped only when another beats it
    on EVERY axis. Among what survives, `min()` remains, and remains
    arbitrary -- see ADR 0047. The arbitrariness is now confined to rows
    that no other row beats outright.
    """
    if len(entries) < 2:
        _report_preparation(entries[0], log, tier, quantity)
        # One row is its own frontier. Returned as a list of one rather
        # than empty: an ensemble over a single measurement is a
        # legitimate (if narrow) ensemble, and an empty list here would
        # read downstream as 'nothing was resolved'.
        return entries[0], None, list(entries)
    kept = evidence_rank.frontier(
        entries, requested_organism, relatedness_by_organism
    )
    for line in evidence_rank.describe_discards(
        entries, kept, requested_organism, relatedness_by_organism
    ):
        log.append(f"{tier}: {line}")
    if len(kept) < len(entries):
        log.append(
            f"{tier}: {len(kept)} of {len(entries)} row(s) are non-dominated; "
            "choosing the lowest value among those"
        )
    chosen = min(kept, key=lambda e: e.km_value)
    _report_preparation(chosen, log, tier, quantity)
    # The tie is computed HERE, where `kept` exists, and returned alongside
    # the row. Recomputing it at the call site would need the frontier
    # again, and a second frontier is a second implementation.
    #
    # THE FRONTIER ITSELF IS RETURNED TOO, for the same reason and one step
    # further. Bakker's ensemble needs a reliability score for EVERY
    # surviving row, not just the winner, and those rows carry the assay pH,
    # temperature and organism that `score_reliability` grades on. They exist
    # only here; by the time the caller has a KineticResult they have been
    # collapsed to one value and a list of bare TiedCandidates with no assay
    # fields.
    #
    # So the ensemble could not be built downstream without re-parsing
    # BRENDA, which would be a second resolution of the same query -- the
    # duplicate-source-of-truth defect that this comment's first paragraph
    # already refuses one level up.
    return chosen, find_tie(kept, chosen), list(kept)


def _score_frontier(
    frontier,
    requested_organism,
    physiological=None,
    relatedness_by_organism=None,
) -> list:
    """Grade every surviving row, so the ensemble has weights to sample by.

    ONE IMPLEMENTATION, NOT TWO. These use `score_reliability` -- the same
    function that grades the winner on its way to the API response. A second
    grader for candidates would be ADR 0027 exactly: two implementations of
    one score, drifting until somebody notices they disagree.

    Returns plain dicts rather than `ensemble.Candidate` objects. The
    literature layer must not import the ensemble module to produce its own
    output: that would make the resolver depend on the sampler, when the
    real relationship is the other way round.
    """
    import reliability

    scored = []
    for entry in frontier or []:
        value = getattr(entry, "km_value", None)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        measured = getattr(entry, "organism", None)
        verdict = None
        if relatedness_by_organism and measured:
            verdict = relatedness_by_organism.get(measured)
        score = reliability.score_reliability(
            ph=getattr(entry, "assay_ph", None),
            temperature_c=getattr(entry, "assay_temperature_c", None),
            unreported=list(getattr(entry, "assay_unreported", []) or []),
            reference=physiological,
            requested_organism=requested_organism,
            measured_organism=measured,
            cross_species=bool(
                requested_organism and measured and requested_organism != measured
            ),
            relatedness=verdict,
        )
        scored.append({
            "value": float(value),
            "unit": getattr(entry, "unit", None),
            "organism": measured,
            "reference_id": getattr(entry, "reference_id", None),
            "conditions": getattr(entry, "conditions", None),
            # The row's assay conditions, as PARSED by the existing
            # condition parser (`_parse_ph` / `_parse_temperature` /
            # `AssayConditions`) when the entry was built -- the same values
            # `score_reliability` grades with, one field above. Carried so a
            # caller can re-select among these rows against a reference
            # window without re-parsing BRENDA, which would be a second
            # implementation of one parse.
            "ph": getattr(entry, "assay_ph", None),
            "temperature_c": getattr(entry, "assay_temperature_c", None),
            "buffer": getattr(entry, "assay_buffer", None),
            "grades": {
                "assay_completeness": score.assay_completeness.grade,
                "condition_proximity": score.condition_proximity.grade,
                "organism_match": score.organism_match.grade,
            },
        })
    return scored


def _evidence_only(pool, allow_variants, tier, organism, quantity,
                   relatedness_by_organism=None) -> list:
    """`KineticResult.evidence_only`: the frontier the call without `isoform`
    and `inhibition_mode` would choose from, its choice first.

    The same steps that call takes, on the same rows: variants removed as it
    removes them (keep_isozymes=False: with no isoform asked, an isozyme row
    is a variant), then `_best_evidenced`. Its log lines are discarded, since
    they describe a choice this call did not make, and the frontier is
    scored as `ensemble_candidates` is scored."""
    rows = list(pool)
    if not allow_variants:
        rows, _ = _partition_variants(rows)
    if not rows:
        return []
    best, _, frontier = _best_evidenced(rows, [], tier, organism, relatedness_by_organism,
                                        quantity=quantity)
    return _score_frontier([best] + [e for e in frontier if e is not best], organism)


def _preparation_of(entry) -> "PreparationVerdict":
    """One place the verdict is derived, so the field and the log agree.

    Deriving it twice -- once for the log line, once for the field -- is two
    implementations of one fact, which is ADR 0027 exactly.
    """
    return getattr(entry, "preparation", None) or enzyme_preparation.classify(
        getattr(entry, "conditions", None)
    )


def _report_preparation(entry, log, tier, quantity=None) -> None:
    """Say when the chosen row measured a preparation, not the free enzyme.

    ADR 0029 removes rows measuring a protein VARIANT. It cannot see a
    covalent modification, an affinity tag or an immobilised enzyme, because
    none of those is a sequence change -- and BRENDA records all three in
    the same commentary cell.

    Measured before this existed: `resolve_kinetic_value("1.1.1.27",
    "Homo sapiens", "NADH", quantity="ki")` returned **0.00059**, whose
    commentary reads "competitive versus NADH, pH 7.5, 37 C, recombinant
    His-tagged enzyme". The search log said only "BRENDA exact", the
    citation carried `notes=None`, and no flag mentioned the tag. A tagged
    construct's inhibition constant was served as the human enzyme's.

    Reporting only. Whether to EXCLUDE these by default, as ADR 0029 does
    for variants, is a policy question with a real cost on both sides and is
    left open in ADR 0090 rather than decided here -- silently narrowing
    what a student can resolve is the kind of change that should be argued
    for, not slipped in beside a logging fix.
    """
    verdict = _preparation_of(entry)
    sentence = enzyme_preparation.describe(verdict, quantity)
    if sentence:
        log.append(f"{tier}: {sentence}")


def _isoform_of(conditions):
    """The isoform a row's commentary names, read by caterva.bind.core (the
    parser `caterva bind` and `caterva compose --isoform` use). Raises
    ImportError where the caterva package is not importable."""
    from caterva.bind.core import read_isoform
    return read_isoform(conditions)


def _same_isoform(a, b):
    """Whether two isoform names name one isoform, by caterva.bind.core's
    `same_isoform`: the comparison `caterva compose --isoform` and `caterva
    bind --isoform` use. This held its own copy until 2026-09-30; the copies
    agreed only while nothing changed either. Raises ImportError where the
    caterva package is not importable, as `_isoform_of` does, and is only
    reached after `_isoform_of` has succeeded."""
    from caterva.bind.core import same_isoform
    return same_isoform(a, b)


def _partition_isoform(entries, isoform, log, where):
    """`(rows, matched, refused_isoforms)` for a request for one isoform.

    Rows naming the isoform win. Failing those, rows naming no isoform are
    kept (whether they measured it is unknown, and the log says so). Failing
    those too, every row measured another isoform: `rows` is empty and
    `refused_isoforms` names what exists. The same three cases, in the same
    order, as `caterva compose --isoform` (caterva/compose/isoform.py).
    """
    try:
        named = [(e, _isoform_of(e.conditions)) for e in entries]
    except ImportError:
        log.append(f"isoform {isoform!r} asked for, but caterva's isoform reader is not "
                   f"importable here, so {where} rows were NOT filtered by isoform")
        return entries, False, []
    matching = [e for e, iso in named if _same_isoform(iso, isoform)]
    if matching:
        log.append(f"Kept the {len(matching)} of {len(entries)} {where} row(s) measuring {isoform}")
        return matching, True, []
    unnamed = [e for e, iso in named if iso is None]
    if unnamed:
        log.append(f"No {where} row names {isoform}; kept the {len(unnamed)} naming no isoform, "
                   f"which may or may not have measured it")
        return unnamed, False, []
    return [], False, sorted({iso for _, iso in named if iso})


def _isoform_withheld_result(isoform, available, log):
    log.append(f"Every candidate row measured another isoform ({', '.join(available)}), "
               f"not {isoform}: a constant of another isoform is a different protein's")
    return KineticResult(
        found=False,
        source="isoform_withheld",
        isoforms_available=available,
        search_log=log,
    )


def _ki_mode():
    """caterva.compose.ki_mode, where the one ranking of Ki rows by inhibition
    mode lives (`caterva compose` chooses with it too). Imported lazily, as
    `_isoform_of` imports caterva.bind.core. Raises ImportError where the
    caterva package is not importable."""
    from caterva.compose import ki_mode
    return ki_mode


def _mode_asked(inhibition_mode, quantity, log):
    """The inhibition mode to rank Ki rows for, or None when there is none.

    A mode says which Ki row is the model's constant. It has no bearing on a
    Km or a kcat, so for those it is not applied, and the log says so rather
    than letting the caller believe a Km was chosen by it. A mode that is not
    one a model can be of ("mixed", "", "Competitive") is refused with
    ValueError, whatever the quantity: ranking for "mixed" would silently
    mean something no model here is, and a caller sending one with a Km has
    the same mistake in hand, found one lookup later if it is only logged.
    """
    if inhibition_mode is None:
        return None
    try:
        modes = _ki_mode().MODES
    except ImportError:
        modes = None  # for a Ki, _partition_mode says it could not rank
    if modes is not None and inhibition_mode not in modes:
        raise ValueError(f"inhibition_mode must be one of {', '.join(modes)}; "
                         f"got {inhibition_mode!r}")
    if quantity != "ki":
        log.append(f"inhibition mode {inhibition_mode!r} not applied: it chooses among Ki "
                   f"rows, and this is a {quantity} lookup")
        return None
    return inhibition_mode


def _naming_no_isoform(pool, isoform_matched, allow_variants):
    """Rows of `pool` that name no isoform, when the isoform step kept only
    rows naming the one asked for; else none.

    Compose, told the isoform, ranks a row naming it before a row naming
    none, and still takes a row naming none when every row naming the
    isoform states another mode (ki_mode's docstring, "With --isoform").
    `_partition_isoform` has already set those rows aside, so they are put
    back here as candidates behind the isoform's own, with variants removed
    exactly as the variant step would have removed them.

    Removed with keep_isozymes=False, where the rows naming the isoform went
    through the variant step with keep_isozymes=True. That is deliberate.
    An isozyme row is kept there because it names the isoform asked for, so
    it is that protein and not a variant of it. A row here names no isoform
    that `_isoform_of` can read, so if `protein_variant` still calls it an
    isozyme, it names one in words the isoform reader does not take, and
    which one is unknown. On BRENDA's IMPDH page (1.1.1.205, fetched
    2026-09-29, not committed) ref 701583 gives human IMPDH and mizoribine
    monophosphate 0.0039 mM "type 2 isozyme" and 0.0082 mM "type 1
    isozyme": `_isoform_of` reads neither, and `protein_variant` calls both
    isozymes. Kept here, a request for IMPDH2 could take the type 1
    isozyme's constant as a row "naming no isoform". False is also what the
    variant step itself uses when the isoform step keeps the rows naming
    none (isoform_matched False), so these rows are treated the same way
    whichever route brings them in.
    """
    if not isoform_matched:
        return []
    try:
        unnamed = [e for e in pool if _isoform_of(e.conditions) is None]
    except ImportError:
        return []
    if not allow_variants:
        unnamed, _ = _partition_variants(unnamed)
    return unnamed


def _partition_mode(entries, mode, substrate, isoform, isoform_matched, log, where):
    """`(rows, stated)` for a Ki asked for by the model's inhibition mode.

    WHY THE POOL IS NARROWED
    ------------------------
    BRENDA ref 739793 gives human LDH two Ki values for one quinoline
    sulfonamide, from one paper, under one set of conditions: 0.00059 mM
    "competitive versus NADH" and 0.00252 mM "noncompetitive versus
    pyruvate". They are constants of two mechanisms, the evidence grades
    them alike, and selection takes the lower. Every caller got the
    competitive constant, a noncompetitive model's included, and was told
    only which mode the row measured (the runner's `rowScope`).

    WHOSE RULE
    ----------
    `caterva compose`'s. Each row is ranked by `caterva.compose.ki_mode.rank`,
    told the isoform: a row naming the isoform before one naming none; then a
    row of the model's mode (a mixed row counts for noncompetitive), measured
    versus the model's substrate first, then naming nothing, then versus
    another molecule; then a row stating no mode; a Kitz-Wilson row
    (an irreversible inactivation constant filed as a Ki) last; a row of
    another mode or naming another isoform never. The rows sharing the best
    rank are kept and the ordinary choice among them follows. When no row is
    a candidate, `rows` is empty and `stated` lists what the rows state.

    WHERE THIS RUNS, AND WHY BEFORE THE FRONTIER
    --------------------------------------------
    Before a row is chosen, over every row the isoform and variant steps
    left, so a row of the model's mode that another row dominates on evidence
    is still a candidate. Trypanosoma cruzi hexokinase and ADP, on the
    recorded page (Tests/fixtures/recorded/brenda_2.7.1.1.html.gz), is such a
    case: 0.13 mM (no commentary), 1.3 mM ("natural hexokinase from
    epimastigotes, at pH 7.5"), 1.5 mM ("competitive to ATP") and 7.0 mM
    ("noncompetitive to glucose"). The evidence frontier keeps 1.3 alone, the
    one row with a pH; asked for competitive, this returns 1.5.

    Until 2026-09-30 `caterva compose` applied the same rule AFTER this
    resolver, to the frontier of an answer it had asked for without a mode,
    and so carried 1.3 for a competitive model where the API returned 1.5.
    Compose now asks with the model's isoform, mode and substrate
    (ParameterRequest), and carries the row this returns; its selections
    only say what the choice did, against the row the evidence alone would
    take (`KineticResult.evidence_only`, caterva/compose/narrowed.py).
    Rows ranked alike are chosen among by the evidence frontier and then the
    lowest value.

    TWO ORDERS AROUND IT
    --------------------
    - Variant rows are removed before this, not after. A mode step run
      first could keep only variant rows of the model's mode and have the
      variant step refuse the constant while wild-type rows stating no mode
      sat in the pool, which is a worse answer than asking for no mode at
      all. None of the 766 Ki rows parsed from the three committed BRENDA
      pages (LDH and monoamine oxidase in Tests/fixtures/ki_mode/, hexokinase
      in Tests/fixtures/recorded/) is a variant row stating a mode, so no
      real case has decided the order; it is the one that cannot make the
      answer worse than no mode.
    - The isoform step kept only rows naming the isoform, when any did. The
      rows naming none come back here from `_naming_no_isoform`, behind the
      isoform's own, so the isoform-then-mode order is compose's.
    """
    try:
        ki_mode = _ki_mode()
    except ImportError:
        log.append(f"inhibition mode {mode!r} asked for, but caterva's Ki ranking is not "
                   f"importable here, so {where} rows were NOT chosen by mode")
        return entries, []
    readings = [ki_mode.read_row(e.conditions) for e in entries]
    ranks = [ki_mode.rank(r, mode, substrate, isoform) for r in readings]
    candidates = [k for k in ranks if k is not None]
    if not candidates:
        # What the rows that could have been taken state. A row naming
        # another isoform is not among them: it was never a candidate, and
        # the isoform step has already said what it measured.
        stated = []
        for reading in readings:
            said = reading.says()
            if ki_mode.isoform_rank(reading, isoform) is not None and said not in stated:
                stated.append(said)
        return [], stated
    best = min(candidates)
    rows = [e for e, k in zip(entries, ranks) if k == best]
    iso, fits, versus, inexact = best
    # WHICH ROWS A SENTENCE SPEAKS OF. When the isoform step kept rows
    # naming the isoform, `entries` also holds the rows naming none that
    # `_naming_no_isoform` put back behind them. A sentence about every
    # `where` row would then count rows the isoform step's own line ("Kept
    # the K of M rows measuring X") did not, and could deny a row that is
    # in the pool: the rows measuring the isoform can state no mode while a
    # row naming none states the model's, and the isoform's rows still rank
    # first. Gossypol's LDH-A row (0.0019 mM, no mode) and the quinoline
    # sulfonamide's "competitive versus NADH" row, which names no isoform,
    # ranked together for a competitive LDH-A model (two real rows from one
    # page, put in one pool by test_ki_mode_resolution, since no real pool
    # has this shape), were logged as "No exact-match row states
    # competitive inhibition". So the count and the denial are
    # of the rows sharing the kept rows' isoform rank, and a row of the
    # other group that ranks before them on mode alone is named as passed
    # over, with why.
    if isoform_matched:
        scope = f" measuring {isoform}" if iso == 0 else " naming no isoform"
        size = sum(1 for r in readings if ki_mode.isoform_rank(r, isoform) == iso)
    else:
        scope, size = "", len(entries)
    kept = f"the {len(rows)} of {size} {where} row(s){scope + ',' if scope else ''}"
    if fits == 0:
        against = {
            0: f" versus {substrate}, the model's substrate",
            1: "",
            2: f", measured versus another molecule than {substrate}, the model's substrate",
        }[versus]
        sentence = f"Kept {kept} stating {'mixed' if inexact else mode} inhibition{against}"
        if inexact:
            sentence += " (a mixed row counts for a noncompetitive model)"
    elif fits == 1:
        sentence = (f"No {where} row{scope} states {mode} inhibition; kept {kept} stating no "
                    f"mode, so whether the value is the {mode} constant is unknown")
    else:
        # Worded as the Kitz-Wilson rows' own commentary words it (ref
        # 702238, "determined from Kitz-Wilson plots"), with what that
        # makes the number.
        sentence = (f"No {where} row{scope} states {mode} inhibition or is a reversible "
                    f"constant stating no mode; kept {kept} stating no mode and determined "
                    f"from Kitz-Wilson plots, which give the K_I of an irreversible "
                    f"inactivation, not a reversible Ki")
    passed = []
    for reading, k in zip(readings, ranks):
        if k is not None and k[0] > iso and k[1:] < best[1:] and reading.says() not in passed:
            passed.append(reading.says())
    if passed:
        # Only rows naming no isoform rank below the isoform's own, so
        # this arises only when the kept rows measured the isoform.
        sentence += (f"; {where} row(s) naming no isoform and stating {'; '.join(passed)} "
                     f"were passed over, because a row measuring {isoform} is taken before "
                     f"one that may not have measured it, as caterva compose takes it")
    if iso == 1 and isoform_matched:
        sentence += (f"; no row measuring {isoform} could be used for a {mode} model, so these "
                     f"name no isoform and whether they measured {isoform} is unknown")
    log.append(sentence)
    return rows, []


def _mode_withheld_result(mode, stated, log):
    log.append(f"Every candidate row states an inhibition mode other than {mode} "
               f"({'; '.join(stated)}): each is a constant of another mechanism than the "
               f"{mode} one asked for, so none is returned")
    return KineticResult(
        found=False,
        source="mode_withheld",
        modes_available=stated,
        search_log=log,
    )


def _mechanism_evidence(ranked, carried, mode, substrate, isoform, log):
    """A row of `ranked` that is evidence against the model's mechanism for
    `carried`, the row returned, as a MechanismEvidence; or None.

    WHY THIS IS HERE AND NOT IN THE RUNNER
    --------------------------------------
    The row the finding names is, by construction, one the mode step does
    not keep: it states another mode, so `_partition_mode` ranks it None and
    it is in neither the returned row, the tie, nor `ensemble_candidates`.
    Only this module holds it, so the finding is made here and carried on
    the result, and the runner emits it. The rule is not this module's:
    `caterva.compose.ki_mode.evidence_against` decides, as it decides for
    `caterva compose`'s report, and its sentence goes in the log.

    WHICH ROWS
    ----------
    `ranked` is what `_partition_mode` ranked: the rows the isoform and
    variant steps kept, and behind them the rows naming no isoform that
    `_naming_no_isoform` put back. Compose checks the resolver's ranked
    alternatives in the pick's unit; BRENDA's Ki table is in mM throughout,
    so the unit restriction removes nothing here, and a row's unit is
    carried with it regardless. In the cross-species tier the rows can be
    of several related organisms, as compose's alternatives can, and the
    organism is carried so the reader sees whose row it is.

    With no model substrate there is nothing to be measured against, and
    where caterva is not importable `_partition_mode` has already logged
    that nothing was chosen by mode; both give None.
    """
    if not substrate:
        return None
    try:
        ki_mode = _ki_mode()
    except ImportError:
        return None
    readings = [ki_mode.read_row(e.conditions) for e in ranked]
    reading = next((r for e, r in zip(ranked, readings) if e is carried), None)
    if reading is None:
        reading = ki_mode.read_row(carried.conditions)
    against = ki_mode.evidence_against(reading, readings, mode, substrate, isoform)
    if against is None:
        return None
    row = next(e for e, r in zip(ranked, readings) if r is against)
    sentence = ki_mode.evidence_against_sentence(
        against, ki_mode.row_label(row.km_value, row.unit, row.reference_id),
        reading, ki_mode.row_label(carried.km_value, carried.unit, carried.reference_id),
        mode, substrate)
    log.append(sentence[0].upper() + sentence[1:])
    return MechanismEvidence(
        value=row.km_value,
        unit=row.unit,
        organism=row.organism,
        reference_id=row.reference_id,
        inhibition_mode=against.mode,
        versus=against.versus,
        conditions=row.conditions,
        model_mode=mode,
        model_substrate=substrate,
    )


def _partition_variants(entries, keep_isozymes=False):
    """`(usable, withheld)` — rows measuring the enzyme, and rows measuring
    a variant of it.

    `unstated` rows are USABLE. They are the majority of the corpus, BRENDA
    does not require curators to write "wild-type" when the paper measured
    wild-type, and withholding them would refuse most of the literature over
    an absence of words. That is a deliberate asymmetry: this filter removes
    rows that SAY they are variants, and claims nothing about the rest.

    Stated plainly because it is the limit of the check. An unlabelled
    mutant still passes, and the fix for that is better BRENDA commentary,
    not a more aggressive regex here.
    """
    usable, withheld = [], []
    for entry in entries:
        verdict = getattr(entry, "variant", None)
        if (verdict is not None and verdict.status == "variant"
                and not (keep_isozymes and verdict.kind == "isozyme")):
            # An isozyme row is kept when it is the isozyme that was asked
            # for: then it is the enzyme, not a variant of it.
            withheld.append(entry)
        else:
            usable.append(entry)
    return usable, withheld


def _variant_withheld_result(withheld, log):
    """Every candidate measured a variant. Say which, and of what kind."""
    described = sorted(
        {
            (e.variant.evidence or e.variant.kind or "unnamed variant")
            for e in withheld
            if e.variant is not None
        }
    )
    log.append(
        f"All {len(withheld)} candidate row(s) measured a protein variant "
        f"({', '.join(described) or 'unnamed'}); withheld: allow_variants=False"
    )
    return KineticResult(
        found=False,
        source="variant_withheld",
        variant_candidates_available=described,
        search_log=log,
    )


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
    allow_cross_species: bool = False,
    allow_variants: bool = False,
    lineage_provider: LineageProvider | None = None,
    isoform: str | None = None,
    inhibition_mode: str | None = None,
    model_substrate: str | None = None,
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

    ``inhibition_mode`` ("competitive", "noncompetitive", "uncompetitive")
    is the mechanism of the model a Ki is for, and ``model_substrate`` that
    model's substrate (``substrate`` is the inhibitor, for a Ki: BRENDA files
    a Ki under it). With a mode, the Ki rows are narrowed before a row is
    chosen, by the ranking `caterva compose` uses
    (caterva.compose.ki_mode.rank), and a Ki every row of which states
    another mode is refused, source "mode_withheld", naming what they state
    (`_partition_mode`). Order: isoform, then variants, then mode.
    """
    table_label = QUANTITY_TABLE_LABELS.get(quantity, KM_TABLE_LABEL)
    quantity_upper = {"ki": "Ki", "kcat": "kcat"}.get(quantity, "Km")
    log = []
    mode = _mode_asked(inhibition_mode, quantity, log)
    model_substrate = model_substrate or None

    log.append(f"BRENDA exact: {enzyme_ec}, {organism}, {substrate} ({quantity})")
    exact = _brenda_entries(
        enzyme_ec, organism, substrate, html_provider, uniprot_provider,
        taxon_id_provider, table_label=table_label,
    )
    if exact:
        # An isoform asked for narrows the pool first, for the same reason
        # variants are removed before selection: min() over three isoforms'
        # rows picks a protein, not a value.
        pool = exact
        isoform_matched = False
        if isoform:
            exact, isoform_matched, other_isoforms = _partition_isoform(exact, isoform, log, "exact-match")
            if not exact:
                return _isoform_withheld_result(isoform, other_isoforms, log)
        # Variant rows are removed BEFORE selection, not flagged after it.
        #
        # That ordering is the whole point. Selection is min(), point
        # substitutions are chosen precisely because they change the
        # kinetics, and they therefore sit in the tail a minimum reaches
        # into: in the AChE turnover fixture the lowest mutant kcat is
        # twelve times below the lowest wild-type one. Flagging afterwards
        # would attach a warning to a value that had already been selected
        # FOR being a mutant. See ADR 0029.
        if not allow_variants:
            usable, withheld = _partition_variants(exact, keep_isozymes=isoform_matched)
            if withheld:
                log.append(
                    f"Excluded {len(withheld)} of {len(exact)} exact-match "
                    "row(s) measuring a protein variant"
                )
            if not usable:
                return _variant_withheld_result(withheld, log)
            exact = usable
        # A Ki asked for by mode: the rows compose's ranking puts first for
        # that model, before min() takes the lower of two mechanisms'
        # constants.
        ranked = []
        if mode:
            ranked = exact + _naming_no_isoform(pool, isoform_matched, allow_variants)
            exact, stated = _partition_mode(
                ranked, mode, model_substrate, isoform, isoform_matched, log, "exact-match")
            if not exact:
                return _mode_withheld_result(mode, stated, log)
        # Detect designed contrasts BEFORE reporting a winner. A value
        # returned while the other arm of its own experiment sits unmentioned
        # in the same pool is half an answer, and the reader cannot ask for
        # the other half without being told it exists.
        contrasts = find_contrasts([(e.km_value, e.conditions) for e in exact])
        mixtures = find_form_mixtures([(e.km_value, e.conditions) for e in exact])
        source_rows = [(e.km_value, e.organism, e.conditions) for e in exact]
        discrepancies = find_organism_discrepancies(source_rows)
        source_mix = find_source_mixtures(source_rows)
        source_unavailable = source_check_status(source_rows)
        if source_unavailable:
            log.append(source_unavailable.reason)
        if discrepancies:
            log.append(
                f"{len(discrepancies)} row(s) whose commentary names a different "
                "organism than the organism column"
            )
        if source_mix:
            log.append(
                f"{len(source_mix)} organism(s) measured from several biological "
                "sources: "
                + "; ".join(
                    f"{m.organism} ({', '.join(m.values_by_source)})" for m in source_mix
                )
            )
        if mixtures:
            log.append(
                f"{len(mixtures)} pool(s) mixing named enzyme forms: "
                + "; ".join(
                    f"{m.base} ({', '.join(m.values_by_form)})" for m in mixtures
                )
            )
        if contrasts:
            log.append(
                f"{len(contrasts)} presence/absence contrast(s) in the candidate pool: "
                + "; ".join(c.compound for c in contrasts)
            )
        best, tie, frontier = _best_evidenced(
            exact, log, "exact match", organism, quantity=quantity
        )
        # After the choice, because whether a row contradicts the model
        # depends on what the row returned states (ki_mode.evidence_against).
        evidence = (_mechanism_evidence(ranked, best, mode, model_substrate, isoform, log)
                    if mode else None)
        return KineticResult(
            found=True,
            value=best.km_value,
            unit=best.unit,
            organism=best.organism,
            source="brenda_exact",
            evidence_only=(_evidence_only(pool, allow_variants, "exact match", organism, quantity)
                           if isoform or mode else []),
            mechanism_evidence=evidence,
            effector_contrasts=contrasts,
            form_mixtures=mixtures,
            organism_discrepancies=discrepancies,
            source_mixtures=source_mix,
            source_check_unavailable=source_unavailable,
            variant=best.variant,
            preparation=_preparation_of(best),
            selection_tie=tie,
            # No physiological reference at this layer -- it is a runner
            # input, supplied per request, and the resolver never sees it.
            # So `condition_proximity` grades `not_assessed` for every row,
            # which is the honest state and costs the weighting nothing: an
            # axis where every candidate scores alike cannot discriminate,
            # and cancels under normalisation (see ensemble.py).
            ensemble_candidates=_score_frontier(frontier, organism),
            selected_form=name_selected_form(mixtures, best.km_value),
            effectors=list(best.effectors),
            citation=citation_from_brenda_entry(best),
            assay_ph=best.assay_ph,
            assay_temperature_c=best.assay_temperature_c,
            assay_buffer=best.assay_buffer,
            assay_unreported=list(best.assay_unreported),
            commentary=best.conditions,
            search_log=log,
        )

    log.append(f"BRENDA any organism: {enzyme_ec}, {substrate} ({quantity})")
    broad = _brenda_entries(
        enzyme_ec, None, substrate, html_provider, uniprot_provider,
        taxon_id_provider, table_label=table_label,
    )

    # Cross-species use is OPT-IN, and off by default.
    #
    # This tier used to fire automatically: no human Km, so return the
    # rabbit one with cross_species_flag=True and a warning. Lisa Jeske of
    # the BRENDA curation team (DSMZ) was asked directly whether that is
    # the right behaviour for a tool consuming BRENDA at scale, and said
    # it is not:
    #
    #   "Enzyme kinetics are species-specific ... Transferring a value
    #    from one species to another is not recommended from a
    #    biochemical standpoint. ... The simulation should rather abort or
    #    leave the value empty if there is no exact organism match,
    #    instead of providing incorrect data. ... the student/teacher must
    #    actively check a box ('Allow cross-species data'), accompanied by
    #    a clear educational warning that this is an inaccurate model."
    #
    # A warning attached to a returned value is read by whoever is looking
    # for a reason to doubt the number. A student reading a result screen
    # is not that person. Requiring the opt-in moves the decision to
    # before the number exists, which is the only point at which it is
    # actually a decision.
    #
    # The withheld case still reports WHICH organisms had data, because a
    # refusal that cannot say what it refused leaves the user no way to
    # exercise the opt-in it just demanded of them.
    #
    # This is deliberately narrower than ADR 0018 as originally written;
    # see ADR 0024 for the full argument, including Herbert Sauro's
    # opposite recommendation and why the teaching case resolves it this
    # way.
    if broad and not allow_cross_species:
        organisms = sorted({e.organism for e in broad if e.organism})
        log.append(
            f"Cross-species value(s) found in {', '.join(organisms) or 'unnamed organism(s)'} "
            f"but withheld: allow_cross_species=False"
        )
        return KineticResult(
            found=False,
            source="cross_species_withheld",
            cross_species_organisms_available=organisms,
            # The numbers, not only the names. Every one is a real
            # measurement with a reference; none of them is a measurement
            # of the organism that was asked about, and nothing here says
            # otherwise.
            cross_species_candidates=[
                TiedCandidate(
                    value=float(e.km_value),
                    unit=getattr(e, "unit", None),
                    organism=e.organism,
                    reference_id=getattr(e, "reference_id", None),
                    conditions=getattr(e, "conditions", None),
                    selected=False,
                )
                for e in broad
                # PRECAUTIONARY, AND UNEXERCISED. `TiedCandidate.value` is
                # a required float, so a row with no value would raise a
                # ValidationError here rather than produce a bad candidate.
                # Measured: all 8 rows in the LDH fixture carry a value, so
                # no test exercises this filter and mutating it away breaks
                # nothing. Said out loud rather than left to look tested —
                # a guard nobody can fail is worth keeping and not worth
                # believing in.
                if getattr(e, "km_value", None) is not None
            ],
            search_log=log,
        )

    if broad:
        # THE OPT-IN IS NOT THE WHOLE CHECK.
        #
        # Jeske gave three recommendations, not one. The opt-in above is
        # the second. This is the third:
        #
        #   "The software should at least check whether the organisms are
        #    closely related enough (e.g., two different mammals instead of
        #    a bacterium and a human)."
        #
        # Without it, ticking the box buys a Plasmodium falciparum Ki as a
        # stand-in for a mouse -- which is the real content of golden tuple
        # G5, not a hypothetical. A checkbox that grants unlimited
        # substitution is a checkbox that makes the user complicit in a
        # decision they had no information about.
        #
        # Candidates whose relatedness cannot be RESOLVED are dropped too.
        # See taxonomy.assess_relatedness: "unknown" is a third state, and
        # it does not permit.
        provider = lineage_provider or default_lineage_provider
        query_lineage = provider(organism) if organism else None

        verdicts: list[Relatedness] = []
        acceptable = []
        for entry in broad:
            verdict = assess_relatedness(
                query_lineage,
                provider(entry.organism) if entry.organism else None,
                query_name=organism,
                candidate_name=entry.organism,
            )
            verdicts.append(verdict)
            if verdict.permits_transfer:
                acceptable.append(entry)

        for verdict in verdicts:
            log.append(
                f"Relatedness {verdict.candidate_organism} -> "
                f"{verdict.query_organism}: {verdict.status}"
                + (f" (shared {verdict.shared_rank} {verdict.shared_name})"
                   if verdict.shared_rank else "")
            )

        if not acceptable:
            log.append(
                "Every cross-species candidate failed the relatedness check; "
                "nothing returned"
            )
            return KineticResult(
                found=False,
                source="cross_species_too_distant",
                cross_species_organisms_available=sorted(
                    {e.organism for e in broad if e.organism}
                ),
                relatedness=verdicts,
                search_log=log,
            )

        pool = acceptable
        isoform_matched = False
        if isoform:
            acceptable, isoform_matched, other_isoforms = _partition_isoform(
                acceptable, isoform, log, "cross-species")
            if not acceptable:
                return _isoform_withheld_result(isoform, other_isoforms, log)
        if not allow_variants:
            usable, withheld = _partition_variants(acceptable, keep_isozymes=isoform_matched)
            if withheld:
                log.append(
                    f"Excluded {len(withheld)} of {len(acceptable)} "
                    "cross-species row(s) measuring a protein variant"
                )
            if not usable:
                return _variant_withheld_result(withheld, log)
            acceptable = usable
        ranked = []
        if mode:
            ranked = acceptable + _naming_no_isoform(pool, isoform_matched, allow_variants)
            acceptable, stated = _partition_mode(
                ranked, mode, model_substrate, isoform, isoform_matched, log, "cross-species")
            if not acceptable:
                return _mode_withheld_result(mode, stated, log)

        # Detect designed contrasts BEFORE reporting a winner. A value
        # returned while the other arm of its own experiment sits unmentioned
        # in the same pool is half an answer, and the reader cannot ask for
        # the other half without being told it exists.
        contrasts = find_contrasts([(e.km_value, e.conditions) for e in acceptable])
        mixtures = find_form_mixtures([(e.km_value, e.conditions) for e in acceptable])
        source_rows = [(e.km_value, e.organism, e.conditions) for e in acceptable]
        discrepancies = find_organism_discrepancies(source_rows)
        source_mix = find_source_mixtures(source_rows)
        source_unavailable = source_check_status(source_rows)
        if source_unavailable:
            log.append(source_unavailable.reason)
        if discrepancies:
            log.append(
                f"{len(discrepancies)} row(s) whose commentary names a different "
                "organism than the organism column"
            )
        if source_mix:
            log.append(
                f"{len(source_mix)} organism(s) measured from several biological "
                "sources: "
                + "; ".join(
                    f"{m.organism} ({', '.join(m.values_by_source)})" for m in source_mix
                )
            )
        if mixtures:
            log.append(
                f"{len(mixtures)} pool(s) mixing named enzyme forms: "
                + "; ".join(
                    f"{m.base} ({', '.join(m.values_by_form)})" for m in mixtures
                )
            )
        if contrasts:
            log.append(
                f"{len(contrasts)} presence/absence contrast(s) in the candidate pool: "
                + "; ".join(c.compound for c in contrasts)
            )
        best, tie, frontier = _best_evidenced(
            acceptable,
            log,
            "cross-species",
            organism,
            # The gate above already computed a verdict per candidate
            # organism. Passing them here is what turns "close enough?"
            # into "which of these is closest?" -- see ADR 0024 and the
            # relatedness_depth axis in evidence_rank.
            {v.candidate_organism: v for v in verdicts},
            quantity=quantity,
        )
        evidence = (_mechanism_evidence(ranked, best, mode, model_substrate, isoform, log)
                    if mode else None)
        return KineticResult(
            found=True,
            value=best.km_value,
            unit=best.unit,
            organism=best.organism,
            source="brenda_cross_species",
            evidence_only=(_evidence_only(pool, allow_variants, "cross-species", organism, quantity,
                                          {v.candidate_organism: v for v in verdicts})
                           if isoform or mode else []),
            mechanism_evidence=evidence,
            effector_contrasts=contrasts,
            form_mixtures=mixtures,
            organism_discrepancies=discrepancies,
            source_mixtures=source_mix,
            source_check_unavailable=source_unavailable,
            variant=best.variant,
            preparation=_preparation_of(best),
            selection_tie=tie,
            # No physiological reference at this layer -- it is a runner
            # input, supplied per request, and the resolver never sees it.
            # So `condition_proximity` grades `not_assessed` for every row,
            # which is the honest state and costs the weighting nothing: an
            # axis where every candidate scores alike cannot discriminate,
            # and cancels under normalisation (see ensemble.py).
            ensemble_candidates=_score_frontier(frontier, organism),
            selected_form=name_selected_form(mixtures, best.km_value),
            effectors=list(best.effectors),
            citation=citation_from_brenda_entry(best),
            cross_species_flag=True,
            relatedness=verdicts,
            assay_ph=best.assay_ph,
            assay_temperature_c=best.assay_temperature_c,
            assay_buffer=best.assay_buffer,
            assay_unreported=list(best.assay_unreported),
            commentary=best.conditions,
            search_log=log,
        )

    if not search_literature:
        available = _nothing_matched(
            enzyme_ec, substrate, html_provider, table_label, log
        )
        log.append("Literature search skipped (search_literature=False)")
        return KineticResult(
            found=False,
            source="not_found",
            substrates_available=available,
            search_log=log,
        )

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
        # Papers exist, but the database miss may still be a spelling: a
        # typo'd substrate ("glucoze") reached here and read as "no
        # database value" while BRENDA held D-glucose. Diagnosed into a
        # separate log so this path's last line is still its verdict.
        return KineticResult(
            found=False,
            source="literature_candidates",
            literature_candidates=candidates,
            substrates_available=_nothing_matched(
                enzyme_ec, substrate, html_provider, table_label, []),
            search_log=log,
        )

    # The hint goes BEFORE the conclusion. `_nothing_matched` appends its
    # own line, and two existing tests read `search_log[-1]` for the
    # verdict -- correctly: a reader scanning the end of the log wants the
    # answer, not the advice that led to it.
    available = _nothing_matched(enzyme_ec, substrate, html_provider, table_label, log)
    log.append(
        "Exhausted BRENDA (exact + cross-species), PubMed, and CORE - genuine gap"
    )
    return KineticResult(
        found=False,
        source="not_found",
        substrates_available=available,
        search_log=log,
    )


if __name__ == "__main__":
    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "lactate", enzyme_name="lactate dehydrogenase"
    )
    print(result.model_dump_json(indent=2))
