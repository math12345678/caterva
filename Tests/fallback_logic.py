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
import re
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
    substrate_matches,
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
import row_form
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


class ModeDefault(BaseModel):
    """What a Ki lookup asked for no inhibition mode would have returned had
    it been asked for the model's (`resolve_kinetic_value(compare_mode=...)`).

    `caterva compose --any-mode` asks this resolver for a Ki with no mode, so
    it carries the row the runner returns when no mode is sent (the
    TypeScript CLI without --mode). Its report must still say what the default, which asks with the
    model's mode, would have carried instead, and why the two differ. Until
    2026-09-30 compose worked that out by ranking the rows the answer held,
    which are the frontier of the rows the evidence kept, and the default's
    row need not be among them: for Trypanosoma cruzi hexokinase and ADP
    (Tests/fixtures/recorded/brenda_2.7.1.1.html.gz) the answer holds 1.3 mM
    alone, the default carries 1.5 mM "competitive to ATP", and the report
    said nothing. This is that call's row, found here from the same rows by
    the same steps, so the page is fetched and parsed once.
    """
    #: The mode compared for, and the model substrate the ranking read.
    mode: str
    model_substrate: str | None = None
    #: The row the call with `inhibition_mode=mode` returns, as the dicts
    #: `ensemble_candidates` holds; None when that call refuses.
    row: dict | None = None
    #: What the rows state when that call refuses (source "mode_withheld"),
    #: as its `modes_available` would name them.
    modes_available: list[str] = []


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

    #: Every row of the pool a value would have been chosen from, as
    #: "1e-06 1/s (BRENDA ref 729224)", when EVERY one is outside the
    #: physically plausible range for the quantity (PLAUSIBLE_FOR_SELECTION).
    #: Populated only for source="implausible_withheld": such a value is a
    #: unit slip or a misfiled row far more often than a measurement, and
    #: none is reported as one.
    implausible_values: "list[str]" = []

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

    #: With source "isoform_withheld": how many rows naming no isoform were
    #: not taken as the asked isoform's because every row naming a protein
    #: named another (`_isoform_tiers`). 0 when every row named another.
    isoform_unnamed_withheld: int = 0

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

    #: Why THIS row was carried, in plain English, on every found result:
    #: which rows were set aside and for what (implausible values, missing
    #: pH or temperature, mutants), and that the value is the median row of
    #: what remained -- an actual measurement with its own reference, never
    #: an average. See `_best_evidenced` and ADR 0182.
    chosen_because: str | None = None

    #: Rows set aside before the choice because the value is physically
    #: implausible for the quantity (a kcat below 1e-3 or above 1e8 1/s, a
    #: Km below 1e-7 or above 1e4 mM) while plausible rows existed. Each is
    #: {"value", "unit", "reference_id", "reason"}. Kept, not discarded, so
    #: a reader can see what was not used and argue with it.
    set_aside: list = []

    #: max/min across the rows the choice was made from, when they differ.
    spread_fold: float | None = None

    #: True when that spread exceeds WIDE_SPREAD_FOLD (100-fold). The median
    #: pick stands; the report should say that the literature disagrees by
    #: more than two orders of magnitude, because one number then hides most
    #: of what is known.
    wide_spread: bool = False

    #: The BRENDA reference of every row the choice was made from. Read by
    #: `resolve_kinetic_pair` to find a Km and a kcat measured in one paper.
    candidate_references: list[str] = []

    #: What the carried row itself is, in words a reader can check against
    #: the row: "a K0.5 with a Hill coefficient of 1.8, not a
    #: Michaelis-Menten Km", "an isolated domain ('C-domain')", "its UniProt
    #: accession P35557 is GCK". Each is also in `chosen_because`. Empty when
    #: the row is the plain enzyme's ordinary constant as far as its words say.
    row_notes: list[str] = []

    #: The isoform the carried row measured, by its commentary or, failing
    #: that, its own UniProt cell (`_row_isoform`): "HK-I", "GCK", "IDH1".
    #: None when the row names none. Read by `resolve_kinetic_pair`, which
    #: keeps a Km and a kcat to one isozyme, and by `caterva compose`, whose
    #: report would otherwise say a row naming IDH1 by accession "names no
    #: isoform".
    row_isoform: str | None = None

    #: The carried row's own single UniProt accession (`_own_cell`), or None.
    #: With `row_isoform`, what `resolve_kinetic_pair` reads to keep a Km
    #: and a kcat to one protein where the enzyme index names no isoform.
    row_uniprot: str | None = None

    #: Every row `resolve_kinetic_pair` may pair across tables: the rows left
    #: after the checks that decide what a row IS (implausible values, an
    #: inhibitor in the assay, a treated arm, a minus-activator control,
    #: mutants, constructs, K0.5) and before the preference for complete
    #: conditions, scored as `ensemble_candidates` is. A Km row and a kcat
    #: row of one paper are paired only when their stated conditions match.
    pairable: list = []

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

    #: The other direction: a Ki asked for no mode, with `compare_mode`,
    #: carries what the same call asked for that mode would have returned
    #: (`ModeDefault`). None otherwise, and None when this call found
    #: nothing, since the call with the mode then finds nothing either: the
    #: two take the same tier and differ only at the mode step.
    #:
    #: Read by `caterva compose --any-mode` to say which row its default
    #: would carry and why the two differ. Not emitted by the runner, for
    #: `evidence_only`'s reason: the API always asks with its model's mode,
    #: and the TypeScript CLI prints the stated mode of the row it returns.
    mode_default: "ModeDefault | None" = None

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
    # The accession is a fallback locator only: it stamps rows whose own
    # UniProt cell is empty. It must never decide whether the search runs.
    # Until round 3 of the real-values work a UniProt 503 or ReadTimeout here
    # raised out of the whole BRENDA search -- every constant became a
    # placeholder although the BRENDA page had loaded and held the rows. On
    # any failure the true state is "no fallback accession": rows keep their
    # own cells (brenda_structured and brenda_client do the same).
    try:
        taxon_id = taxon_id_provider(organism)
        if not taxon_id:
            return None
        return uniprot_provider(ec_number, taxon_id)
    except Exception as exc:  # network, HTTP status, malformed JSON
        UNIPROT_FAILURES.append(f"{ec_number}: {type(exc).__name__}")
        return None


#: Fallback-accession lookups that failed this process, as "EC: error type".
#: Read by the report to say the accession could not be fetched; never a
#: reason to stop the search.
UNIPROT_FAILURES: list[str] = []


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
    entries = [e for e in entries if not e.flagged]
    # Nor a computed value: "predicted Ki value" is no measurement
    # (row_form.predicted; fifth round of the real-values review).
    entries = [e for e in entries if not row_form.predicted(getattr(e, "conditions", None))]
    if table_label != KI_TABLE_LABEL and entries:
        inhibitors = _inhibitor_keys(ec_number, html) | _activator_keys(ec_number, html)
        for e in entries:
            e.inhibitors_present = _inhibitors_in_assay(e, inhibitors, substrate)
    if entries:
        papers = _paper_isoform_map(ec_number, html)
        for e in entries:
            e.paper_isoform = _paper_isoform(e, papers)
            _mark_other_enzyme(e)
        _mark_unattributed(entries)
    return entries


def _mark_unattributed(entries) -> None:
    """Mark the rows no protein can be read off: a UniProt cell listing two
    or more accessions, words naming none, and a row of the same paper that
    names a protein in its words. Ref 706823's fenthion rows list CYP2C8,
    CYP1A2, CYP2D6, CYP2B6 and CYP2A6 while its other rows name CYP2C19,
    CYP2C9, CYP1A1 and CYP3A4: an unnamed row is one of several proteins',
    and was carried as CYP2D6's Km (fifth round of the real-values review)."""
    def words_name(e):
        try:
            return _isoform_of(getattr(e, "conditions", None))
        except ImportError:
            return None
    naming = {str(getattr(e, "reference_id", None)) for e in entries if words_name(e)}
    for e in entries:
        e.unattributed = bool(
            getattr(e, "uniprot_from_row", False)
            and len(row_form.accessions(getattr(e, "uniprot", None))) >= 2
            and str(getattr(e, "reference_id", None)) in naming
            and not words_name(e))


def _mark_other_enzyme(entry) -> None:
    """A row whose own UniProt cell names a subunit of ANOTHER enzyme filed
    under the EC (`row_form.other_enzyme`: E. coli FrdA under succinate
    dehydrogenase, 1.3.5.1) is withheld as a variant is, never kept as an
    isoform: its constant is a different enzyme's (fifth round of the
    real-values review)."""
    if not getattr(entry, "uniprot_from_row", False):
        return
    label = row_form.other_enzyme(getattr(entry, "ec_number", None), getattr(entry, "uniprot", None))
    if not label:
        return
    entry.variant = VariantVerdict(
        status="variant", kind="other_enzyme",
        evidence=f"{label}, another enzyme filed under EC {entry.ec_number}",
        reason=(f"The row's UniProt accession ({entry.uniprot}) is {label}, a subunit of another "
                f"enzyme that UniProt files under EC {entry.ec_number}, not an isoform of the "
                "enzyme asked about."))


#: (EC, page digest) -> row_form.paper_isoforms of the page.
_PAPER_ISOFORMS: dict = {}
#: A reading that is a code alone ("1", "II", "b"): which enzyme's code is not said.
_BARE_CODE = re.compile(r"^(?:\d{1,2}|[IVX]{1,4}|[A-Za-z])[a-z]?$")


def _paper_isoform_map(ec_number: str, html: str) -> dict:
    """`row_form.paper_isoforms` of the page, parsed once per page."""
    import hashlib
    key = (ec_number, hashlib.sha1(html.encode("utf-8", "replace")).hexdigest())
    if key not in _PAPER_ISOFORMS:
        try:
            _PAPER_ISOFORMS[key] = row_form.paper_isoforms(ec_number, html)
        except Exception:  # a page that cannot be read names no paper's isoform
            _PAPER_ISOFORMS[key] = {}
    return _PAPER_ISOFORMS[key]


def _canonical_isoform(ec_number, organism, reading):
    """The enzyme index's label for the protein `reading` names ("glucokinase",
    "HK-IV" and "GCK" are all GCK under EC 2.7.1.1 in human), else `reading`."""
    try:
        from caterva.enzymes.finder import isozymes
        from caterva.enzymes.isozyme import _listed
    except ImportError:
        return reading
    try:
        found = isozymes(ec_number, organism)
        listed = _listed(found, reading) if found.organism and found.count > 1 else None
    except Exception:
        return reading
    return listed[0].label if listed else reading


def _cell_is_read(entry) -> bool:
    """Whether the row's own UniProt cell names a protein the enzyme index
    files under its EC (one isoform, several, or THE enzyme of a
    one-protein organism): then the cell, not the paper, says what the row
    measured. A cell the index does not know (ref 734041's seven NDM
    accessions under EC 3.5.2.6) says nothing, and the paper is read."""
    if not getattr(entry, "uniprot_from_row", False):
        return False
    try:
        return bool(row_form.isoforms_of_accessions(entry.ec_number, entry.uniprot))
    except Exception:  # an index that cannot be read leaves the cell as the word
        return True


def _paper_isoform(entry, papers) -> "str | None":
    """The isoform(s) the entry's paper names elsewhere on the page, for a
    row whose own words and own UniProt cell name none, joined as the
    isoform reader joins two ("NDM-3 and NDM-4") when several; else None.

    Several are read as a UniProt cell listing several proteins is
    (`_row_isoform`): a row of a paper naming only NDM variants is not
    TEM-1's, while it names none of them for a request of any one."""
    if not getattr(entry, "reference_id", None) or _cell_is_read(entry):
        return None
    try:
        if _isoform_of(getattr(entry, "conditions", None)):
            return None
        readings = papers.get(((entry.organism or "").lower(), str(entry.reference_id))) or ()
        readings = [_canonical_isoform(entry.ec_number, entry.organism, r) for r in readings
                    if not _BARE_CODE.match(r.strip())]
        distinct = row_form.distinct_isoforms(readings, _same_isoform)
        return " and ".join(distinct) if distinct else None
    except ImportError:
        return None


#: (EC, page digest) -> the compound keys BRENDA lists Ki rows for.
_INHIBITOR_KEYS: dict = {}


def _compound_key(name) -> str:
    """One compound's key for "is this compound present in the assay":
    its spellings one (compound_names.identity_key), and a leading stereo
    descriptor aside, since an Activating Compounds table writes
    "fructose 1,6-bisphosphate" where a row writes "D-fructose
    1,6-bisphosphate"."""
    text = " ".join((name or "").split())
    try:
        from compound_names import identity_key
    except ImportError:  # pragma: no cover - the package layout
        from Tests.compound_names import identity_key
    text = re.sub(r"^(?:[DL]{1,2}|alpha|beta|\([RS+-]\))-(?=\w)", "", text)
    return identity_key(text) or "".join(text.lower().split())


def _inhibitor_keys(ec_number: str, html: str) -> frozenset:
    """Every compound the page's Ki table lists, any organism: the enzyme's
    known inhibitors. Parsed once per page."""
    import hashlib
    key = (ec_number, hashlib.sha1(html.encode("utf-8", "replace")).hexdigest())
    if key not in _INHIBITOR_KEYS:
        try:
            rows = parse_brenda_km_html(html, ec_number, [], None, require_substrate_match=False,
                                        table_label=KI_TABLE_LABEL)
        except Exception:  # a page whose Ki table cannot be read names no inhibitor
            rows = []
        _INHIBITOR_KEYS[key] = frozenset(_compound_key(e.substrate) for e in rows)
    return _INHIBITOR_KEYS[key]


#: (EC, page digest) -> the compound keys BRENDA's Activating Compounds table lists.
_ACTIVATOR_KEYS: dict = {}
#: Compounds an Activating Compounds table lists that are an assay's
#: ordinary stabilisers, reducing agents or detergents, not an allosteric
#: effector a Km is measured "in the presence of" to change it.
_ASSAY_ADDITIVES = frozenset(_compound_key(n) for n in (
    "dithiothreitol", "DTT", "2-mercaptoethanol", "beta-mercaptoethanol", "mercaptoethanol",
    "bovine serum albumin", "BSA", "albumin", "glycerol", "EDTA", "Triton X-100", "Tween 20",
    "Tween 80", "polyethylene glycol", "PEG", "sucrose", "glutathione", "cysteine", "L-cysteine",
    "ethanol", "dimethyl sulfoxide", "DMSO", "Brij 35", "CHAPS", "sodium dodecyl sulfate", "SDS",
    "additional information"))


def _activator_keys(ec_number: str, html: str) -> frozenset:
    """Every compound the page's Activating Compounds table lists, any
    organism, ions and assay additives aside: the enzyme's known
    activators. A Km "in the presence of D-fructose 1,6-bisphosphate" for
    pyruvate kinase (ref 709464), whose commentary does not call FBP an
    activator, is as apparent a constant as one "activation by" it (fourth
    round of the real-values review). Read by a regular expression over the
    table's compound cells, once per page."""
    import hashlib
    key = (ec_number, hashlib.sha1(html.encode("utf-8", "replace")).hexdigest())
    if key not in _ACTIVATOR_KEYS:
        found = set()
        table = re.search(r"showTable\('(tab\d+)'\)\">Activating Compounds<", html)
        if table:
            for cell in re.findall(r'id="' + table.group(1) + r'r\d+(?:sr\d+)?c0"[^>]*>([^<]*)<', html):
                name = " ".join(cell.split())
                if name and not row_form.is_ion(name) and _compound_key(name) not in _ASSAY_ADDITIVES:
                    found.add(_compound_key(name))
        _ACTIVATOR_KEYS[key] = frozenset(found)
    return _ACTIVATOR_KEYS[key]


def _is_cofactor(name: str) -> bool:
    try:
        from caterva.compose.defaults import is_cofactor
    except ImportError:  # the flat layout
        return _compound_key(name) in {"atp", "adp", "nad+", "nadh", "nadp+", "nadph", "fad",
                                       "fmn", "coa", "h2o", "o2"}
    return is_cofactor(name)


def _inhibitors_in_assay(entry, inhibitor_keys, substrate=None) -> list:
    """The compounds `entry` says were present in its assay that are
    inhibitors of the enzyme: named as such ("in the presence of inhibitor
    X"), or listed in the page's Ki table. Ions, cofactors and the substrate
    itself are not counted: Mg2+ for a kinase and NADH for a dehydrogenase
    are the assay, and a substrate's own Ki row is substrate inhibition."""
    out = []
    for x in getattr(entry, "effectors", None) or []:
        if x.presence != "present" or not x.named:
            continue
        name = x.compound_text
        if row_form.is_ion(name) or _is_cofactor(name):
            continue
        if substrate and _compound_key(name) == _compound_key(substrate):
            continue
        if x.role in ("inhibitor", "activator") or _compound_key(name) in inhibitor_keys:
            out.append(name)
    # A compound listed bare at a concentration, with no "in the presence
    # of": "hCA I, 25 mM hydroxyurea" (BRENDA ref 650526, human carbonic
    # anhydrase I, beside the same paper's plain "hCA I" row).
    for m in _BARE_ROLE_COMPOUND.finditer(getattr(entry, "conditions", None) or ""):
        # "0.008 mM inhibitor 3-(3,5-dibromo)-4-hydroxybenzylidine-..."
        # (bovine glutamate dehydrogenase, ref 698927): the commentary calls
        # it an inhibitor, with no "in the presence of". A comma inside a
        # name ("3,5-") is the name's; one followed by a space ends it.
        name = m.group(1).strip()
        if name and name not in out:
            out.append(name)
    for m in _BARE_COMPOUND.finditer(getattr(entry, "conditions", None) or ""):
        name = m.group(1).strip()
        if _BARE_ROLE.match(name):
            continue
        if (_compound_key(name) in inhibitor_keys and name not in out
                and not row_form.is_ion(name) and not _is_cofactor(name)
                and not (substrate and _compound_key(name) == _compound_key(substrate))):
            out.append(name)
    return out


_BARE_COMPOUND = re.compile(r"\b\d+(?:\.\d+)?\s*[mµun]?M\s+([A-Za-z0-9(][^,;]*?)\s*(?=[,;]|$)")
_BARE_ROLE = re.compile(r"(?:allosteric\s+)?(?:inhibitor|activator|effector)s?\s+", re.IGNORECASE)
_BARE_ROLE_COMPOUND = re.compile(
    r"\b\d+(?:\.\d+)?\s*[mµun]?M\s+(?:allosteric\s+)?(?:inhibitor|activator|effector)s?\s+"
    r"(\S.*?)\s*(?=,\s|;|$)", re.IGNORECASE)


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


#: Physically plausible ranges used to SET ASIDE rows before the choice, per
#: quantity, as (low, high, unit). Narrower than brenda_client's flagging
#: bounds (KCAT_PLAUSIBLE_MIN_PER_S is 1e-6, a cross-layer contract under ADR
#: 0003), on purpose: those bounds drop a row from every use, these only
#: decide which rows a pick is made from when plausible ones exist.
#:
#: kcat: below 1e-3 1/s is one turnover every quarter of an hour, which in
#: BRENDA is almost always a unit slip (min^-1 or a specific activity
#: entered as a turnover number); above 1e8 1/s is past the diffusion
#: limit. The case that made this necessary: human carbonic anhydrase and
#: CO2, rows spanning 1e-06 to 1.4e6 1/s, and the minimum, 1e-06, was carried
#: as GROUNDED. CA II's true kcat is ~1e6 1/s.
#: Km: below 1e-7 mM (0.1 nM) and above 1e4 mM (10 M, past the solubility of
#: almost anything) are not Michaelis constants.
#: Ki is not bounded here: tight-binding inhibitors reach picomolar Ki
#: honestly, and a lower bound would set the best inhibitors aside.
PLAUSIBLE_FOR_SELECTION = {
    "kcat": (1e-3, 1e8, "1/s"),
    "km": (1e-7, 1e4, "mM"),
}

def _implausible_withheld(best, rows, quantity, log, tier):
    """A not-found result when the row chosen is outside the plausible range,
    which `_best_evidenced` allows only when EVERY row is (it sets
    implausible rows aside whenever a plausible one exists); None otherwise.

    The carbonic anhydrase kcat of 1e-06 1/s was carried as GROUNDED while
    its rows had plausible company; with none, the choice would still be a
    number no enzyme has, so nothing is reported and the rows are named."""
    q = _quantity_of(rows, quantity)
    bounds = PLAUSIBLE_FOR_SELECTION.get(q)
    if not bounds or best is None:
        return None
    low, high, unit = bounds
    if low <= best.km_value <= high:
        return None
    values = [f"{e.km_value:g} {getattr(e, 'unit', None) or unit} (BRENDA ref {_ref(e)})" for e in rows]
    log.append(f"{tier}: every candidate {q} row is outside the physically plausible range "
               f"({low:g} to {high:g} {unit}): {'; '.join(values)}; none is reported as a "
               f"measurement (a unit slip or a misfiled row is far likelier)")
    return KineticResult(
        found=False,
        source="implausible_withheld",
        implausible_values=values,
        search_log=log,
    )


#: A spread of the values chosen from wider than this is recorded on the
#: result (`wide_spread`) so the report can flag it. The median pick stands.
WIDE_SPREAD_FOLD = 100.0


def _quantity_of(entries, quantity):
    """'km' | 'kcat' | 'ki' for these rows: the caller's word, else the unit."""
    if quantity:
        return quantity
    unit = getattr(entries[0], "unit", None) if entries else None
    return "kcat" if unit == "1/s" else "km"


def _ref(entry):
    return getattr(entry, "reference_id", None) or "no reference"


def _is_mutant(entry) -> bool:
    """A row whose commentary says it measured a mutant or other non-isozyme
    variant ("mutant R132H", "C123A"). An isozyme row is not a mutant: when
    it is still in the pool, the isoform step kept it as the isoform asked
    for."""
    verdict = getattr(entry, "variant", None)
    return bool(verdict is not None and verdict.status == "variant"
                and verdict.kind != "isozyme")


def _variant_words(entry) -> str:
    """The words of a mutant row that say which mutant it is."""
    verdict = getattr(entry, "variant", None)
    found = sorted(_mutations_of(getattr(entry, "conditions", None) or ""))
    if found:
        return "/".join(found)
    return (getattr(verdict, "evidence", None) or getattr(verdict, "descriptor", None)
            or "mutant")


def _kitz_wilson(entry) -> bool:
    """Whether a Ki row was "determined from Kitz-Wilson plots": the K_I of
    an irreversible inactivation, which `caterva compose` ranks after every
    reversible constant (caterva.compose.ki_mode). The median must not land
    on one when a reversible row exists: human MAO-B and benzylhydrazine
    (ref 702238) would carry 0.048 mM, the Kitz-Wilson row, as its Ki. The
    pattern is compose's own, so the two cannot disagree on what one is."""
    try:
        from caterva.compose.ki_mode import _KITZ_WILSON as pattern
    except ImportError:  # the flat layout, without the caterva package
        import re
        pattern = re.compile(r"\bKitz[\s-]*Wilson\b", re.IGNORECASE)
    return bool(pattern.search(getattr(entry, "conditions", None) or ""))


def _effector_key(effector) -> str:
    return " ".join((getattr(effector, "compound_text", "") or "").lower().split())


def _added_compounds(entry, rows) -> list:
    """The compounds `entry` was measured WITH, where a row of the same paper
    in `rows` was measured WITHOUT them: the treated arm of that paper's own
    presence/absence experiment."""
    ref = getattr(entry, "reference_id", None)
    if not ref:
        return []
    same_paper = [other for other in rows
                  if other is not entry and getattr(other, "reference_id", None) == ref]
    absent = {
        _effector_key(x)
        for other in same_paper
        for x in (getattr(other, "effectors", None) or []) if x.presence == "absent"
    }
    # A row of the same paper that names no added compound at all is that
    # paper's control as surely as one saying "in the absence of": human
    # HDAC8 and Fluor de Lys HDAC8 substrate, BRENDA ref 719061, reports Km
    # 0.744 mM plainly and 0.23 mM "presence of activator
    # N-(phenylcarbamothioyl)benzamide"; the model carried the activated Km
    # beside the same paper's plain kcat (2026-11-12).
    plain = any(not (getattr(other, "effectors", None) or []) for other in same_paper)
    # An ion is not an addition: with and without K+ is pyruvate kinase's
    # essential activator present or withdrawn (`_withdrawn_ions`), and the
    # arm WITH it is the enzyme's physiological constant.
    # "chimera with Haemophilus influenzae enzyme": a construct of two
    # proteins, not a compound added to the assay. Read as one, the note
    # said rows "measured with Haemophilus influenzae enzyme ... added"
    # (third round's review); `construct_of` names it a chimera instead.
    if (row_form.construct_of(getattr(entry, "conditions", None)) or "").startswith(
            "a chimeric construct"):
        return []
    return [
        x.compound_text for x in (getattr(entry, "effectors", None) or [])
        if x.presence == "present" and (plain or _effector_key(x) in absent)
        and not row_form.is_ion(x.compound_text)
        and not re.search(r"\benzyme\b|\bprotein\b", x.compound_text or "", re.IGNORECASE)
    ]


def _withdrawn_ions(entry, rows) -> list:
    """The ions `entry` was measured WITHOUT where a row of the same paper in
    `rows` was measured with them: the minus-activator control.

    BRENDA ref 674499 gives human muscle pyruvate kinase and PEP kcat 3.2
    1/s "in the absence of K+" and 1182 1/s "in the presence of K+". K+ is
    the enzyme's essential activator, and the control without it was carried
    as GROUNDED because K+ read as an added compound to strip."""
    ref = getattr(entry, "reference_id", None)
    if not ref:
        return []
    present = {
        _effector_key(x)
        for other in rows if getattr(other, "reference_id", None) == ref
        for x in (getattr(other, "effectors", None) or [])
        if x.presence == "present" and row_form.is_ion(x.compound_text)
    }
    withdrawn = [
        x.compound_text for x in (getattr(entry, "effectors", None) or [])
        if x.presence == "absent" and row_form.is_ion(x.compound_text) and _effector_key(x) in present
    ]
    stand_in = row_form.cation_stand_in(getattr(entry, "conditions", None))
    if stand_in and present and not any(
            x.presence == "present" and row_form.is_ion(x.compound_text)
            and _effector_key(x) in present for x in (getattr(entry, "effectors", None) or [])):
        withdrawn.append(f"the activating cation ({stand_in} in its place)")
    return withdrawn


_ROLE_ONLY = {"inhibitor", "inhibitors", "effector", "effectors", "activator", "activators"}


def _inhibited(entry, rows) -> list:
    """The inhibitors present in `entry`'s assay: the page's own Ki table or
    the commentary says they inhibit (`_inhibitors_in_assay`), or the same
    paper has a row "in the absence of inhibitor" and this row names an
    organic compound present at a concentration. An apparent Km or kcat
    measured with an inhibitor present is not the enzyme's own constant.

    BRENDA ref 766313, xanthine oxidase and xanthine: 0.01208 mM "in the
    absence of inhibitor"; 0.01435, 0.0167 and 0.02014 mM "in the presence
    of" 0.00025 to 0.001 mM of a tropolone inhibitor. The median of the pool
    landed on 0.0167 and was put into a competitive-inhibition model as the
    Km."""
    named = list(getattr(entry, "inhibitors_present", None) or [])
    # A compound the commentary itself calls an effector of the enzyme
    # ("in the presence of 0.02 mM activator LY-2121260", a glucokinase
    # activator drug) changes the constant just as an inhibitor does.
    named += [x.compound_text for x in (getattr(entry, "effectors", None) or [])
              if x.presence == "present" and x.named and x.role in ("activator", "effector")
              and not row_form.is_ion(x.compound_text) and x.compound_text not in named]
    if named:
        return named
    ref = getattr(entry, "reference_id", None)
    if not ref:
        return []
    control = any(
        x.presence == "absent" and x.compound_text.strip().lower() in _ROLE_ONLY
        for other in rows if getattr(other, "reference_id", None) == ref
        for x in (getattr(other, "effectors", None) or [])
    )
    if not control:
        return []
    return [x.compound_text for x in (getattr(entry, "effectors", None) or [])
            if x.presence == "present" and x.named and x.concentration_text
            and not row_form.is_ion(x.compound_text)]


def _isoform_from_accession(entry) -> str | None:
    """The protein(s) a row's OWN UniProt cell names, joined as the isoform
    reader joins two ("CYP3A5 and CYP3A43"), or None when the cell is the
    caller's fallback, absent, or names an accession the enzyme index does
    not file under the row's EC number -- or when the EC is one protein in
    the row's organism: human ACHE's P22303 under EC 3.1.1.7 is THE enzyme,
    not an isoform of it, and the report said "the row measured isoform
    ACHE; if the enzyme you mean is another isoform ..." of it."""
    if not getattr(entry, "uniprot_from_row", False):
        return None
    ec, cell = getattr(entry, "ec_number", None), getattr(entry, "uniprot", None)
    labels = row_form.isoforms_of_accessions(ec, cell)
    if not labels or row_form.proteins_in_organism_of(ec, cell) < 2:
        return None
    return " and ".join(labels)


def _own_cell(entry) -> str | None:
    """The row's own UniProt cell, one accession, or None (no cell, several,
    or the caller's fallback accession)."""
    if not getattr(entry, "uniprot_from_row", False):
        return None
    cells = row_form.accessions(getattr(entry, "uniprot", None))
    return cells[0] if len(cells) == 1 else None


def _isoform_own(entry):
    """The isoform a row names in its words or its own UniProt cell, or None."""
    try:
        named = _isoform_of(getattr(entry, "conditions", None))
    except ImportError:
        named = None
    return named or _isoform_from_accession(entry)


def _protein_of(isoform, uniprot):
    """What identifies the protein a row measured: its isoform reading, else
    its own single UniProt accession, else None."""
    return isoform or uniprot or None


def _other_protein(a, b) -> bool:
    """Whether two `_protein_of` readings name different proteins. Unknown
    (either None) is not different."""
    if not (a and b) or a == b:
        return False
    try:
        return not _same_isoform(a, b)
    except ImportError:
        return True


def _row_isoform_or_none(entry):
    """`_row_isoform`, or None where caterva's isoform reader is not
    importable (then only the UniProt cell is read)."""
    try:
        return _row_isoform(entry)
    except ImportError:
        return _isoform_from_accession(entry)


def _row_notes(entry, quantity) -> list:
    """What the carried row is, beyond its value, for the report
    (`KineticResult.row_notes`). See row_form's module docstring."""
    notes = []
    text = getattr(entry, "conditions", None)
    ranged = getattr(entry, "value_range", None)
    if ranged:
        notes.append(f"BRENDA gives the paper's value as a range ({ranged[0]:g} - {ranged[1]:g} "
                     f"{getattr(entry, 'unit', '') or ''}), and its lower bound is carried")
    if quantity == "km":
        k05 = row_form.half_saturation(text)
        if k05:
            notes.append(f"the row is {k05}, not a Michaelis-Menten Km: a hyperbolic rate law "
                         "built with it approximates a cooperative enzyme")
    if _is_mutant(entry):
        # Carried only when asked for ("IDH1 R132H") or when no wild-type
        # row exists; either way the reader is told it is a mutant's.
        notes.append(f"the row measured a mutant enzyme ({_variant_words(entry)!r}), not the "
                     "wild type")
    construct = row_form.construct_of(text)
    if construct:
        notes.append(f"the row measured {construct}, not the native enzyme")
    reaction = _REACTION_NAMED.search(text or "")
    if reaction:
        # "CYP3A4, desulfuration ... to fenthion-oxon" (ref 706823) beside the
        # same paper's sulfoxidation row: which reaction the Km is of (third
        # round's review).
        notes.append(f"the row measured one reaction of the compound, {reaction.group(1)} to "
                     f"{reaction.group(2).strip()}")
    inhibitors = list(getattr(entry, "inhibitors_present", None) or [])
    if inhibitors:
        notes.append(f"the row was measured with {', '.join(inhibitors)} present, an inhibitor or effector: an "
                     "apparent constant")
    if quantity == "ki" and IRREVERSIBLE_INHIBITOR.search(str(getattr(entry, "substrate", "") or "")):
        notes.append(f"{entry.substrate} is an irreversible (covalent or mechanism-based) "
                     "inactivator: a Ki row describes its initial reversible complex, and a "
                     "reversible inhibition model leaves the inactivation out")
    if quantity == "ki" and _NO_PREINCUBATION.search(text or ""):
        # Thrombin's DV24K10RY rows say "after no preincubation time": the
        # apparent Ki of a slow-binding inhibitor before equilibrium (fourth
        # round of the real-values review).
        notes.append("the row was measured without preincubating enzyme and inhibitor: for a "
                     "slow-binding inhibitor that is an apparent, not the equilibrium, Ki")
    elif quantity == "ki" and _PREINCUBATED.search(text or ""):
        notes.append("the row was measured after preincubating enzyme and inhibitor")
    assayed = _assay_substrate(text) if quantity == "ki" else None
    if assayed:
        notes.append(f"the Ki was measured on the hydrolysis of {assayed}")
    try:
        commentary_isoform = _isoform_of(text)
    except ImportError:
        commentary_isoform = None
    accession_isoform = _isoform_from_accession(entry)
    if (accession_isoform and not commentary_isoform
            and row_form.proteins_in_organism_of(entry.ec_number, entry.uniprot) > 1):
        notes.append(f"the row's UniProt accession ({entry.uniprot}) is {accession_isoform}")
    paper = getattr(entry, "paper_isoform", None)
    if paper and " and " not in paper and not commentary_isoform and not accession_isoform:
        notes.append(f"the row names no isoform itself; its paper (BRENDA ref {entry.reference_id}) "
                     f"names only {paper} in its other entries on BRENDA's page")
    return notes


#: Inhibitors that inactivate covalently or by mechanism: a Ki row of one
#: describes its initial reversible complex, and a competitive model leaves
#: the inactivation out. Thrombin's automatic inhibitor was a chloromethyl
#: ketone; MAO-B and selegiline was modelled as a reversible competitor with
#: no word of it (fourth round of the real-values review).
IRREVERSIBLE_INHIBITOR = re.compile(
    r"chloromethyl[- ]?ketone|fluoromethyl[- ]?ketone|\b(?:CMK|FMK)\b|diisopropyl ?fluorophosphate"
    r"|phenylmethyl(?:sulfonyl|sulphonyl) fluoride|\bPMSF\b|\bDFP\b|selegiline|deprenyl|rasagiline"
    r"|clorgyline|pargyline|tranylcypromine|phenelzine|\baspirin\b|acetylsalicylic|clavulan"
    r"|sulbactam|tazobactam|difluoromethylornithine|\bDFMO\b|eflornithine|vigabatrin"
    r"|iodoacetamide|iodoacetate|N-ethylmaleimide|\bTLCK\b|\bTPCK\b|tosyl-L-(?:lysine|phenylalanine) "
    r"chloromethyl"
    # Serpins trap their protease in a covalent complex (suicide substrates).
    r"|antithrombin|\bserpin|antitrypsin|antichymotrypsin|antiplasmin|plasminogen activator inhibitor",
    re.IGNORECASE)

_NO_PREINCUBATION = re.compile(r"\b(?:no|without)\s+preincubation\b|\bnot\s+preincubated\b",
                               re.IGNORECASE)
_PREINCUBATED = re.compile(r"\bafter\s+(?:\d+\s*\w+\s+)?preincubation\b|\bpreincubated\b",
                           re.IGNORECASE)

#: A reaction named with its product in a commentary: "desulfuration ... to
#: fenthion-oxon", "N-demethylation to norketamine".
_REACTION_NAMED = re.compile(
    r"\b((?:[A-Za-z]-)?[a-z]+(?:ation|oxidation|ylation|lysis))\b[^,;]{0,40}?\bto\s+([^,;]{3,60})")


def _treated_arm(entry, rows) -> bool:
    """Whether `entry` is the "in the presence of X" arm of an experiment
    whose "in the absence of X" arm is also in `rows`.

    The case: human carbonic anhydrase II and CO2, BRENDA ref 702518 reports
    Km 13 mM "in the absence of timolol" and 0.012 and 0.013 mM "in the
    presence of" 4.5 and 2.0 mM timolol. The enzyme's own Km is the control
    arm; the median of all three was 0.013, a thousandfold below CA II's
    textbook ~10 mM. Only a designed contrast within one paper is read this
    way: a cofactor every row of a paper states as present (Mg2+ for a
    kinase) is the assay, not a treatment, and is left alone."""
    return bool(_added_compounds(entry, rows))


def _has_any_condition(entry) -> bool:
    return (getattr(entry, "assay_ph", None) is not None
            or getattr(entry, "assay_temperature_c", None) is not None)


def _has_conditions(entry) -> bool:
    return (getattr(entry, "assay_ph", None) is not None
            and getattr(entry, "assay_temperature_c", None) is not None)


def _is_row(entry, row) -> bool:
    """Whether `entry` is the row `row` (a dict of `_score_frontier`'s shape)
    describes: one reference, one value, one commentary."""
    return (str(getattr(entry, "reference_id", None)) == str(row.get("reference_id"))
            and float(entry.km_value) == float(row.get("value"))
            and (getattr(entry, "conditions", None) or None) == (row.get("conditions") or None))


#: Fewer rows than this stating both pH and temperature are checked against
#: the rows stating one of them before the rest are passed over.
CONDITIONS_FEW = 3
#: How far outside a range "outside" is: any distance. Only the median of
#: few rows is compared, against many, and the remedy is to choose among more.
OUTSIDE_FOLD = 1.0


def _paper_median(rows):
    """`(median, papers)`: the median over papers of each paper's median row
    value, so one paper's long series (E. coli catalase, ref 685401: fifteen
    rows of a pH and cosubstrate series at 11-151 1/s beside four papers at
    200-18000 1/s) counts once; and how many papers there are."""
    by_paper = {}
    for e in rows:
        v = getattr(e, "km_value", None)
        if isinstance(v, (int, float)) and v > 0:
            by_paper.setdefault(str(getattr(e, "reference_id", None)), []).append(v)
    medians = sorted(sorted(vs)[(len(vs) - 1) // 2] for vs in by_paper.values())
    if not medians:
        return None, 0
    return medians[(len(medians) - 1) // 2], len(medians)


#: At least this many papers before the rows stating both pH and
#: temperature are judged against the rest (`_median_far`).
BULK_PAPERS_MIN = 5


def _median_far(few, many) -> bool:
    """Whether the median row of `few` lies more than PAIR_MAX_FOLD_FROM_PICK
    from the paper median of `many` (`_paper_median`), over at least
    BULK_PAPERS_MIN papers."""
    a, _ = _median_row(few)
    x = getattr(a, "km_value", None)
    y, papers = _paper_median(many)
    if papers < BULK_PAPERS_MIN or not (isinstance(x, (int, float)) and x > 0 and y):
        return False
    return max(x / y, y / x) > PAIR_MAX_FOLD_FROM_PICK


def _outside(few, many) -> bool:
    """Whether the median of `few` lies more than OUTSIDE_FOLD outside the
    range of `many` (both lists of entries)."""
    values = sorted(e.km_value for e in many if isinstance(getattr(e, "km_value", None), (int, float)))
    picked = _median_row(few)
    v = getattr(picked, "km_value", None) if picked is not None else None
    if not values or not isinstance(v, (int, float)) or v <= 0:
        return False
    return v > values[-1] * OUTSIDE_FOLD or v < values[0] / OUTSIDE_FOLD


_ASSAYED = re.compile(r"\b(?:hydrolysis|cleavage) of\s+([^,;]+?)\s*(?=[,;]|$)"
                     r"|\b(?:with|using)\s+([^,;]+?)\s+as (?:the )?substrate\b", re.IGNORECASE)


def _assay_substrate(conditions) -> "str | None":
    m = _ASSAYED.search(conditions or "")
    return " ".join((m.group(1) or m.group(2)).split()) if m else None


_WILD_LABEL = re.compile(r"\bwild[- ]?type(?:\s+enzyme)?\b,?\s*", re.IGNORECASE)


def _bare(conditions) -> str:
    return re.sub(r"[\s,;]+", " ", _WILD_LABEL.sub("", conditions or "")).strip().lower()


def _unlabelled_beside_wild_type(entry, rows) -> bool:
    """Whether `entry` states no wild-type label while a row of its own paper
    (same compound) states one and otherwise the same conditions."""
    text = getattr(entry, "conditions", None) or ""
    ref = getattr(entry, "reference_id", None)
    if not ref or _WILD_LABEL.search(text):
        return False
    mine = _bare(text)
    return any(other is not entry and getattr(other, "reference_id", None) == ref
               and getattr(other, "substrate", None) == getattr(entry, "substrate", None)
               and _WILD_LABEL.search(getattr(other, "conditions", None) or "")
               and _bare(other.conditions) == mine
               for other in rows)


def _unit_slip(middle_pool, every_row):
    """`(kept, slipped, fold, reference median)` when the two middle rows of
    an even pool differ by a power of a thousand (within a factor of 2) --
    the signature of an mM/µM (or per-minute/per-second) slip -- and the
    rest of the candidate rows, before the narrowing, side with one of them;
    else None.

    Candida rugosa lipase and 4-nitrophenyl palmitate: the free enzyme's Km
    is 0.17 mM (ref 678010) and 0.00017 mM (ref 714870), both "pH 7.0,
    37 C"; the immobilised preparations of both papers lie at 0.089-0.274
    mM. "The lower of the two middle values" carried 0.00017, the
    sub-micromolar row (fourth round of the real-values review)."""
    import math
    ordered = sorted(middle_pool, key=lambda e: e.km_value)
    a, b = ordered[(len(ordered) - 1) // 2], ordered[len(ordered) // 2]
    if not (a.km_value and b.km_value and a.km_value > 0):
        return None
    fold = b.km_value / a.km_value
    power = round(math.log10(fold) / 3)
    if power < 1 or abs(math.log10(fold) - 3 * power) > math.log10(2):
        return None
    rest = [e.km_value for e in every_row if e is not a and e is not b
            and isinstance(e.km_value, (int, float)) and e.km_value > 0]
    if not rest:
        return None
    reference = sorted(rest)[len(rest) // 2]
    def distance(e):
        return abs(math.log10(e.km_value / reference))
    if abs(distance(a) - distance(b)) < 1:
        return None
    kept, slipped = (a, b) if distance(a) < distance(b) else (b, a)
    return kept, slipped, fold, reference


def _middle_ph_series(pool):
    """`(kept, other)` when the two middle rows of an even pool are one
    paper's rows stating the same conditions but for pH, the kept one being
    nearer PHYSIOLOGICAL_PH; else None. Bovine liver glutamate
    dehydrogenase, ref 671289: 0.24 mM at pH 8.5 was carried over 1.01 mM at
    pH 7.4 as "the lower of the two middle values" (fifth round of the
    real-values review)."""
    ordered = sorted(pool, key=lambda e: e.km_value)
    a, b = ordered[(len(ordered) - 1) // 2], ordered[len(ordered) // 2]
    if a is b or getattr(a, "reference_id", None) != getattr(b, "reference_id", None):
        return None
    pa, pb = getattr(a, "assay_ph", None), getattr(b, "assay_ph", None)
    if pa is None or pb is None or abs(pa - pb) < 0.05:
        return None
    if getattr(a, "assay_temperature_c", None) != getattr(b, "assay_temperature_c", None):
        return None
    strip = re.compile(r"\b(?:at\s+)?pH\s*\d{1,2}(?:\.\d+)?", re.IGNORECASE)
    if row_form.condition_words(strip.sub(" ", a.conditions or "")) != row_form.condition_words(
            strip.sub(" ", b.conditions or "")):
        return None
    if abs(pa - PHYSIOLOGICAL_PH) <= abs(pb - PHYSIOLOGICAL_PH):
        return a, b
    return b, a


def _median_row(rows):
    """The row whose value is the median of `rows`: an actual row, so the
    citation stays one real measurement. With an even count, the lower of
    the two middle rows (no row holds the mean of the two, and an average
    of two papers is a number neither paper reported). Ties in value keep
    the rows' order, so the choice is deterministic."""
    ordered = sorted(rows, key=lambda e: e.km_value)
    return ordered[(len(ordered) - 1) // 2], len(ordered) % 2 == 0


def _best_evidenced(
    entries, log, tier, requested_organism=None, relatedness_by_organism=None,
    quantity=None, prefer_reference=None, detail=None, prefer_row=None,
):
    """Choose the row a model carries, and say why in plain English.

    THE POLICY (ADR 0182), in order, each step applied only when it leaves
    at least one row:

    1. Set aside physically implausible values (`PLAUSIBLE_FOR_SELECTION`),
       naming each. Carbonic anhydrase and CO2 in human carried kcat 1e-06
       1/s out of rows reaching 1.4e6, labelled GROUNDED.
    2. Prefer the control arm of a paper's own presence/absence experiment
       over its treated arm (`_treated_arm`), rows that carry a BRENDA
       reference over rows that carry none (a value with no reference cannot
       be checked), and rows stating both pH and temperature (STRENDA, ADR
       0010) -- or, when none states both, rows stating one -- in that order.
    3. For a Ki, prefer reversible constants over Kitz-Wilson inactivation
       constants (`_kitz_wilson`). Prefer rows not measuring a mutant ("mutant", "R132H", "C123A").
       `_partition_variants` already removes them unless allow_variants is
       set; this keeps the preference when it is.
    4. Across organisms only, the non-dominated frontier (`evidence_rank`,
       ADR 0047), which ranks the closer relative first. In one organism
       it is skipped (see the comment at the step).
    5. When `prefer_row` names a row still among the candidates (one
       `resolve_kinetic_pair` matched to the other constant's row by its
       stated conditions), take it. `prefer_reference` (a paper) is the
       older, looser form, kept for callers that send it.
    6. Take the MEDIAN row of what remains.

    WHAT A ROW IS (the second adversarial round, 2026-11-11; row_form.py).
    Before the preference for complete conditions, each applied only when
    it leaves some rows: rows measured with an inhibitor or other effector
    in the assay (`_inhibited`: the page's Ki table lists it, the commentary
    calls it one, or the paper has an "in the absence of inhibitor" row) are
    passed over; the minus-activator control of an ion (no K+ for pyruvate
    kinase, choline chloride for thrombin's Na+) is passed over for the row
    with it (`_withdrawn_ions`); constructs and altered preparations
    (`row_form.construct_of`) after native rows; for a Km, K0.5 / Hill rows
    after true Km rows. What the carried row still is -- a K0.5, a construct,
    an isozyme its own UniProt cell names -- is said (`row_notes`).

    WHY THE MEDIAN, NOT THE MINIMUM. This was `min(key=km_value)` over the
    frontier. A minimum seeks the tail, and the tail is where unit slips and
    unusual preparations sit: hexokinase/D-glucose kcat in human carried the
    bottom of 40.1-101 1/s, TEM-1/ampicillin 5.4 of 5.4-3660 1/s. The median
    row is the measurement the literature sits around, it is robust to one
    wild value at either end, and it is still a real row with a real
    reference -- an average would be a number no paper reported.

    When what remains still spans more than WIDE_SPREAD_FOLD, the pick stands
    and `detail["wide_spread"]` is set so the report can say so.

    `detail`, when a dict is passed, receives `chosen_because`, `set_aside`,
    `spread_fold`, `wide_spread` and `candidate_references`.
    """
    q = _quantity_of(entries, quantity)
    rows = list(entries)
    passed_over = []  # plain-English clauses, in the order applied
    set_aside = []

    bounds = PLAUSIBLE_FOR_SELECTION.get(q)
    if bounds and len(rows) > 1:
        low, high, unit = bounds
        implausible = [e for e in rows if not (low <= e.km_value <= high)]
        if implausible and len(implausible) < len(rows):
            rows = [e for e in rows if low <= e.km_value <= high]
            for e in implausible:
                side = "below" if e.km_value < low else "above"
                reason = (f"{e.km_value:g} {unit} is {side} the physically plausible range "
                          f"for a {q} ({low:g} to {high:g} {unit})")
                set_aside.append({"value": float(e.km_value), "unit": getattr(e, "unit", unit),
                                  "reference_id": getattr(e, "reference_id", None),
                                  "reason": reason})
            listed = "; ".join(f"{s['value']:g} {unit} (BRENDA ref {s['reference_id'] or '?'})"
                               for s in set_aside)
            passed_over.append(f"{len(implausible)} physically implausible row(s) set aside "
                               f"(outside {low:g} to {high:g} {unit}): {listed}")
            log.append(f"{tier}: set aside {len(implausible)} of {len(entries)} row(s) as "
                       f"physically implausible for a {q}: {listed}")

    def prefer(keep, clause, line):
        """Keep the rows `keep` accepts when that leaves some but not all."""
        nonlocal rows
        kept_rows = [e for e in rows if keep(e)]
        if kept_rows and len(kept_rows) < len(rows):
            passed_over.append(clause(len(rows) - len(kept_rows), [e for e in rows if not keep(e)]))
            log.append(f"{tier}: kept the {len(kept_rows)} of {len(rows)} row(s) {line}")
            rows = kept_rows

    def names(found):
        return ", ".join(sorted({x for e in found for x in e}))

    # An inhibitor in the assay makes the constant an apparent one.
    prefer(lambda e: not _inhibited(e, rows),
           lambda n, out: (f"{n} row(s) measured with an inhibitor or effector present "
                           f"({names(_inhibited(e, rows) for e in out)}: apparent constants) "
                           "passed over for rows measured without one"),
           "measured without an inhibitor or other effector in the assay")

    controls = [e for e in rows if not _treated_arm(e, rows)]
    if controls and len(controls) < len(rows):
        treated = [e for e in rows if _treated_arm(e, rows)]
        added = sorted({x for e in treated for x in _added_compounds(e, rows)})
        passed_over.append(f"{len(treated)} row(s) measured with {', '.join(added)} added "
                           "passed over for the same paper's control without it")
        log.append(f"{tier}: kept the {len(controls)} of {len(rows)} row(s) that are not the "
                   f"treated arm of a presence/absence experiment ({', '.join(added)})")
        rows = controls

    # An activating ion withdrawn is the control, not the enzyme's constant.
    prefer(lambda e: not _withdrawn_ions(e, rows),
           lambda n, out: (f"{n} row(s) measured without "
                           f"{names(_withdrawn_ions(e, rows) for e in out)} (the same paper's "
                           "minus-activator control) passed over for the rows with it"),
           "not measured with an activating ion withdrawn")

    if q == "ki":
        reversible = [e for e in rows if not _kitz_wilson(e)]
        if reversible and len(reversible) < len(rows):
            passed_over.append(f"{len(rows) - len(reversible)} Kitz-Wilson row(s) (the K_I of an "
                               "irreversible inactivation, not a reversible Ki) passed over")
            log.append(f"{tier}: kept the {len(reversible)} of {len(rows)} row(s) that are not "
                       "Kitz-Wilson inactivation constants")
            rows = reversible

    cited = [e for e in rows if getattr(e, "reference_id", None)]
    if cited and len(cited) < len(rows):
        passed_over.append(f"{len(rows) - len(cited)} row(s) with no BRENDA reference passed over")
        log.append(f"{tier}: kept the {len(cited)} of {len(rows)} row(s) that carry a reference")
        rows = cited

    wild = [e for e in rows if not _is_mutant(e)]
    if wild and len(wild) < len(rows):
        passed_over.append(f"{len(rows) - len(wild)} mutant row(s) passed over for wild-type ones")
        log.append(f"{tier}: kept the {len(wild)} of {len(rows)} row(s) not measuring a mutant")
        rows = wild

    # A paper's row labelled wild-type over its unlabelled row stating the
    # same conditions otherwise: human chymotrypsin, ref 769319, holds
    # "wild-type, pH 8" (0.575 mM / 22.8 1/s), mutants D236R and S242T, and
    # a bare "pH 8" row (0.304 / 10.9) of a construct the commentary does
    # not name; the bare row was carried (fourth round's review).
    prefer(lambda e: not _unlabelled_beside_wild_type(e, rows),
           lambda n, out: (f"{n} unlabelled row(s) passed over for the same paper's row labelled "
                           "wild-type under otherwise the same stated conditions"),
           "labelled wild-type where the same paper labels one")

    # Constructs (an isolated domain, a chimera, a modified or immobilised
    # enzyme, a cosolvent, another subtype) after native rows.
    prefer(lambda e: not row_form.construct_of(getattr(e, "conditions", None)),
           lambda n, out: (f"{n} row(s) measuring a construct or altered preparation ("
                           + "; ".join(sorted({row_form.construct_of(e.conditions) for e in out}))
                           + ") passed over for rows of the native enzyme"),
           "of the native enzyme (no construct, modification or cosolvent named)")

    if q == "km":
        prefer(lambda e: not row_form.half_saturation(getattr(e, "conditions", None)),
               lambda n, out: (f"{n} K0.5 / Hill row(s) (a cooperative half-saturation "
                               "constant, not a Michaelis-Menten Km) passed over for true Km rows"),
               "reporting a Michaelis-Menten Km rather than a K0.5")

    # What a Km may be paired with: every row that IS a candidate, before the
    # preference for rows stating both pH and temperature.
    pairable = list(rows)

    complete = [e for e in rows if _has_conditions(e)]
    partial = [e for e in rows if _has_any_condition(e)]
    stating_one = [e for e in partial if e not in complete]
    if (complete and len(stating_one) >= CONDITIONS_FEW
            and (len(complete) < CONDITIONS_FEW or len(stating_one) >= 3 * len(complete))
            and _outside(complete, stating_one)):
        # A few rows stating both, lying outside every row stating one of
        # them, are not better evidence than those rows: rabbit muscle
        # aldolase kept two outliers (Km 0.107 mM, kcat 4.87 1/s, ref 770643)
        # over ~20 wild-type aldolase A rows stating 30 C alone (0.0051-0.0138
        # mM, kcat 10-13 1/s), the textbook values (third round's review).
        passed_over.append(f"the {len(complete)} row(s) stating both pH and temperature lie "
                           f"outside every one of the {len(stating_one)} stating one of them, so "
                           f"those were kept too; {len(rows) - len(partial)} row(s) stating "
                           "neither passed over" if len(partial) < len(rows) else
                           f"the {len(complete)} row(s) stating both pH and temperature lie "
                           f"outside every one of the {len(stating_one)} stating one of them, so "
                           "those were kept too")
        log.append(f"{tier}: kept the {len(partial)} of {len(rows)} row(s) stating pH or "
                   "temperature: the few stating both lie outside the rest")
        rows = partial
    elif complete and len(complete) < len(rows) and _median_far(complete, rows):
        # The rows stating both lie, as a group, more than tenfold from the
        # candidate rows as a whole: pig kidney D-amino acid oxidase and
        # D-alanine, kcat 10-440 1/s for the four rows stating pH and
        # temperature (133-151 at 37 C, 440 at pH 8.5) beside 6.5-12.7 1/s
        # for the wild-type rows stating less, and the pair carried was 440
        # 1/s (fifth round of the real-values review). The median of every
        # candidate row is then the reference, and the rows are kept.
        passed_over.append(f"the {len(complete)} row(s) stating both pH and temperature lie, by "
                           f"their median, more than {PAIR_MAX_FOLD_FROM_PICK:g}-fold from the "
                           f"median of the {_paper_median(rows)[1]} papers' rows, so the rows "
                           "stating less were kept too")
        log.append(f"{tier}: kept all {len(rows)} row(s): the rows stating both pH and "
                   "temperature lie far from the rest")
    elif complete and len(complete) < len(rows):
        # Their values are said: mouse AChE's other wild-type kcat rows
        # (2330 and 2333 1/s, ref 652016, no conditions) are 9-fold above
        # the carried 250 1/s, and nothing said so (fourth round's review).
        dropped = sorted({float(e.km_value) for e in rows if e not in complete})
        shown = ", ".join(f"{v:g}" for v in dropped[:4]) + (" ..." if len(dropped) > 4 else "")
        passed_over.append(f"{len(rows) - len(complete)} row(s) not stating both pH and "
                           f"temperature passed over ({shown} {getattr(rows[0], 'unit', '') or ''})"
                           .replace(" )", ")"))
        log.append(f"{tier}: kept the {len(complete)} of {len(rows)} row(s) stating both pH "
                   "and temperature")
        rows = complete
    elif not complete and partial and len(partial) < len(rows):
        # No row states both: one stating either is still a better-described
        # measurement than one stating neither (the order evidence_rank's
        # assay-completeness axis uses: complete > partial > absent).
        # Their values are said, as above: human HMG-CoA reductase's Km of
        # 0.07 mM (ref 667627, the Ki's own paper) went unmentioned beside
        # the 0.6 mM carried (fifth round of the real-values review).
        dropped = sorted({float(e.km_value) for e in rows if e not in partial})
        shown = ", ".join(f"{v:g}" for v in dropped[:4]) + (" ..." if len(dropped) > 4 else "")
        passed_over.append(f"{len(rows) - len(partial)} row(s) stating neither pH nor "
                           f"temperature passed over ({shown} "
                           f"{getattr(rows[0], 'unit', '') or ''}, and no row states both)"
                           .replace(" ,", ","))
        log.append(f"{tier}: no row states both pH and temperature; kept the {len(partial)} "
                   f"of {len(rows)} row(s) stating one of them")
        rows = partial

    if len(rows) < 2 or not relatedness_by_organism:
        # In one organism the frontier's remaining axis is the variant
        # STATEMENT (an explicit "wild-type" beats a row saying nothing),
        # and applying it there shrank Escherichia coli beta-lactamase and
        # ampicillin kcat to the two rows of mutagenesis papers that write
        # "wild-type enzyme" (90.7 and 3660 1/s), out of 13 rows stating pH
        # and temperature (live, 2026-11-11). Steps 2 and 3 already prefer
        # complete conditions and non-mutants; a row saying nothing about
        # the protein is the ordinary case (`_partition_variants`), not a
        # weaker one, so in one organism every remaining row is a candidate.
        kept = list(rows)
    else:
        # Across organisms the frontier is what ranks the closer relative
        # first (ADR 0024, relatedness_depth), and it stays.
        kept = evidence_rank.frontier(rows, requested_organism, relatedness_by_organism)
        for line in evidence_rank.describe_discards(
            rows, kept, requested_organism, relatedness_by_organism
        ):
            log.append(f"{tier}: {line}")
        if len(kept) < len(rows):
            passed_over.append(f"{len(rows) - len(kept)} row(s) another row beats on every "
                               "evidence axis passed over")
            log.append(f"{tier}: {len(kept)} of {len(rows)} row(s) are non-dominated")

    pick_from = kept
    paired = None
    matched = None
    if prefer_row:
        matched = next((e for e in pairable if _is_row(e, prefer_row)), None)
        if matched is not None:
            pick_from = [matched]
            log.append(f"{tier}: took the row of BRENDA ref {_ref(matched)} measured under the "
                       "same stated conditions as the paired constant's row")
        else:
            log.append(f"{tier}: the paired row asked for is not among the candidate rows; "
                       "choosing independently")
    elif prefer_reference:
        same_paper = [e for e in kept if getattr(e, "reference_id", None) == str(prefer_reference)]
        if same_paper:
            pick_from = same_paper
            paired = str(prefer_reference)
            log.append(f"{tier}: {len(same_paper)} row(s) from BRENDA ref {paired}, the paper "
                       "the paired constant came from; choosing among those")
        else:
            log.append(f"{tier}: no remaining row is from BRENDA ref {prefer_reference}, the "
                       "paired constant's paper; the two constants come from different papers")

    chosen, even = _median_row(pick_from)
    unit_slip = None
    ph_series = None
    if even and matched is None and len(pick_from) >= 2:
        unit_slip = _unit_slip(pick_from, entries)
        if unit_slip is not None:
            chosen = unit_slip[0]
        else:
            ph_series = _middle_ph_series(pick_from)
            if ph_series is not None:
                chosen = ph_series[0]
    values = [e.km_value for e in kept]
    lo, hi = min(values), max(values)
    fold = (hi / lo) if lo > 0 and hi != lo else None
    wide = bool(fold is not None and fold > WIDE_SPREAD_FOLD)

    unit = getattr(chosen, "unit", None) or ""
    n = len(pick_from)
    if matched is not None:
        how = (f"the row of BRENDA ref {_ref(chosen)} measured under the same stated conditions "
               f"({chosen.conditions or 'none stated'}) as the paired constant's row from that "
               "paper, so the two were measured together")
    elif n == 1 and paired:
        how = f"the one remaining row from BRENDA ref {paired}, the paper the paired constant came from"
    elif n == 1:
        how = "the only row remaining"
    elif unit_slip is not None:
        slipped = unit_slip[1]
        how = (f"one of the two middle values of the {n} remaining rows, which differ "
               f"{unit_slip[2]:.3g}-fold ({slipped.km_value:g} {getattr(slipped, 'unit', '') or ''}, "
               f"BRENDA ref {_ref(slipped)}): a factor of a thousand between rows stating the same "
               "conditions is the signature of a unit slip (mM written for µM, or per minute for "
               "per second), so the one lying with the other rows measured on this compound "
               f"(median {unit_slip[3]:g}) was taken and the other is a probable error")
    elif ph_series is not None:
        other = ph_series[1]
        how = (f"one of the two middle values of the {n} remaining rows, which are one paper's "
               f"rows differing only in pH (pH {chosen.assay_ph:g} against pH {other.assay_ph:g}, "
               f"{other.km_value:g} {getattr(other, 'unit', '') or ''}); the row nearest "
               f"pH {PHYSIOLOGICAL_PH:g} was taken")
    elif even:
        how = (f"the lower of the two middle values of the {n} remaining rows"
               + (f" from BRENDA ref {paired}, the paper the paired constant came from"
                  if paired else "")
               + " (a median row, so the value is one real measurement, not an average)")
        ordered = sorted(pick_from, key=lambda e: e.km_value)
        upper = ordered[len(ordered) // 2]
        mine, theirs = _assay_substrate(chosen.conditions), _assay_substrate(upper.conditions)
        if mine and theirs and mine != theirs:
            # ACE and captopril, ref 650001: 1e-05 mM on Abz-SDK(Dnp)P-OH and
            # 4.6e-05 mM on Abz-FRK(Dnp)P-OH, wild-type both (fourth round).
            how += (f"; the two middle rows differ in the assay substrate ({mine} against "
                    f"{theirs}, {upper.km_value:g} {getattr(upper, 'unit', '') or ''}), which is what "
                    "separates them, so the choice between them is not one the evidence makes")
    else:
        how = (f"the median of the {n} remaining rows"
               + (f" from BRENDA ref {paired}, the paper the paired constant came from"
                  if paired else "")
               + " (an actual row, so the value is one real measurement, not an average)")
    because = f"{chosen.km_value:g} {unit} (BRENDA ref {_ref(chosen)}) is {how}"
    if fold is not None:
        because += f"; the {len(kept)} remaining rows span {lo:g} to {hi:g} {unit}"
        if wide and unit_slip is None:
            because += (f", a {fold:.3g}-fold spread: the literature disagrees by more than "
                        f"{WIDE_SPREAD_FOLD:g}-fold, so this one value hides most of what is known")
    if passed_over:
        because += (f"; of the {len(entries)} candidate rows (after the organism, substrate, "
                    "isoform and variant checks): " + "; ".join(passed_over))
    notes = _row_notes(chosen, q)
    others = [e for e in pairable if getattr(e, "reference_id", None) != chosen.reference_id
              and isinstance(getattr(e, "km_value", None), (int, float)) and e.km_value > 0]
    if len(others) >= 2 and chosen.km_value and chosen.km_value > 0:
        lo_o, hi_o = min(e.km_value for e in others), max(e.km_value for e in others)
        far = max(chosen.km_value / hi_o, lo_o / chosen.km_value)
        if far > PAIR_MAX_FOLD_FROM_PICK:
            # Human DHODH and dihydroorotate: 0.29 mM and 0.78 1/s (ref
            # 762769, measured with coenzyme Q0 as acceptor) carried as the
            # only rows stating pH and temperature, 20-70x from the other
            # papers' rows (third round's review). Said, not hidden.
            notes.append(f"it lies {far:.3g}-fold outside the {len(others)} other papers' rows "
                         f"({lo_o:g} to {hi_o:g} {unit}), which were passed over for stating "
                         "less: an outlier of one paper, so read it before relying on it")
    if notes:
        because += "; what the carried row is: " + "; ".join(notes)
    log.append(f"{tier}: chose {because}")
    if wide:
        log.append(f"{tier}: WIDE SPREAD -- the rows chosen from span {fold:.3g}-fold")
    if detail is not None:
        detail.update(
            chosen_because=because,
            set_aside=set_aside,
            spread_fold=fold,
            wide_spread=wide,
            candidate_references=sorted({str(e.reference_id) for e in kept
                                         if getattr(e, "reference_id", None)}),
            row_notes=notes,
            row_isoform=_row_isoform_or_none(chosen),
            row_uniprot=_own_cell(chosen),
            pairable=_score_frontier(pairable, requested_organism),
        )

    _report_preparation(chosen, log, tier, quantity)
    if len(kept) < 2:
        # One row is its own frontier. Returned as a list of one rather
        # than empty: an ensemble over a single measurement is a
        # legitimate (if narrow) ensemble, and an empty list here would
        # read downstream as 'nothing was resolved'.
        return chosen, None, list(kept)
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
    return chosen, _tie_of(kept, chosen), list(kept)


def _state_the_form(chosen: dict, best, asked: str | None, log, tier) -> None:
    """Say so when the row carried names the compound more precisely than
    the request did.

    A request naming no stereochemistry ("lactate", "glucose") matches the
    rows of every form BRENDA writes ("(S)-lactate", "beta-D-glucose";
    `brenda_client.substrate_matches`), and the parser keeps BRENDA's name
    on each. The report states the compound the user typed beside the
    number, so without this sentence a "(R)-lactate" row would be cited as
    "lactate" with nothing saying which form was measured (found in review,
    2026-11-11). Spelling alone ("acetyl thiocholine") is not a different
    form and is not mentioned."""
    measured = getattr(best, "substrate", None)
    if not asked or not measured or not getattr(best, "substrate_verified", True):
        return
    if measured.strip().lower() == asked.strip().lower() or not substrate_matches(measured, asked):
        return
    if substrate_matches(asked, measured):  # the same compound, spelled otherwise
        return
    clause = (f"BRENDA names this row's compound {measured!r}, a stated form of the "
              f"{asked!r} asked for")
    if chosen.get("chosen_because"):
        chosen["chosen_because"] += f"; {clause}"
    log.append(f"{tier}: {clause}")


def _tie_of(kept, chosen):
    """`find_tie`, with its reason saying how THIS resolver broke the tie.

    selection_tie.find_tie's sentence says the value "was chosen by taking
    the lowest". That was true of `min()` and is not of the median row, and
    the sentence reaches every report as the constant's `chosen_because`
    (caterva/studio/adapters/constants.py), so it is rewritten here rather
    than left to describe a rule that no longer runs."""
    tie = find_tie(kept, chosen)
    if tie is None:
        return None
    spread = f"{tie.low:g} to {tie.high:g}" + (
        f", a {tie.fold_range:.3g}-fold range" if tie.fold_range is not None else "")
    return tie.model_copy(update={"reason": (
        f"{len(kept)} rows were equally well evidenced -- no row beats another on assay "
        f"completeness, what it states about the protein, and organism match -- and their "
        f"values span {spread}. The value returned is the median row of those, an actual "
        "measurement with its own reference rather than an average. That spread is "
        "disagreement in the literature, not a measurement uncertainty, and the alternatives "
        "are listed so it can be read as such."
    )})


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
            # The row's compound, as the parser labels it: for a request
            # naming a substrate, that name on every row it matched; for a
            # request naming none, the row's own compound cell, so the
            # frontier holds rows of every substrate the table has. Read by
            # the agents' assay-window re-selection, which can move to
            # another substrate's row only in the second case and says so
            # (caterva/agents/scouts.py). In the first case the label is the
            # name asked for, or BRENDA's own when the row was matched through
            # a stereo descriptor ("(S)-lactate" for "lactate"); since
            # 2026-11-11 the whole compound is matched
            # (brenda_client.substrate_matches), so the LDH turnover page's
            # phenylpyruvate rows (94.7 and 6467 1/s, ref 761568) no longer
            # read "pyruvate".
            "substrate": getattr(entry, "substrate", None),
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
            # The isoform the row measured, by its words or its own UniProt
            # cell (`_row_isoform`): "IDH1" for an O75874 row whose words name
            # none. Read by `caterva compose --isoform`, which otherwise
            # judged rows by their words alone and said a row naming IDH1 by
            # accession "names no isoform" (ADR 0182, second round).
            "isoform": _row_isoform_or_none(entry),
            # The row's OWN UniProt cell (never the fallback accession), so
            # two rows naming different proteins only by accession -- outside
            # the enzyme index (mushroom tyrosinase C7FF04, C7FF05) -- are
            # not paired or combined as one protein's.
            "uniprot": _own_cell(entry),
            # The isoform the row names ITSELF (words or own UniProt cell),
            # not read from its paper's other entries: what a spread may set
            # a row aside by (caterva.compose.export.Measurement).
            "isoform_own": _isoform_own(entry),
            # A row no protein can be read off (`_mark_unattributed`): not
            # taken as the isoform asked for by `caterva compose --isoform`.
            "unattributed": bool(getattr(entry, "unattributed", False)),
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


def _row_isoform(entry, isoform=None):
    """The isoform a row measured: what its commentary names, else what its
    OWN UniProt cell names (`_isoform_from_accession`). Raises ImportError
    where the caterva package is not importable, as `_isoform_of` does.

    The commentary alone missed BRENDA's own statement: "60.4 | D-glucose |
    Homo sapiens | P35557 | wild type enzyme ..." (ref 703624) named no
    isoform in words and was carried as HK2's kcat, and P35557 is
    glucokinase; "P20815, Q9HB55" (CYP3A5, CYP3A43) was carried as CYP2B6's
    Ki (ref 764467).

    A cell listing SEVERAL proteins says only that the paper concerns them:
    BRENDA gives one reference's accessions on each of its rows (human MAO,
    "P21397,P27338", MAO-A and MAO-B). Such a row names none of them when
    `isoform` (or, with no isoform given, any isoform) is among them, and
    names the others -- another isoform's -- when it is not."""
    named = _isoform_of(getattr(entry, "conditions", None))
    if named:
        return named
    # "heart phosphorylase I and III" for rabbit muscle glycogen
    # phosphorylase: a tissue's enzyme is that tissue's isoform (fifth round).
    tissue = row_form.tissue_isoform_of_row(getattr(entry, "ec_number", None),
                                            getattr(entry, "conditions", None))
    if tissue:
        return tissue
    from_cell = _isoform_from_accession(entry)
    if not from_cell and not _cell_is_read(entry):
        # Neither its words nor its own cell: the isoform(s) its paper's
        # other entries on the page name (`_paper_isoform`), if any, read as
        # a cell is below. Ref 722237's "67.6 | D-glucose | Homo sapiens |
        # - | wild-type, 37°C" is glucokinase's by its paper's synonyms, and
        # was HK2's kcat; ref 734041's ampicillin rows, a paper naming only
        # NDM variants, were TEM-1's.
        from_cell = getattr(entry, "paper_isoform", None)
    if not from_cell or " and " not in from_cell:
        return from_cell
    if isoform is None or any(_same_isoform(part, isoform) for part in from_cell.split(" and ")):
        return None
    return from_cell


def _same_isoform(a, b):
    """Whether two isoform names name one isoform, by caterva.bind.core's
    `same_isoform`: the comparison `caterva compose --isoform` and `caterva
    bind --isoform` use. This held its own copy until 2026-09-30; the copies
    agreed only while nothing changed either. Raises ImportError where the
    caterva package is not importable, as `_isoform_of` does, and is only
    reached after `_isoform_of` has succeeded."""
    from caterva.bind.core import same_isoform
    return same_isoform(a, b)


def _partition_isoform(entries, isoform, log, where, wild_first=False):
    """`(rows, matched, refused_isoforms)` for a request for one isoform.

    Rows naming the isoform win. Failing those, rows naming no isoform are
    kept (whether they measured it is unknown, and the log says so). Failing
    those too, every row measured another isoform: `rows` is empty and
    `refused_isoforms` names what exists. The same three cases, in the same
    order, as `caterva compose --isoform` (caterva/compose/isoform.py).

    The second round's review (2026-11-12):

    - A row names the isoform by its words, its own UniProt cell or the
      other entries of its paper (`_row_isoform`).
    - With `wild_first` (no mutant asked for, variants not allowed), the
      three cases are decided on the rows not measuring a variant first:
      PKM2's kcat was refused as "every row measured a variant" because the
      one row whose cell names PKM (P14618) is the mutant PKM2 G415R, while
      ref 674499's wild-type rows name no isoform.
    """
    try:
        named = [(e, _row_isoform(e, isoform)) for e in entries]
        if wild_first:
            wild = [(e, iso) for e, iso in named if not _is_variant_row(e, iso, isoform)]
            if wild and len(wild) < len(named):
                rows, matched, _ = _isoform_tiers(wild, isoform, len(entries), log, where)
                if rows:
                    return rows, matched, []
        rows, matched, refused = _isoform_tiers(named, isoform, len(entries), log, where)
    except ImportError:
        log.append(f"isoform {isoform!r} asked for, but caterva's isoform reader is not "
                   f"importable here, so {where} rows were NOT filtered by isoform")
        return entries, False, []
    return rows, matched, refused


def _is_variant_row(entry, iso, isoform) -> bool:
    """A row `_partition_variants` would withhold, an isozyme row of the
    isoform asked for excepted."""
    verdict = getattr(entry, "variant", None)
    if verdict is None or verdict.status != "variant":
        return False
    return not (verdict.kind == "isozyme" and _same_isoform(iso, isoform))


class _Refused(list):
    """The isoforms refused, and how many rows naming none went with them."""
    unnamed = 0


#: Rows naming another isoform, at least this many and outnumbering the rows
#: naming none, make those rows the other isoform's field, not the asked one's.
UNNAMED_AMONG_OTHERS_MIN = 2


#: Rows naming the isoform asked for are set aside for the rows naming none
#: when every one lies further than this outside the span of at least
#: `ISOFORM_OUTLIER_MIN_UNNAMED` rows naming none: a name is evidence of the
#: protein, not of the number.
ISOFORM_OUTLIER_FOLD = 100.0
ISOFORM_OUTLIER_MIN_UNNAMED = 2


def _lists_among_several(entry, isoform=None) -> bool:
    """Whether a row cannot be attributed to one protein: its own UniProt
    cell lists two or more accessions, its words name none, and a row of its
    paper names a protein in its words (`_mark_unattributed`)."""
    return bool(getattr(entry, "unattributed", False))


def isoform_rows_outlying(matching_values, unnamed_values, fold=ISOFORM_OUTLIER_FOLD):
    """Whether every value of the rows naming the isoform lies more than
    `fold` outside the span of the rows naming none. "DPP4 inhibited by
    sitagliptin": the gene symbol was read as --isoform DPP4, and the one
    paper whose rows name P27487 (ref 665551) gave kcat 279000 1/s against
    20-87 1/s for every wild-type row naming no isoform; it was carried with
    "scale: all numbers possible" (fourth round of the real-values review)."""
    low = [v for v in unnamed_values if v and v > 0]
    high = [v for v in matching_values if v and v > 0]
    if len(low) < ISOFORM_OUTLIER_MIN_UNNAMED or not high:
        return False
    lo, hi = min(low), max(low)
    return all(v > hi * fold or v < lo / fold for v in high)


def isolated(values, fold=ISOFORM_OUTLIER_FOLD) -> list:
    """The indexes of `values` lying more than `fold` from every other value,
    among at least three: a row no other row comes near. DPP4's kcat rows for
    Gly-Pro-4-nitroanilide in human are 20, 24, 87 and 279000 1/s; the last
    (ref 665551, naming P27487) was the one an isoform request could reach
    first, and pairing carried it."""
    vals = [float(v) if v is not None else 0.0 for v in values]
    if sum(1 for v in vals if v > 0) < 3:
        return []
    out = []
    for i, v in enumerate(vals):
        if v <= 0:
            continue
        others = [w for j, w in enumerate(vals) if j != i and w > 0]
        if others and all(max(v / w, w / v) > fold for w in others):
            out.append(i)
    return out


def _isoform_tiers(named, isoform, total, log, where):
    lone = isolated([e.km_value for e, _ in named])
    if lone:
        listed = ", ".join(f"{named[i][0].km_value:g} (BRENDA ref "
                           f"{getattr(named[i][0], 'reference_id', None) or '?'})" for i in lone)
        log.append(f"Set aside {len(lone)} {where} row(s) lying more than "
                   f"{ISOFORM_OUTLIER_FOLD:g}-fold from every other row ({listed}) before choosing "
                   f"among the rows naming {isoform}: a probable error, which a name must not carry")
        named = [x for i, x in enumerate(named) if i not in lone]
    matching = [e for e, iso in named if _same_isoform(iso, isoform)]
    unnamed = [e for e, iso in named if iso is None]
    # A row naming no protein in its words whose own UniProt cell lists the
    # isoform among several is not that isoform's: CYP2D6 and fenthion, ref
    # 706823, "P10632, P05177, P10635, P20813, P11509" (CYP2C8, CYP1A2,
    # CYP2D6, CYP2B6, CYP2A6) beside the paper's rows naming CYP2C19, CYP2C9,
    # CYP1A1 and CYP3A4, was carried as CYP2D6's Km while the substrate note
    # said the Km would stay a placeholder (fifth round's review).
    listing = [e for e in unnamed if _lists_among_several(e, isoform)]
    if listing and not matching:
        unnamed = [e for e in unnamed if e not in listing]
        refs = sorted({str(getattr(e, "reference_id", None) or "?") for e in listing})
        log.append(f"Set aside {len(listing)} {where} row(s) of BRENDA ref {', '.join(refs)}: "
                   f"each lists {isoform}'s accession among several in its UniProt column and "
                   f"names no protein in its words, so whose constant it is cannot be told")
        if not unnamed and not [iso for _, iso in named if iso]:
            refused = _Refused([f"rows that cannot be attributed (BRENDA ref {', '.join(refs)} "
                                f"lists {isoform} among several proteins and names none of them "
                                "in its words)"])
            return [], False, refused
    if matching and isoform_rows_outlying([e.km_value for e in matching],
                                          [e.km_value for e in unnamed]):
        listed = ", ".join(f"{e.km_value:g} (BRENDA ref {getattr(e, 'reference_id', None) or '?'})"
                           for e in matching)
        log.append(f"The {len(matching)} {where} row(s) naming {isoform} ({listed}) lie more than "
                   f"{ISOFORM_OUTLIER_FOLD:g}-fold outside every one of the {len(unnamed)} naming "
                   f"none ({min(e.km_value for e in unnamed):g} to "
                   f"{max(e.km_value for e in unnamed):g}): set aside as a probable error, and the "
                   f"rows naming none kept")
        return unnamed, False, []
    if matching:
        log.append(f"Kept the {len(matching)} of {total} {where} row(s) measuring {isoform}")
        return matching, True, []
    others = [iso for _, iso in named if iso]
    # A row whose paper names the asked isoform among several is ambiguous,
    # not silent: it is not set aside with the field (an NDM-12 request and
    # ref 734041, a paper naming NDM-4 and NDM-12).
    def among_its_paper(entry):
        paper = getattr(entry, "paper_isoform", None) or ""
        try:
            return any(_same_isoform(part, isoform) for part in paper.split(" and ") if part)
        except ImportError:
            return False
    if (unnamed and len(others) >= UNNAMED_AMONG_OTHERS_MIN and len(others) > len(unnamed)
            and not any(among_its_paper(e) for e in unnamed)):
        # The third round's review: HK2's kcat was ref 672188's "38 |
        # D-glucose | - | wild-type enzyme", a glucokinase Y214C paper, among
        # human D-glucose kcat rows every one of which that names a protein
        # names GCK; ABL1's Km and kcat were ref 663196's poly(Glu4-Tyr) rows,
        # a Csk paper, among rows naming only Csk and Chk. Where the rows that
        # do name a protein all name others and outnumber the rest, a row
        # naming none is far likelier theirs than the asked isoform's.
        try:
            listed = row_form.distinct_isoforms(others, _same_isoform)
        except ImportError:
            listed = sorted(set(others))
        log.append(f"No {where} row names {isoform}; the {len(others)} naming a protein name "
                   f"only {', '.join(listed)}, so the {len(unnamed)} naming none are not taken "
                   f"as {isoform}'s")
        refused = _Refused(listed)
        refused.unnamed = len(unnamed)
        return [], False, refused
    if unnamed:
        log.append(f"No {where} row names {isoform}; kept the {len(unnamed)} naming no isoform, "
                   f"which may or may not have measured it")
        return unnamed, False, []
    return [], False, sorted({iso for _, iso in named if iso})


def _isoform_withheld_result(isoform, available, log):
    unnamed = getattr(available, "unnamed", 0)
    if not unnamed:
        log.append(f"Every candidate row measured another isoform ({', '.join(available)}), "
                   f"not {isoform}: a constant of another isoform is a different protein's")
    return KineticResult(
        found=False,
        source="isoform_withheld",
        isoforms_available=list(available),
        isoform_unnamed_withheld=unnamed,
        search_log=log,
    )


def _ki_mode():
    """caterva.compose.ki_mode, where the one ranking of Ki rows by inhibition
    mode lives (`caterva compose` chooses with it too). Imported lazily, as
    `_isoform_of` imports caterva.bind.core. Raises ImportError where the
    caterva package is not importable."""
    from caterva.compose import ki_mode
    return ki_mode


def _mode_asked(inhibition_mode, quantity, log, name="inhibition_mode"):
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
        raise ValueError(f"{name} must be one of {', '.join(modes)}; "
                         f"got {inhibition_mode!r}")
    if quantity != "ki":
        log.append(f"inhibition mode {inhibition_mode!r} not applied: it chooses among Ki "
                   f"rows, and this is a {quantity} lookup")
        return None
    return inhibition_mode


def _naming_no_isoform(pool, isoform_matched, allow_variants, isoform=None):
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
        unnamed = [e for e in pool if _row_isoform(e, isoform) is None]
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


def _rank_by_mode(entries, pool, isoform_matched, allow_variants, mode, substrate, isoform,
                  log, where):
    """`(ranked, kept, stated)`: the mode step, over the rows the isoform and
    variant steps kept (`entries`) and, behind them, the rows naming no
    isoform that `_naming_no_isoform` puts back. `ranked` is every row the
    step ranked, which `_mechanism_evidence` reads; `kept` and `stated` are
    `_partition_mode`'s. One function for the call asked for a mode and for
    `_mode_default`, so the row the latter names is the row the former
    returns, not a second reading of the rule."""
    ranked = entries + _naming_no_isoform(pool, isoform_matched, allow_variants, isoform)
    kept, stated = _partition_mode(ranked, mode, substrate, isoform, isoform_matched, log, where)
    return ranked, kept, stated


def _mode_default(entries, pool, isoform_matched, allow_variants, mode, substrate, isoform,
                  where, tier, organism, quantity, relatedness_by_organism=None):
    """`KineticResult.mode_default`: what this call, asked for `mode`, would
    return from the same rows. It takes the steps that call takes after the
    variant step, which is the only place the two calls part: the mode step
    (`_rank_by_mode`), then `_best_evidenced` over what it kept, with the
    same tier and relatedness. Its log lines are discarded, as
    `_evidence_only` discards its own: they describe a choice this call did
    not make."""
    _, kept, stated = _rank_by_mode(entries, pool, isoform_matched, allow_variants, mode,
                                    substrate, isoform, [], where)
    if not kept:
        return ModeDefault(mode=mode, model_substrate=substrate, modes_available=stated)
    best, _, _ = _best_evidenced(kept, [], tier, organism, relatedness_by_organism,
                                 quantity=quantity)
    return ModeDefault(mode=mode, model_substrate=substrate,
                       row=_score_frontier([best], organism)[0])


def _compare_mode_asked(compare_mode, inhibition_mode, quantity):
    """The mode to say what the call asked for it would return, or None.

    Checked as `_mode_asked` checks a mode: one no model is of is refused
    with ValueError, and for anything but a Ki it has nothing to change, so
    it is not applied. It is refused beside `inhibition_mode`: a call ranked
    by one mode cannot also be the call that ranks by none."""
    if compare_mode is None:
        return None
    if inhibition_mode is not None:
        raise ValueError(f"compare_mode is for a call asked for no inhibition mode; this one "
                         f"was asked for {inhibition_mode!r}")
    # Named as the argument the caller passed, so a bad compare_mode is not
    # reported as a bad inhibition_mode the caller never sent.
    return _mode_asked(compare_mode, quantity, [], name="compare_mode")


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
        if (verdict is not None and verdict.status == "variant" and verdict.kind == "isozyme"
                and _names_the_sole_protein(entry)):
            # "isoform CELA1" for pig pancreatic elastase: the only protein
            # the EC holds in the organism is the enzyme itself.
            usable.append(entry)
            continue
        if (verdict is not None and verdict.status == "variant"
                and not (keep_isozymes and verdict.kind == "isozyme")):
            # An isozyme row is kept when it is the isozyme that was asked
            # for: then it is the enzyme, not a variant of it.
            withheld.append(entry)
        else:
            usable.append(entry)
    return usable, withheld


def _names_the_sole_protein(entry) -> bool:
    try:
        reading = _isoform_of(getattr(entry, "conditions", None))
    except ImportError:
        return False
    return row_form.is_sole_protein(getattr(entry, "ec_number", None),
                                    getattr(entry, "organism", None), reading)


def _mutations_of(text) -> set:
    """The point mutations a commentary names, one per substitution:
    "mutant enzyme R132H" gives {"R132H"}, "R132H/S280F" both."""
    return {m.upper() for m in re.findall(r"(?<![A-Za-z0-9])[A-Z]\d{1,4}[A-Z](?![A-Za-z0-9])",
                                          text or "")}


def _partition_mutant(entries, mutation, log, where):
    """The rows measuring `mutation` (every substitution of "R132H/S280F"),
    and only those: a mutant asked for is never answered with wild-type rows,
    and never with another mutant's.

    "IDH1 R132H" carried wild-type isocitrate rows (ref 760535) as GROUNDED
    while BRENDA holds the R132H rows of that same paper."""
    wanted = {m.strip().upper() for m in re.split(r"[/,+\s]+", mutation) if m.strip()}
    kept = [e for e in entries if wanted <= _mutations_of(getattr(e, "conditions", None))]
    if kept:
        log.append(f"Kept the {len(kept)} of {len(entries)} {where} row(s) measuring the mutant "
                   f"{mutation}")
    else:
        log.append(f"No {where} row measures the mutant {mutation}; the {len(entries)} row(s) of "
                   "the enzyme are not used for it")
    return kept


def _mutant_not_found_result(mutation, log):
    return KineticResult(
        found=False,
        source="mutant_not_found",
        variant_candidates_available=[mutation],
        search_log=log,
    )


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
    compare_mode: str | None = None,
    prefer_reference: str | None = None,
    prefer_row: dict | None = None,
    mutation: str | None = None,
    exclude_references: "tuple | frozenset | None" = None,
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

    ``compare_mode`` is a model's mode sent WITHOUT ranking by it, with the
    model's ``model_substrate``: the answer is the one this call gives with
    no mode, row for row, and `mode_default` says what it would have
    returned asked for ``compare_mode``. `caterva compose --any-mode` sends
    it, so its report can name the row its default carries. Refused
    beside ``inhibition_mode``; not applied to anything but a Ki.

    ``prefer_reference`` is a BRENDA reference id: when a row from that
    paper survives every filter, the value is taken from that paper's rows
    (`_best_evidenced` step 5). `resolve_kinetic_pair` passes the Km's paper
    when it resolves the kcat, so the two constants of one model come from
    one measurement when the literature allows it.

    ``exclude_references`` are papers whose rows are not candidates:
    `resolve_kinetic_pair` sends a paper one of whose rows of the paired
    constant is a probable error (`probable_error_papers`).
    """
    table_label = QUANTITY_TABLE_LABELS.get(quantity, KM_TABLE_LABEL)
    quantity_upper = {"ki": "Ki", "kcat": "kcat"}.get(quantity, "Km")
    log = []
    mode = _mode_asked(inhibition_mode, quantity, log)
    compare = _compare_mode_asked(compare_mode, inhibition_mode, quantity)
    model_substrate = model_substrate or None

    log.append(f"BRENDA exact: {enzyme_ec}, {organism}, {substrate} ({quantity})")
    exact = _brenda_entries(
        enzyme_ec, organism, substrate, html_provider, uniprot_provider,
        taxon_id_provider, table_label=table_label,
    )
    if exclude_references and exact:
        excluded = {str(r) for r in exclude_references}
        kept = [e for e in exact if str(getattr(e, "reference_id", None)) not in excluded]
        if kept and len(kept) < len(exact):
            log.append(f"Set aside the {len(exact) - len(kept)} exact-match row(s) of BRENDA ref "
                       f"{', '.join(sorted(excluded))}: a row of that paper for the paired "
                       "constant lies more than 100-fold from every other row, a probable error, "
                       "so the paper supplies neither constant")
            exact = kept
    if exact:
        # An isoform asked for narrows the pool first, for the same reason
        # variants are removed before selection: min() over three isoforms'
        # rows picks a protein, not a value.
        pool = exact
        isoform_matched = False
        if isoform:
            exact, isoform_matched, other_isoforms = _partition_isoform(
                exact, isoform, log, "exact-match", wild_first=not allow_variants and not mutation)
            if not exact:
                return _isoform_withheld_result(isoform, other_isoforms, log)
        if mutation:
            exact = _partition_mutant(exact, mutation, log, "exact-match")
            if not exact:
                return _mutant_not_found_result(mutation, log)
        # Variant rows are removed BEFORE selection, not flagged after it.
        #
        # That ordering is the whole point. Selection is min(), point
        # substitutions are chosen precisely because they change the
        # kinetics, and they therefore sit in the tail a minimum reaches
        # into: in the AChE turnover fixture the lowest mutant kcat is
        # twelve times below the lowest wild-type one. Flagging afterwards
        # would attach a warning to a value that had already been selected
        # FOR being a mutant. See ADR 0029.
        if not allow_variants and not mutation:
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
            ranked, exact, stated = _rank_by_mode(
                exact, pool, isoform_matched, allow_variants, mode, model_substrate, isoform,
                log, "exact-match")
            if not exact:
                return _mode_withheld_result(mode, stated, log)
        # Asked for no mode with a model's mode to compare: the answer the
        # mode would have given, from these same rows (`ModeDefault`).
        mode_default = (_mode_default(exact, pool, isoform_matched, allow_variants, compare,
                                      model_substrate, isoform, "exact-match", "exact match",
                                      organism, quantity)
                        if compare else None)
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
        chosen = {}
        best, tie, frontier = _best_evidenced(
            exact, log, "exact match", organism, quantity=quantity,
            prefer_reference=prefer_reference, detail=chosen, prefer_row=prefer_row,
        )
        withheld_as_implausible = _implausible_withheld(best, exact, quantity, log, "exact match")
        if withheld_as_implausible is not None:
            return withheld_as_implausible
        _state_the_form(chosen, best, substrate, log, "exact match")
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
            mode_default=mode_default,
            mechanism_evidence=evidence,
            effector_contrasts=contrasts,
            form_mixtures=mixtures,
            organism_discrepancies=discrepancies,
            source_mixtures=source_mix,
            source_check_unavailable=source_unavailable,
            variant=best.variant,
            preparation=_preparation_of(best),
            selection_tie=tie,
            **chosen,
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
                acceptable, isoform, log, "cross-species",
                wild_first=not allow_variants and not mutation)
            if not acceptable:
                return _isoform_withheld_result(isoform, other_isoforms, log)
        if mutation:
            acceptable = _partition_mutant(acceptable, mutation, log, "cross-species")
            if not acceptable:
                return _mutant_not_found_result(mutation, log)
        if not allow_variants and not mutation:
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
            ranked, acceptable, stated = _rank_by_mode(
                acceptable, pool, isoform_matched, allow_variants, mode, model_substrate, isoform,
                log, "cross-species")
            if not acceptable:
                return _mode_withheld_result(mode, stated, log)
        relatedness_by_organism = {v.candidate_organism: v for v in verdicts}
        mode_default = (_mode_default(acceptable, pool, isoform_matched, allow_variants, compare,
                                      model_substrate, isoform, "cross-species", "cross-species",
                                      organism, quantity, relatedness_by_organism)
                        if compare else None)

        # Detect designed contrasts BEFORE reporting a winner. A value
        # returned while the other arm of its own experiment sits unmentioned
        # in the same pool is half an answer, and the reader cannot ask for
        # the other half without being told it exists.
        chosen = {}
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
            relatedness_by_organism,
            quantity=quantity,
            prefer_reference=prefer_reference,
            detail=chosen,
            prefer_row=prefer_row,
        )
        withheld_as_implausible = _implausible_withheld(best, acceptable, quantity, log, "cross-species")
        if withheld_as_implausible is not None:
            return withheld_as_implausible
        _state_the_form(chosen, best, substrate, log, "cross-species")
        evidence = (_mechanism_evidence(ranked, best, mode, model_substrate, isoform, log)
                    if mode else None)
        return KineticResult(
            found=True,
            value=best.km_value,
            unit=best.unit,
            organism=best.organism,
            source="brenda_cross_species",
            evidence_only=(_evidence_only(pool, allow_variants, "cross-species", organism, quantity,
                                          relatedness_by_organism)
                           if isoform or mode else []),
            mode_default=mode_default,
            mechanism_evidence=evidence,
            effector_contrasts=contrasts,
            form_mixtures=mixtures,
            organism_discrepancies=discrepancies,
            source_mixtures=source_mix,
            source_check_unavailable=source_unavailable,
            variant=best.variant,
            preparation=_preparation_of(best),
            selection_tie=tie,
            **chosen,
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


#: A paired row further than this from the constant's own independent pick
#: is not taken for the sake of pairing: human acetylcholinesterase's one
#: kcat row in the Km's paper was 7.18 1/s (ref 749746), 13-fold below the
#: median of 7.18, 93 and 6500 and ~1000-fold below the enzyme's known
#: turnover, and pairing carried it.
PAIR_MAX_FOLD_FROM_PICK = 10.0

#: The pH a paper's pH series is read at when it measured several pairs.
PHYSIOLOGICAL_PH = 7.4
#: The salt concentration (M) a paper's salt series is read at.
PHYSIOLOGICAL_SALT_M = 0.15

_SALT_IN = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(m?M)\s+(?:NaCl|KCl|LiCl|Na2SO4|NaClO4|K2SO4)\b")


def _salt_molar(conditions) -> "float | None":
    """The molar concentration of the monovalent salt a row's commentary
    states ("pH 5.0, 2.0 M NaCl" is 2.0), or None when it states none."""
    m = _SALT_IN.search(conditions or "")
    if not m:
        return None
    value = float(m.group(1))
    return value / 1000.0 if m.group(2) == "mM" else value


def _matched_pairs(km, kcat, substrate):
    """`(pairs, unresolvable)`: every (Km row, kcat row) of one paper measured
    under the same stated conditions, and the papers where rows of matching
    conditions hold several different values, so which Km goes with which
    kcat cannot be told (TEM-1 and ampicillin, ref 734041: seven Km and seven
    kcat rows with one commentary)."""
    pairs, unresolvable, _ = _matched_pairs_with_undescribed(km, kcat, substrate)
    return pairs, unresolvable


def _matched_pairs_with_undescribed(km, kcat, substrate):
    """`_matched_pairs`, and the papers whose matching Km and kcat rows were
    not considered because they state less (no pH or temperature) than the
    constants' own picks. Said, so "no paper holds a pair" is not claimed of
    a paper that does.

    A pair must state a pH (a temperature) only when BOTH picks state one:
    the model's description is no better than its less-described constant.
    Xanthine oxidase, ref 644648: a Km and a kcat with an artificial electron
    acceptor and no conditions, against two picks stating pH and temperature,
    are not carried. Mouse hexokinase, ref 758915: Km 0.42 and kcat 93.39
    (Hk2, O08528), neither stating pH or temperature, ARE carried over Km
    0.42 with another paper's kcat 53.2 (ref 674800) -- the Km pick states
    none, so pairing loses nothing and gains one paper's protein; so are
    horse liver ADH's Km 4.0 and kcat 123 "wild-type enzyme Adh1" (ref
    285647), the kcat pick's own paper, over a Km from another paper."""
    need_ph = km.assay_ph is not None and kcat.assay_ph is not None
    need_t = km.assay_temperature_c is not None and kcat.assay_temperature_c is not None

    def described(row, result):
        # "pH 4.u" states a pH, unreadably (row_form.garbled_ph).
        return ((not need_ph or row.get("ph") is not None
                 or row_form.garbled_ph(row.get("conditions")) is not None)
                and (not need_t or row.get("temperature_c") is not None))

    by_ref, all_by_ref = {}, {}
    for table, result in (("km", km), ("kcat", kcat)):
        for r in result.pairable or []:
            ref = r.get("reference_id")
            if not (ref and r.get("value")):
                continue
            all_by_ref.setdefault(str(ref), {"km": [], "kcat": []})[table].append(r)
            if described(r, result):
                by_ref.setdefault(str(ref), {"km": [], "kcat": []})[table].append(r)
    undescribed = []
    for ref, rows in sorted(all_by_ref.items()):
        here = by_ref.get(ref, {"km": [], "kcat": []})
        if any(row_form.same_measurement(k, c, substrate) for k in rows["km"] for c in rows["kcat"]) \
                and not any(row_form.same_measurement(k, c, substrate)
                            for k in here["km"] for c in here["kcat"]):
            undescribed.append(ref)
    pairs, unresolvable = [], []
    for ref, rows in sorted(by_ref.items()):
        if not rows["km"] or not rows["kcat"]:
            continue
        for k in rows["km"]:
            twins = [x for x in rows["km"] if row_form.same_measurement(k, x, substrate)]
            mates = [c for c in rows["kcat"] if row_form.same_measurement(k, c, substrate)]
            if not mates:
                continue
            if len(row_form.distinct_values(twins)) > 1 or len(row_form.distinct_values(mates)) > 1:
                if ref not in unresolvable:
                    unresolvable.append(ref)
                continue
            pairs.append((ref, k, mates[0]))
    return pairs, unresolvable, undescribed


def probable_error_papers(enzyme_ec, organism, substrate, html_provider, quantity, kwargs) -> dict:
    """{paper: value} for the papers one of whose rows of `quantity` lies more
    than ISOFORM_OUTLIER_FOLD from every other row (`isolated`), among the
    rows of the organism and substrate not measuring a variant.

    DPP4 and Gly-Pro-4-nitroanilide in human: ref 665551's wild-type kcat is
    279000 1/s against 20-87 1/s; the kcat was set aside, but the same
    paper's Km of 1.43 mM, ~10-fold above every other wild-type human row,
    was carried as "the row for DPP4" (fifth round of the real-values
    review). A paper with a probable error in one constant does not supply
    the other."""
    label = QUANTITY_TABLE_LABELS.get(quantity, KM_TABLE_LABEL)
    try:
        rows = _brenda_entries(
            enzyme_ec, organism, substrate, html_provider,
            kwargs.get("uniprot_provider") or enzyme_lookup.fetch_uniprot_accession,
            kwargs.get("taxon_id_provider") or enzyme_lookup.fetch_taxon_id,
            table_label=label)
    except Exception:  # noqa: BLE001 - a check that cannot run sets nothing aside
        return {}
    if kwargs.get("mutation"):
        # A mutant asked for is judged among that mutant's rows: IDH1 R132H's
        # paper 761477 was set aside for a wild-type row (fifth round).
        rows = _partition_mutant(rows, kwargs["mutation"], [], "probable-error check")
    elif not kwargs.get("allow_variants"):
        rows, _ = _partition_variants(rows, keep_isozymes=True)
    lone = isolated([e.km_value for e in rows])
    return {str(rows[i].reference_id): rows[i].km_value for i in lone
            if getattr(rows[i], "reference_id", None)}


def _is_dict_row(a, b) -> bool:
    """Whether two pairable row dicts are one row."""
    return (str(a.get("reference_id")) == str(b.get("reference_id"))
            and a.get("value") == b.get("value") and a.get("conditions") == b.get("conditions"))


def _with_clause(result, clause):
    if not result.chosen_because:
        # A result that gives no reason (a stand-in) is not given one here.
        return result
    because = result.chosen_because + "; " + clause
    # The reason only: the search log is the search's, and a caller's log
    # of a found value stays the lookup it made (test_science_agent_runner).
    return result.model_copy(update={"chosen_because": because})


def resolve_kinetic_pair(
    enzyme_ec: str,
    organism: str,
    substrate: str,
    html_provider: HtmlProvider = fetch_brenda_html,
    **kwargs,
) -> "tuple[KineticResult, KineticResult]":
    """`(km, kcat)` for one model: from one paper's matched rows when the
    literature holds them, else each constant's own best row.

    A Km and a kcat from two papers were measured on two preparations, often
    at two temperatures, so a pair measured together is better -- but only a
    pair that WAS measured together. Each constant is first chosen by the
    ordinary policy. Then, among the rows each could carry
    (`KineticResult.pairable`), a Km row and a kcat row are a pair when they
    come from one paper and state the same pH, temperature and remaining
    conditions (`row_form.same_measurement`): the same form of the enzyme,
    the same salt, the same additive. Rows of one paper at different pH
    (fumarase, ref 771047: Km at pH 9.0, kcat at pH 6.5) or with different
    salts (thrombin, ref 709074: Km in 200 mM NaCl, kcat in choline chloride)
    are not a pair. A paper whose matching rows hold several values cannot
    say which Km goes with which kcat, and is not paired from. A pair whose
    member lies more than PAIR_MAX_FOLD_FROM_PICK from that constant's own
    pick is not taken.

    Of the pairs left, one measured at an ordinary assay temperature
    (25-37 C) comes first, then the one nearest the two independent picks
    (on a log scale) is carried, and each result says so; with none, the independent
    picks stand and each result says why they were not paired.

    The page is fetched once: `html_provider` is wrapped in a cache for the
    duration of the call. Every other keyword goes to `resolve_kinetic_value`.
    """
    import functools
    import math

    page = functools.lru_cache(maxsize=None)(html_provider)
    kwargs.pop("quantity", None)
    kwargs.pop("prefer_reference", None)
    kwargs.pop("prefer_row", None)

    def resolve(quantity, row=None):
        return resolve_kinetic_value(enzyme_ec=enzyme_ec, organism=organism, substrate=substrate,
                                     html_provider=page, quantity=quantity, prefer_row=row,
                                     **kwargs)

    km = resolve("km")
    kcat = resolve("kcat")
    if not (km.found and kcat.found):
        return km, kcat

    # A paper with a probable error in one constant supplies neither.
    discredited, said = {}, {}
    for quantity, other in (("km", "kcat"), ("kcat", "km")):
        result = km if quantity == "km" else kcat
        cited = str(getattr(result.citation, "reference_id", None) or "")
        if not cited:
            continue
        errors = probable_error_papers(enzyme_ec, organism, substrate, page, other, kwargs)
        if cited in errors:
            again = resolve_kinetic_value(enzyme_ec=enzyme_ec, organism=organism,
                                          substrate=substrate, html_provider=page,
                                          quantity=quantity,
                                          **{**kwargs, "exclude_references": (cited,)})
            if again.found:
                note = (f"BRENDA ref {cited}'s row was not used: the same paper's "
                        f"{'kcat' if other == 'kcat' else 'Km'} ({errors[cited]:g}) lies more "
                        f"than {ISOFORM_OUTLIER_FOLD:g}-fold from every other row, a probable "
                        f"error, so that paper supplies neither constant (it gave "
                        f"{result.value:g} {result.unit or ''}".rstrip() + ")")
                discredited[cited] = errors[cited]
                said[quantity] = note
                again = _with_clause(again, note)
                if quantity == "km":
                    km = again
                else:
                    kcat = again
    if discredited:
        kwargs = {**kwargs, "exclude_references": tuple(discredited)}

        def resolve(quantity, row=None, _resolve=resolve):
            # A pair resolved again still says which paper was set aside.
            result = _resolve(quantity, row)
            return (_with_clause(result, said[quantity])
                    if quantity in said and result.found else result)

    one_isozyme = None
    if not kwargs.get("isoform"):
        rest = {k: v for k, v in kwargs.items() if k != "isoform"}
        km, kcat, one_isozyme = _one_isozyme(km, kcat, resolve_kinetic_value, dict(
            enzyme_ec=enzyme_ec, organism=organism, substrate=substrate,
            html_provider=page, **rest))

    def resolve(quantity, row=None, _resolve=resolve):
        # A pair keeps to the isozyme `_one_isozyme` settled on.
        if one_isozyme is None:
            return _resolve(quantity, row)
        return resolve_kinetic_value(enzyme_ec=enzyme_ec, organism=organism,
                                     substrate=substrate, html_provider=page,
                                     quantity=quantity, prefer_row=row,
                                     **{**kwargs, "isoform": one_isozyme[quantity]})

    pairs, unresolvable, undescribed = _matched_pairs_with_undescribed(km, kcat, substrate)

    def fold(value, pick):
        return max(value / pick, pick / value) if value > 0 and pick and pick > 0 else math.inf

    def protein(row):
        return _protein_of(row.get("isoform"), row.get("uniprot"))

    km_protein = _protein_of(km.row_isoform, km.row_uniprot)
    kcat_protein = _protein_of(kcat.row_isoform, kcat.row_uniprot)
    # A pair is one protein's: its two rows never name two.
    pairs = [(ref, k, c) for ref, k, c in pairs if not _other_protein(protein(k), protein(c))]

    def close(row, pick, pick_protein):
        # A pick that is another protein's than the pair is no reference for
        # it. Human carbonic anhydrase: the kcat pick was CA III's 13000 1/s
        # (P07451, ref 699246), the median of two rows of two isozymes, and
        # it vetoed ref 729384's CA II pair (Km 9.3 mM, kcat 1.4e6 1/s) as
        # "more than 10-fold from the picks" (third round's review).
        if fold(row["value"], pick.value) <= PAIR_MAX_FOLD_FROM_PICK:
            return True
        if not _other_protein(protein(row), pick_protein):
            return False
        # The pick is no reference for another protein's row, but that
        # protein's own rows are, and so is every other row of the
        # constant: mushroom tyrosinase's Km 26.1 mM (ref 746472, C7FF05)
        # rode in on its kcat's pairing, ~70-fold from the pick and more
        # than 10-fold from every one of 19 L-DOPA rows (0.17-1.5 mM), and
        # the report called it GROUNDED (fifth round of the real-values
        # review). With fewer than two rows of its own protein, the median
        # of the constant's other rows is the reference.
        rows = [r for r in (pick.pairable or []) if isinstance(r.get("value"), (int, float))
                and r["value"] > 0]
        own = [r for r in rows if protein(r) and not _other_protein(protein(r), protein(row))]
        if len(own) >= 2:
            ordered = sorted(r["value"] for r in own)
            return fold(row["value"], ordered[(len(ordered) - 1) // 2]) <= PAIR_MAX_FOLD_FROM_PICK
        # Two rows of two proteins are no bulk: either may be right, and the
        # pair of one protein is carried (third round's review); three or
        # more other rows are.
        others = sorted(r["value"] for r in rows if not _is_dict_row(r, row))
        return len(others) < 3 or fold(row["value"], others[(len(others) - 1) // 2]) \
            <= PAIR_MAX_FOLD_FROM_PICK

    near = [(ref, k, c) for ref, k, c in pairs
            if close(k, km, km_protein) and close(c, kcat, kcat_protein)]
    far = [p for p in pairs if p not in near]
    def outside_assay_range(row):
        # How far (degrees C) a pair's temperature lies outside the 25-37 C
        # of an ordinary assay. One paper's temperature series (bovine
        # trypsin and BAPNA, ref 678548: 5, 15, 25 and 35 C) is otherwise
        # settled by which rows the medians fell on: Km 0.26 at 25 C and
        # kcat 0.76 at 15 C made the 15 C pair the nearer.
        t = row.get("temperature_c")
        return 0.0 if t is None else max(0.0, 25.0 - float(t), float(t) - 37.0)

    def from_physiological_salt(row):
        # One paper's salt series is read as a series too, nearest the
        # ionic strength of a cell: HIV-1 protease, ref 648156, measured at
        # 0.1, 1.0 and 2.0 M NaCl; the 2.0 M pair was carried for being 0.1
        # pH unit nearer 7.4 than the 1.0 M one (fourth round's review).
        molar = _salt_molar(row.get("conditions"))
        return 0.0 if molar is None else abs(math.log10(max(molar, 1e-3) / PHYSIOLOGICAL_SALT_M))

    def from_physiological_ph(row):
        ph = row.get("ph")
        return abs(float(ph) - PHYSIOLOGICAL_PH) if ph is not None else 0.0

    if near:
        ref, k_row, c_row = min(near, key=lambda p: (
            outside_assay_range(p[1]),
            abs(math.log10(p[1]["value"] / km.value)) + abs(math.log10(p[2]["value"] / kcat.value)),
            p[0]))
        # Within the paper chosen, its series is read as a series: a pair at
        # an ordinary assay temperature, then nearest pH 7.4, whatever the
        # medians fell on. IDH1 R132H, ref 761477: the 21 C pair (Km 6 mM,
        # kcat 0.12 1/s) was carried over the same paper's 37 C pair (4.2 mM,
        # 2.4 1/s), which lay "far" from a kcat pick that was itself the 21 C
        # row; fumarase, ref 771047: pH 6.5 (0.4 mM, 175 1/s) over pH 7.5
        # (0.37 mM, 370 1/s) (third round's review).
        series = [p for p in pairs if p[0] == ref and not _other_protein(
            protein(p[1]), protein(k_row) or protein(c_row))]
        ref, k_row, c_row = min(series, key=lambda p: (
            outside_assay_range(p[1]),
            from_physiological_salt(p[1]),
            from_physiological_ph(p[1]),
            abs(math.log10(p[1]["value"] / km.value)) + abs(math.log10(p[2]["value"] / kcat.value)),
            p[0]))
        km_p, kcat_p = resolve("km", k_row), resolve("kcat", c_row)
        if km_p.found and kcat_p.found:
            note = (f"the Km ({k_row['value']:g} mM) and kcat ({c_row['value']:g} 1/s) are one "
                    f"measurement: BRENDA ref {ref} states the same conditions for both rows")
            salts = sorted({m for m in (_salt_molar(p[1].get("conditions")) for p in series)
                            if m is not None})
            if len(salts) > 1 and _salt_molar(k_row.get("conditions")) is not None:
                # Said, so a reader sees the series and the level taken
                # (fifth round of the real-values review).
                note += (f"; that paper measured a salt series ("
                         + ", ".join(f"{m:g} M" for m in salts)
                         + f"), and the pair at {_salt_molar(k_row.get('conditions')):g} M, nearest "
                           f"a cell's {PHYSIOLOGICAL_SALT_M:g} M, is carried")
            if row_form.garbled_ph(k_row.get("conditions")) is not None:
                note += (f"; the Km row's pH is printed unreadably on BRENDA "
                         f"({k_row.get('conditions')!r}) and is read as the kcat row's")
            km_p, kcat_p = _with_clause(km_p, note), _with_clause(kcat_p, note)
            return _with_isozyme_note(km_p, kcat_p, one_isozyme)

    crossed = _pair_across_isoform_tiers(enzyme_ec, organism, substrate, page, kwargs, km, kcat,
                                         protein)
    if crossed is not None:
        return _with_isozyme_note(*crossed, one_isozyme)

    reasons = []
    if unresolvable:
        reasons.append(f"BRENDA ref {', '.join(unresolvable)} holds several Km and kcat rows under "
                       "identical stated conditions with different values, so which Km goes with "
                       "which kcat (and which variant each measured) cannot be told from the rows")
    if far:
        listed = "; ".join(f"ref {r}: Km {k['value']:g}, kcat {c['value']:g}" for r, k, c in far[:3])
        reasons.append(f"a matched pair exists ({listed}) but lies more than "
                       f"{PAIR_MAX_FOLD_FROM_PICK:g}-fold from the constants' own picks, so it was "
                       "not carried for the sake of pairing")
    if undescribed:
        reasons.append(f"BRENDA ref {', '.join(undescribed)} holds a Km row and a kcat row "
                       "stated alike, but without the pH or temperature the constants' own "
                       "picks state, so the better-described rows were kept")
    if not reasons:
        reasons.append("no paper holds a Km row and a kcat row stated under the same conditions "
                       "(the same pH, temperature and other stated conditions) among the rows "
                       "considered")
    # The kcat's own paper's Km, when it is not the one carried, is said with
    # how far it lies: human ALDH2's kcat (19.7 1/s, ref 348688, pH 9.5) came
    # with a claim that no paper held a pair, while that paper gives a Km of
    # 0.2 mM, ~400-fold above the 0.00048 mM carried (fifth round's review).
    kcat_ref = str(getattr(kcat.citation, "reference_id", None) or "")
    km_ref = str(getattr(km.citation, "reference_id", None) or "")
    own = [r for r in (km.pairable or []) if str(r.get("reference_id")) == kcat_ref
           and isinstance(r.get("value"), (int, float)) and r["value"] > 0]
    if kcat_ref and km_ref != kcat_ref and own and km.value:
        k = min(own, key=lambda r: abs(math.log10(r["value"] / km.value)))
        reasons.append(f"the kcat's own paper (BRENDA ref {kcat_ref}) gives a Km of "
                       f"{k['value']:g} mM ({k.get('conditions') or 'no conditions stated'}), "
                       f"{fold(k['value'], km.value):.3g}-fold from the Km carried")
    if one_isozyme is None and _other_protein(km_protein, kcat_protein):
        # Not settled by `_one_isozyme` (it reads isoform names) and no pair
        # of one protein: say plainly that two proteins' constants meet here.
        reasons.append(f"the Km's row names {km_protein} and the kcat's row {kcat_protein}: "
                       "different proteins (by isoform or UniProt entry), so the model combines "
                       "two proteins' constants")
    note = ("the Km and the kcat were chosen independently, not as a measured pair: "
            + "; ".join(reasons))
    return _with_isozyme_note(_with_clause(km, note), _with_clause(kcat, note), one_isozyme)


def _pair_across_isoform_tiers(enzyme_ec, organism, substrate, page, kwargs, km, kcat, protein):
    """`(km, kcat)` of one paper when an isoform was asked for, the kcat's
    carried row names none (so it was taken from the rows naming none), the
    Km's names the isoform, and no pair was found -- else None.

    Human pyruvate kinase, "muscle" read as PKM: the kcat (1182 1/s, ref
    674499, "wild type enzyme, in the presence of K+", naming no isoform)
    and a Km from another paper naming P14618 were carried with "no paper
    holds a pair", while ref 674499 holds the Km measured with that kcat
    (0.13 mM, identical commentary). A kcat already accepted from the rows
    naming no isoform makes its own paper's Km, measured with it and naming
    no OTHER protein, a better partner than another paper's row: the two are
    then one measurement of one preparation (the fourth round of the
    real-values review)."""
    asked = kwargs.get("isoform")
    if not (asked and km.found and kcat.found and km.row_isoform and not kcat.row_isoform):
        return None
    cited = getattr(kcat.citation, "reference_id", None)
    if not cited:
        return None
    loose = resolve_kinetic_value(enzyme_ec=enzyme_ec, organism=organism, substrate=substrate,
                                  html_provider=page, quantity="km", **{**kwargs, "isoform": None})
    if not loose.found:
        return None
    crossed, _, _ = _matched_pairs_with_undescribed(loose, kcat, substrate)
    crossed = [(ref, k, c) for ref, k, c in crossed
               if ref == str(cited) and c.get("value") == kcat.value
               and not _other_protein(protein(k), asked) and not k.get("isoform")]
    if not crossed:
        return None
    ref, k_row, c_row = crossed[0]
    km_p = resolve_kinetic_value(enzyme_ec=enzyme_ec, organism=organism, substrate=substrate,
                                 html_provider=page, quantity="km", prefer_row=k_row,
                                 **{**kwargs, "isoform": None})
    kcat_p = resolve_kinetic_value(enzyme_ec=enzyme_ec, organism=organism, substrate=substrate,
                                   html_provider=page, quantity="kcat", prefer_row=c_row, **kwargs)
    if not (km_p.found and kcat_p.found and km_p.value == k_row["value"]):
        return None
    note = (f"the Km ({k_row['value']:g} mM) and kcat ({c_row['value']:g} 1/s) are one "
            f"measurement: BRENDA ref {ref} states the same conditions for both rows. The kcat "
            f"row names no isoform, so its paper's Km row, which names none either, is carried "
            f"as its pair over the row naming {asked} ({km.value:g} mM, BRENDA ref "
            f"{getattr(km.citation, 'reference_id', None) or '?'}): one preparation's two "
            f"constants rather than two papers'")
    return _with_clause(km_p, note), _with_clause(kcat_p, note)


def _one_isozyme(km, kcat, resolve_value, call):
    """`(km, kcat, isoforms)`: the two picks kept to one isozyme when no
    isoform was asked for and their rows name two.

    Human hexokinase and D-glucose carried HK-I's Km (0.06 mM, ref 640237,
    "hexokinase I") with glucokinase's kcat (60.4 1/s, ref 703624, UniProt
    P35557): two proteins' constants in one rate law. When the carried rows
    name different isozymes (`KineticResult.row_isoform`), the kcat is
    sought among rows naming the Km's isozyme, then the Km among rows
    naming the kcat's; a replacement counts only when its own row names that
    isozyme, never a row naming none (on that page the kcat rows naming no
    isoform are glucokinase papers' too). With neither, the picks stand and
    `isoforms` says so. `isoforms` is None when nothing needed settling,
    else {"km": .., "kcat": .., "moved": "km" | "kcat" | None}."""
    a, b = km.row_isoform, kcat.row_isoform
    if not (a and b):
        return km, kcat, None
    try:
        if _same_isoform(a, b):
            return km, kcat, None
    except ImportError:
        if a == b:
            return km, kcat, None
    def names(result, isoform):
        try:
            return bool(result.found and result.row_isoform
                        and _same_isoform(result.row_isoform, isoform))
        except ImportError:
            return bool(result.found and result.row_isoform == isoform)

    def same_tier(alt):
        return alt.source == ("brenda_exact" if km.source == "brenda_exact" else alt.source)

    half_saturation = None
    for moved, isoform, other in (("kcat", a, "km"), ("km", b, "kcat")):
        alt = resolve_value(**call, quantity=moved, isoform=isoform)
        names_it = names(alt, isoform)
        if names_it and moved == "km" and _is_half_saturation(alt) and not _is_half_saturation(km):
            # Human hexokinase, no isozyme named: HK-I's Michaelis-Menten Km
            # (0.06 mM) and only glucokinase kcat rows. The fourth round kept
            # HK-I's Km beside GCK's kcat rather than take GCK's K0.5 (6.3
            # mM, Hill 1.8), and the model's kcat/Km was then neither
            # enzyme's (fifth round of the real-values review). A Km and a
            # kcat are one protein's: another isozyme with both is sought
            # first, and failing one, the kcat's isozyme's K0.5 is carried
            # and said to be one.
            if same_tier(alt):
                half_saturation = (moved, isoform, other, alt)
            continue
        if names_it and same_tier(alt):
            picks = {"km": km, "kcat": kcat}
            independent = picks[moved]
            picks[moved] = alt
            return picks["km"], picks["kcat"], {
                "km": isoform, "kcat": isoform, "moved": moved, "from": independent,
                "from_isoform": b if moved == "kcat" else a, "other": other}
    # A third isozyme with a true Km and a kcat of its own rows.
    seen = [a, b]
    for row in list(km.pairable or []) + list(kcat.pairable or []):
        iso = row.get("isoform") if isinstance(row, dict) else None
        if not iso or " and " in iso:
            continue
        try:
            if any(_same_isoform(iso, x) for x in seen):
                continue
        except ImportError:
            if iso in seen:
                continue
        seen.append(iso)
        km3 = resolve_value(**call, quantity="km", isoform=iso)
        kcat3 = resolve_value(**call, quantity="kcat", isoform=iso)
        if (names(km3, iso) and names(kcat3, iso) and same_tier(km3) and same_tier(kcat3)
                and not _is_half_saturation(km3)):
            return km3, kcat3, {"km": iso, "kcat": iso, "moved": "both", "from": km,
                                "from_kcat": kcat, "from_isoform": a, "from_kcat_isoform": b,
                                "other": None}
    if half_saturation is not None:
        moved, isoform, other, alt = half_saturation
        return alt, kcat, {"km": isoform, "kcat": isoform, "moved": "km", "from": km,
                           "from_isoform": a, "other": "kcat", "half_saturation": True}
    return km, kcat, {"km": a, "kcat": b, "moved": None}


def _is_half_saturation(result) -> bool:
    """Whether a found Km's carried row is a K0.5 / Hill row (row_form)."""
    return bool(row_form.half_saturation(getattr(result, "commentary", None)))


def _with_isozyme_note(km, kcat, settled):
    """Say what `_one_isozyme` did, on both constants."""
    if settled is None:
        return km, kcat
    if settled["moved"] is None:
        note = (f"the Km's row measured {settled['km']} and the kcat's row {settled['kcat']}: no "
                "row of either isozyme gives the other constant, so the model combines two "
                "isozymes' constants")
    elif settled["moved"] == "both":
        was, was_kcat = settled["from"], settled["from_kcat"]
        note = (f"the Km and the kcat chosen alone measured two isozymes ({was.value:g} "
                f"{was.unit or 'mM'}, {settled['from_isoform']}; {was_kcat.value:g} "
                f"{was_kcat.unit or '1/s'}, {settled['from_kcat_isoform']}), so both were taken "
                f"from rows naming {settled['km']}, which has both: one protein's constants")
    else:
        moved, other = settled["moved"], settled["other"]
        was = settled["from"]
        label = {"km": "Km", "kcat": "kcat"}
        note = (f"the {label[moved]} was taken from rows naming {settled[moved]}, the isozyme of "
                f"the {label[other]}'s row, so both constants are one protein's (the "
                f"{label[moved]} chosen alone, {was.value:g} {was.unit or ''}".rstrip()
                + f", measured {settled['from_isoform']})")
        if settled.get("half_saturation"):
            note += (f". No row of {settled['from_isoform']} gives a kcat and no other isozyme "
                     f"has both constants, so the model is {settled[moved]}'s, and its Km row is "
                     "a K0.5 (a cooperative half-saturation constant): one protein's constants "
                     "rather than two proteins' mixed")
    return _with_clause(km, note), _with_clause(kcat, note)


if __name__ == "__main__":
    result = resolve_kinetic_value(
        "1.1.1.27", "Homo sapiens", "lactate", enzyme_name="lactate dehydrogenase"
    )
    print(result.model_dump_json(indent=2))
