"""The shapes that cross the studio's HTTP boundary, and how a number keeps its origin there.

WHY ONE MODULE, MIRRORED BY HAND IN TYPESCRIPT
----------------------------------------------
Five parts of the studio are written at once: the server, two families of
science adapters, the page, and the macOS shell. Each reads or writes these
shapes, and a field one side renames is a field the other side reads as
`undefined` and draws as an empty cell, which on this project is the worst
kind of defect: a number silently absent looks exactly like a number nobody
measured. So every request and response is declared here once, as a
TypedDict, and `Science-Agent-Pipeline/artifacts/caterva-studio/src/api/types.ts`
declares the same names with the same keys. `caterva/tests/test_studio_contract.py`
fails when the two disagree about a type name, a key, whether a key is
optional, or a string union's members.

No generator is used because the only one that fits (pydantic's JSON schema
plus a TypeScript emitter) would add a runtime dependency to a server whose
brief is the standard library only, and a build step to a skeleton five
people are about to edit.

WHY PROVENANCE IS A FIELD OF EVERY NUMBER, NOT A SIDE TABLE
-----------------------------------------------------------
The command line prints a value and its origin on the same line, or in the
same table row, and a reader cannot see one without the other. A JSON API
that returned `{"Km": 0.03}` and put "BRENDA ref 286469" in a separate
`citations` array would let the page draw the number and forget the
citation, which is the laundering `caterva/compose/export.py` exists to
prevent, moved one layer out. So a number that reaches the page is a
`SourcedValue`: the value, its unit and a `Provenance` whose `kind` is one
of five words, and the page is built so a value cannot be drawn without
its mark (docs/studio/CONTRACT.md, "Provenance").

The five kinds are the three `export.py` already uses (measured,
placeholder, chosen) plus two the other commands produce: `computed` (a
number Caterva derived from others: a free energy from a Ki, a block
average over replicas, an SSA count) and `fitted` (a number estimated from
data by a fit, with the fit named). Nothing here decides which kind a
number is by looking at its name; the adapter that produced it says, from
the library object that carried it.

WHAT THE HELPERS AT THE BOTTOM DO, AND DO NOT
---------------------------------------------
`jsonable` turns the library's dataclasses into JSON without choosing a
precision: floats pass through as Python floats (JSON's round-trip is
exact for them), non-finite floats become null, and a complex eigenvalue
becomes {"re", "im"}. It never rounds. `from_parameter_origin` maps
`export.ParameterOrigin`, the one place compose decides an origin, onto
`Provenance`, and uses the origin's own `sentence()` as the reason text
rather than writing a second sentence about the same number.

Two sections below, "Kinetics kinds" and "Structure kinds", belong to the
two science adapter owners; each may ADD optional keys or new types to its
own section, and must make the same change to types.ts in the same commit.
Everything else is changed only by amending docs/studio/CONTRACT.md.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import enum
import math
import pathlib
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple, TypedDict

# ---------------------------------------------------------------------------
# Constants both sides of the boundary read
# ---------------------------------------------------------------------------

#: Bumped when a change to this module would break a page built against the
#: previous one. The page reads it from /api/health and refuses to run
#: against a server whose number differs, rather than drawing half a result.
STUDIO_API_VERSION = 1

#: The request header that carries the per-launch session token.
SESSION_HEADER = "X-Caterva-Session"

#: The <meta name="..."> the server writes the token into, in index.html.
SESSION_META_NAME = "caterva-session"

#: What index.html carries in that meta tag until the server replaces it.
#: A page that still shows this string was not served by the studio server.
TOKEN_PLACEHOLDER = "__CATERVA_SESSION_TOKEN__"

#: The one line `caterva studio --print-url` writes to stdout once serving.
URL_LINE_PREFIX = "CATERVA_STUDIO_URL="

#: The largest request body accepted, in bytes. Every request is a small
#: JSON document; a trajectory is named by its path, never uploaded.
MAX_BODY_BYTES = 1_048_576

#: The `schema` field of every run record written to disk.
RUN_RECORD_SCHEMA = "caterva.studio.run/1"

# ---------------------------------------------------------------------------
# String unions. Each Literal has a tuple beside it so code can iterate the
# members; the test checks the two agree.
# ---------------------------------------------------------------------------

RunKind = Literal[
    "compose", "constants", "sim", "bind",
    "structure", "prepare", "md.setup", "md.summarise", "analyze",
    "fep.status", "complex.check",
    "rates",
]
RUN_KINDS: Tuple[str, ...] = (
    "compose", "constants", "sim", "bind",
    "structure", "prepare", "md.setup", "md.summarise", "analyze",
    "fep.status", "complex.check",
    "rates",
)

#: A run's place in its life. `interrupted` is a run the server was stopped
#: during; it is never resumed, because a half-finished search resumed
#: later would mix two days' database answers in one result.
RunStatus = Literal["queued", "running", "done", "failed", "cancelled", "interrupted"]
RUN_STATUSES: Tuple[str, ...] = ("queued", "running", "done", "failed", "cancelled", "interrupted")

#: What a finished run's CLI exit code means. 2 (malformed) never becomes a
#: run: it is a 400 at submission. 1 (a crash) is status `failed`.
#:
#: Exit 4 is not one meaning across the commands: `bind` uses it for "the
#: computed value disagrees", `prepare` for "every chain has a blocking
#: defect", `analyze` and `md --summarise` for "not (yet) a consistent
#: result", `complex --check` for "the ligand left its pose", `fep
#: --summarise` for "disagrees, or not yet a result". What they share is
#: that the command ran to the end and its answer is a negative finding,
#: which is neither a success nor a refusal. So the meaning is `negative`
#: and NEGATIVE_MEANING carries each command's own words for it; the
#: page shows those words, never a generic "failed".
OutcomeMeaning = Literal["produced", "refused", "negative"]
OUTCOME_MEANINGS: Tuple[str, ...] = ("produced", "refused", "negative")
EXIT_MEANING: Mapping[int, str] = {0: "produced", 3: "refused", 4: "negative"}

#: Kind -> what exit 4 means for the command it mirrors, in that command's
#: `--help` words. A kind absent here never exits 4, and `outcome_for`
#: refuses a 4 from it as a programming error.
NEGATIVE_MEANING: Mapping[str, str] = {
    "bind": "the computed value disagrees with the measured band",
    "prepare": "every chain has a blocking defect",
    "md.summarise": "the replicas are not (yet) a consistent result",
    "analyze": "at least one quantity is not a result (unconverged, replicas disagree, one sample)",
    "fep.status": "disagrees, or not yet a result (one replica, missing legs)",
    "complex.check": "the ligand left its pose",
}

ProvenanceKind = Literal["measured", "fitted", "computed", "placeholder", "chosen"]
PROVENANCE_KINDS: Tuple[str, ...] = ("measured", "fitted", "computed", "placeholder", "chosen")

#: Who chose a chosen number: the person, in the request, or a stated
#: default of the command (the CLI's argparse default, a motif's starting
#: amount). The page marks the second in the caution colour.
ChosenBy = Literal["user", "default"]
CHOSEN_BY: Tuple[str, ...] = ("user", "default")

Nonfinite = Literal["nan", "inf", "-inf"]
NONFINITE: Tuple[str, ...] = ("nan", "inf", "-inf")

ErrorCode = Literal[
    "malformed", "unauthorized", "forbidden", "not_found", "method_not_allowed",
    "conflict", "too_large", "unsupported_media_type", "unavailable", "crash",
]
ERROR_CODES: Tuple[str, ...] = (
    "malformed", "unauthorized", "forbidden", "not_found", "method_not_allowed",
    "conflict", "too_large", "unsupported_media_type", "unavailable", "crash",
)

#: What a run may need beyond the engine. Reported per kind in capabilities.
Need = Literal["network", "literature", "gromacs"]
NEEDS: Tuple[str, ...] = ("network", "literature", "gromacs")

Theme = Literal["system", "light", "dark"]
THEMES: Tuple[str, ...] = ("system", "light", "dark")

EventName = Literal["status", "stage", "log", "result", "error", "end"]
EVENT_NAMES: Tuple[str, ...] = ("status", "stage", "log", "result", "error", "end")

SectionStatus = Literal["answered", "refused", "partly_refused"]
SECTION_STATUSES: Tuple[str, ...] = ("answered", "refused", "partly_refused")

# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class _CitationRequired(TypedDict):
    #: The citation exactly as the library carries it ("BRENDA ref 286469",
    #: a PDB primary citation's `cite()`). Never re-assembled here.
    text: str


class Citation(_CitationRequired, total=False):
    #: The registry the library says it came from ("BRENDA", "PubMed",
    #: "PDB", "M-CSA", "UniProt"), when the library says. Never inferred
    #: from `text`.
    registry: Optional[str]
    reference_id: Optional[str]
    #: A link of a form known to work (CONTRACT.md, "Citation links"). None
    #: rather than a guessed one: BRENDA has no per-reference page.
    url: Optional[str]
    title: Optional[str]
    journal: Optional[str]
    year: Optional[int]
    doi: Optional[str]
    pubmed: Optional[str]
    #: How Caterva reached it ("brenda/km", "literature"), as distinct from
    #: what the paper is.
    via: Optional[str]


class Conditions(TypedDict):
    ph: Optional[float]
    temperature_c: Optional[float]
    buffer: Optional[str]
    #: Conditions the source did not state, named rather than omitted.
    unreported: List[str]


class Spread(TypedDict):
    """The values the resolver ranked for one quantity, when they differ.
    Not an uncertainty estimate; `sentence` is export.Spread.sentence()."""

    low: float
    high: float
    unit: str
    carried: float
    n_values: int
    references: List[str]
    sentence: str


class _FitInfoRequired(TypedDict):
    method: str


class FitInfo(_FitInfoRequired, total=False):
    n_points: Optional[int]
    residual: Optional[float]
    stderr: Optional[float]
    r_squared: Optional[float]


class _ProvenanceRequired(TypedDict):
    kind: ProvenanceKind


class Provenance(_ProvenanceRequired, total=False):
    # measured
    citation: Citation
    organism: Optional[str]
    cross_species: bool
    conditions: Conditions
    #: The source row's commentary, verbatim.
    commentary: Optional[str]
    #: What the row says it measured, where that could make it the wrong
    #: number for this model (row_scope concerns, their `plain` text).
    scope: List[str]
    spread: Optional[Spread]
    #: Why this row was carried rather than the resolver's pick.
    chosen_because: Optional[str]
    # placeholder, chosen, and any refusal: the library's own sentence
    reason: Optional[str]
    #: The database table that would supply a placeholder, when one would.
    table: Optional[str]
    # computed
    method: Optional[str]
    #: Identifiers of the numbers a computed one was derived from.
    inputs: List[str]
    # fitted
    fit: FitInfo
    # chosen
    by: ChosenBy
    #: Anything else the library said about this number, verbatim.
    note: Optional[str]


class Interval(TypedDict):
    """A value the library gives as a range rather than a point (a free
    energy over an unstated assay temperature), with the reason."""

    low: Optional[float]
    high: Optional[float]
    meaning: str


class _SourcedValueRequired(TypedDict):
    #: The library's float, unrounded. None only for a non-finite value
    #: (then `nonfinite` says which) or a range (then `interval`).
    value: Optional[float]
    unit: str
    provenance: Provenance


class SourcedValue(_SourcedValueRequired, total=False):
    #: The identifier the model or report uses for it ("reaction_Km").
    id: str
    #: A short human label ("Km"), when the library has one.
    label: str
    nonfinite: Nonfinite
    interval: Interval


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class _ApiErrorRequired(TypedDict):
    code: ErrorCode
    message: str


class ApiError(_ApiErrorRequired, total=False):
    #: The request key the message is about, for a malformed request.
    field: Optional[str]
    details: Dict[str, Any]


class ErrorBody(TypedDict):
    error: ApiError


# ---------------------------------------------------------------------------
# Meta: health, capabilities, settings
# ---------------------------------------------------------------------------


class Health(TypedDict):
    ok: bool
    version: str
    api_version: int
    started_at: str


class LiteratureCapability(TypedDict):
    available: bool
    reason: Optional[str]


class NetworkCapability(TypedDict):
    #: False until something asked (GET /api/capabilities?probe=network):
    #: probing contacts third parties, so it is never done unasked.
    checked: bool
    reachable: Optional[bool]
    hosts: Dict[str, Optional[bool]]
    checked_at: Optional[str]
    reason: Optional[str]


class GromacsCapability(TypedDict):
    found: bool
    path: Optional[str]
    version: Optional[str]
    reason: Optional[str]


class RatesCapability(TypedDict):
    available: bool
    reason: Optional[str]


class UiCapability(TypedDict):
    built: bool
    static_dir: str
    reason: Optional[str]


class DataDirCapability(TypedDict):
    path: str
    writable: bool
    runs: int
    reason: Optional[str]


class KindCapability(TypedDict):
    available: bool
    title: str
    #: The `caterva <command>` this kind mirrors.
    command: str
    needs: List[Need]
    reason: Optional[str]


class Capabilities(TypedDict):
    version: str
    api_version: int
    python: str
    platform: str
    frozen: bool
    literature: LiteratureCapability
    network: NetworkCapability
    gromacs: GromacsCapability
    rates: RatesCapability
    ui: UiCapability
    data_dir: DataDirCapability
    kinds: Dict[str, KindCapability]
    dev_origin: Optional[str]


class _SettingsRequired(TypedDict):
    theme: Theme
    max_parallel_runs: int
    confirm_delete: bool


class Settings(_SettingsRequired, total=False):
    #: Optional on PUT (a body without it keeps the stored value, so a page
    #: that does not know the key cannot erase it); always present on GET.
    #: The absolute path of the `gmx` program, or None to look for it
    #: (CONTRACT.md 10). Checked to be an executable file when set.
    gromacs_path: Optional[str]
    #: True: the studio contacts no network host on its own (the network
    #: probe answers without probing) and refuses to start a run of any kind
    #: whose `needs` include "network", with that reason (503). Default False.
    offline: bool


class NormaliseOrganismRequest(TypedDict):
    name: str


class NormaliseOrganismResponse(TypedDict):
    organism: Optional[str]
    note: Optional[str]


class ShapesResponse(TypedDict):
    shapes: List[str]


class DevSession(TypedDict):
    """GET /api/dev/session, which exists only with --dev-origin: what the
    Vite dev server writes into its index.html in place of the placeholder."""

    token: str
    api_version: int


# ---------------------------------------------------------------------------
# Runs, jobs and their events
# ---------------------------------------------------------------------------


class _CreateRunBodyRequired(TypedDict):
    kind: RunKind
    #: The kind's request type (ComposeRequest, ...). Validated by the
    #: kind's adapter, through the CLI's own parser.
    request: Dict[str, Any]


class CreateRunBody(_CreateRunBodyRequired, total=False):
    title: str


class Outcome(TypedDict):
    exit_code: int
    meaning: OutcomeMeaning
    #: One line for the history list, from the result (never invented).
    summary: str
    #: For `refused`: what the CLI prints to stderr for the same request
    #: (UnrecognisedShape's message, "Refused: ..."), verbatim, so the page
    #: can show the reason even when the run produced no result. For
    #: `negative`: NEGATIVE_MEANING[kind]. None for `produced`.
    reason: Optional[str]


class _RunErrorRequired(TypedDict):
    type: str
    message: str


class RunError(_RunErrorRequired, total=False):
    traceback: Optional[str]


class ArtifactInfo(TypedDict):
    name: str
    content_type: str
    bytes: int
    description: str


class ProgressState(TypedDict):
    stage: str
    label: str
    fraction: Optional[float]


class RunRecord(TypedDict):
    schema: str
    id: str
    kind: RunKind
    title: str
    status: RunStatus
    created_at: str
    started_at: Optional[str]
    finished_at: Optional[str]
    caterva_version: str
    #: The command line that reproduces the run from the repository root,
    #: as argv: "caterva <command> ..." for every kind but `constants`,
    #: which is "python3 scripts/cite.py ...".
    cli: List[str]
    request: Dict[str, Any]
    outcome: Optional[Outcome]
    error: Optional[RunError]
    artifacts: List[ArtifactInfo]
    progress: Optional[ProgressState]


class RunSummary(TypedDict):
    id: str
    kind: RunKind
    title: str
    status: RunStatus
    created_at: str
    finished_at: Optional[str]
    outcome: Optional[Outcome]


class RunList(TypedDict):
    runs: List[RunSummary]
    next_cursor: Optional[str]


class RunCreated(TypedDict):
    run: RunRecord


class _StatusEventRequired(TypedDict):
    run_id: str
    seq: int
    at: str
    status: RunStatus


class StatusEvent(_StatusEventRequired, total=False):
    outcome: Optional[Outcome]


class StageEvent(TypedDict):
    run_id: str
    seq: int
    at: str
    stage: str
    label: str
    fraction: Optional[float]


class LogEvent(TypedDict):
    run_id: str
    seq: int
    at: str
    line: str


class ResultEvent(TypedDict):
    run_id: str
    seq: int
    at: str
    outcome: Outcome


class ErrorEvent(TypedDict):
    run_id: str
    seq: int
    at: str
    error: RunError


class EndEvent(TypedDict):
    run_id: str
    seq: int
    at: str
    status: RunStatus


class StructuredSection(TypedDict):
    """One heading of a CLI report that has no structured form yet beyond
    its text, or whose structured form rides in `data`."""

    key: str
    title: str
    status: SectionStatus
    #: The section's text exactly as the CLI prints it under its heading.
    text: str
    refusals: List[str]
    data: Optional[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Kinetics kinds (owner: sci-kinetics). compose, constants, sim, bind.
# ---------------------------------------------------------------------------

#: The most rows of an event table (an SSA trajectory) a result carries.
#: A run with more is sent as every n-th row and its last row, and says so
#: (`rows`, `every`): each row sent is one the run held, never an
#: interpolation, and the full table is the CLI's (or the CSV artefact).
SERIES_ROW_LIMIT = 20_000


class _SweepRequestRequired(TypedDict):
    parameters: List[str]


class SweepRequest(_SweepRequestRequired, total=False):
    low: float
    high: float
    steps: int


class RobustnessRequest(TypedDict):
    #: None asks with the module's default sample count (the CLI's bare
    #: `--robustness`).
    samples: Optional[int]


class _StochasticRequestRequired(TypedDict):
    volume_l: float


class StochasticRequest(_StochasticRequestRequired, total=False):
    end_s: Optional[float]
    seed: Optional[int]


class ComposeAnalyses(TypedDict, total=False):
    scale: bool
    predictions: bool
    crnt: bool
    reduction: bool
    identifiability: bool
    design: bool
    validate: bool
    screen: bool
    knockout: List[str]
    overexpress: List[str]
    robustness: RobustnessRequest
    stochastic: StochasticRequest


class _ComposeRequestRequired(TypedDict):
    description: str


class ComposeRequest(_ComposeRequestRequired, total=False):
    subject: str
    organism: str
    substrate: str
    inhibitor: str
    product: str
    isoform: str
    any_mode: bool
    #: port -> compound name, the CLI's repeatable --compound PORT=NAME.
    compounds: Dict[str, str]
    rank_against: str
    sweep: SweepRequest
    no_analysis: bool
    no_simulate: bool
    no_ranking: bool
    analyses: ComposeAnalyses


class Recognition(TypedDict):
    rule: str
    reading: str


class SpeciesRow(TypedDict):
    id: str
    initial: SourcedValue


class ReactionRow(TypedDict):
    id: str
    rate_law: str


class MotifRow(TypedDict):
    name: str
    basis: str
    copies: int


class ModelStructure(TypedDict):
    species: List[SpeciesRow]
    reactions: List[ReactionRow]
    #: Every parameter, each with its provenance (export.provenance_of).
    parameters: List[SourcedValue]
    conservation_laws: List[str]
    unconserved: List[str]
    concentration_unit: str
    motifs: List[MotifRow]


class SearchSummary(TypedDict):
    asked: bool
    refused: bool
    note: Optional[str]
    subject: Optional[str]
    ec: Optional[str]
    organism: Optional[str]
    substrate: Optional[str]
    isoform: Optional[str]
    compounds: Dict[str, str]
    measured: int
    placeholders: int


class Concern(TypedDict):
    source: str
    severity: str
    detail: str
    remedy: str


class VerdictView(TypedDict):
    verdict: str
    licence: str
    behaviour: Optional[str]
    conclusion: Optional[str]
    concerns: List[Concern]
    next_step: Optional[str]
    consulted: Dict[str, str]
    unavailable: Dict[str, str]
    #: verdict.summary(), exactly as the CLI prints it.
    text: str


class ComplexNumber(TypedDict):
    re: float
    im: float


class FixedPointView(TypedDict):
    state: Dict[str, Optional[float]]
    residual: Optional[float]
    eigenvalues: List[ComplexNumber]
    classification: str
    physical: bool
    stable: bool
    oscillatory: bool
    slowest_timescale: Optional[float]


class StabilityView(TypedDict):
    starts_tried: int
    species: List[str]
    notes: List[str]
    fixed_points: List[FixedPointView]
    text: str


class InvariantView(TypedDict):
    law: str
    initial: Optional[float]
    final: Optional[float]
    worst_drift: Optional[float]
    held: bool


class TrajectoryView(TypedDict):
    times: List[Optional[float]]
    columns: Dict[str, List[Optional[float]]]
    end: Optional[float]
    points: int
    window_basis: str
    invariants: List[InvariantView]
    checked: bool
    sound: bool
    unmeasured: List[str]
    text: str


class SensitivityRow(TypedDict):
    parameter: str
    value: Optional[float]
    relative: Optional[float]
    absolute: Optional[float]
    negligible: bool
    unresolvable: bool


class SensitivityView(TypedDict):
    quantity: str
    base_value: Optional[float]
    sensitivities: List[SensitivityRow]
    skipped: Dict[str, str]
    conserved_by: Optional[str]
    resolution: Optional[float]


class ExportInfo(TypedDict):
    available: bool
    #: The artifact name under /api/runs/{id}/artifacts/, when written.
    artifact: Optional[str]
    #: ExportRefused's message, when the format could not be written.
    refused: Optional[str]


class ComposeResult(TypedDict):
    query: str
    recognition: Recognition
    model: ModelStructure
    search: SearchSummary
    verdict: Optional[VerdictView]
    stability: Optional[StabilityView]
    trajectory: Optional[TrajectoryView]
    sensitivity: Optional[SensitivityView]
    #: bifurcation.SweepReport per swept parameter, through `jsonable`.
    sweeps: List[Dict[str, Any]]
    sections: List[StructuredSection]
    notes: List[str]
    #: What `caterva compose` prints to stdout for the same request.
    report_markdown: str
    exports: Dict[str, ExportInfo]


class _ConstantsRequestRequired(TypedDict):
    substrate: str


class ConstantsRequest(_ConstantsRequestRequired, total=False):
    #: Exactly one of ec and enzyme, as scripts/cite.py requires.
    ec: str
    enzyme: str
    organism: str
    quantities: List[str]
    s0: float
    vmax: float
    concentration_unit: str
    basis: str
    title: str
    question: str
    seed: Optional[int]


class ConstantRow(TypedDict):
    name: str
    quantity: str
    found: bool
    #: The resolver's outcome word (KineticResult.source).
    source: str
    value: Optional[SourcedValue]
    #: Every other row the resolver ranked, each as measured.
    alternatives: List[SourcedValue]
    organisms_available: List[str]
    isoforms_available: List[str]
    modes_available: List[str]
    variants_available: List[str]
    #: KineticResult as the resolver returned it (model_dump), for fields
    #: the rows above do not lift out.
    raw: Dict[str, Any]


class _ConstantsResultRequired(TypedDict):
    document_markdown: str
    constants: List[ConstantRow]
    supplied: List[SourcedValue]
    sourced: List[str]
    derived: List[str]
    refusals: List[str]
    disagreements: List[Any]
    defensible: bool


class ConstantsResult(_ConstantsResultRequired, total=False):
    #: How cite.py read the organism typed ("Read --organism 'human' as
    #: Homo sapiens."), which it prints to stderr; None when used as typed.
    organism_note: Optional[str]


class _SimRequestRequired(TypedDict):
    #: Required here although the CLI allows none: a trajectory whose seed
    #: is not recorded cannot be reproduced (ADR 0005).
    seed: int


class SimRequest(_SimRequestRequired, total=False):
    bimolecular: bool
    a0: int
    b0: int
    k: float
    end: float


class _SimResultRequired(TypedDict):
    columns: List[str]
    series: Dict[str, List[Optional[float]]]
    events: int
    seed: int
    parameters: Dict[str, SourcedValue]
    final: Dict[str, SourcedValue]
    expected: SourcedValue
    report_text: str


class SimResult(_SimResultRequired, total=False):
    #: Rows in the run's event table (initial, one per event, final).
    rows: int
    #: `series` holds every `every`-th row and the last one; 1 when it holds
    #: them all (SERIES_ROW_LIMIT).
    every: int


class _ComputedDGRequired(TypedDict):
    value: float


class ComputedDG(_ComputedDGRequired, total=False):
    error: Optional[float]
    unit: Literal["kcal", "kj"]


class _BindRequestRequired(TypedDict):
    ec: str
    mode: Literal["inhibitor", "list", "survey"]


class BindRequest(_BindRequestRequired, total=False):
    organism: str
    inhibitor: str
    state: Literal["free", "ternary"]
    isoform: str
    computed: ComputedDG


class KiRow(TypedDict):
    ki: SourcedValue
    dg: SourcedValue
    compound: str
    organism: str
    reference: Optional[str]
    commentary: Optional[str]
    mode: str
    versus: Optional[str]
    preparation: Optional[str]
    isoform: Optional[str]
    excluded: Optional[str]


class BindTarget(TypedDict):
    compound: str
    organism: str
    state: str
    used: List[KiRow]
    excluded: List[KiRow]
    band_low: Optional[SourcedValue]
    band_high: Optional[SourcedValue]
    references: List[str]
    caveats: List[str]


class _BindVerdictRequired(TypedDict):
    word: str
    gap_kcal: SourcedValue
    ki_fold: SourcedValue
    detail: str
    computed: SourcedValue


class BindVerdict(_BindVerdictRequired, total=False):
    #: The computed value's stated error (σ), in kcal/mol like `computed`.
    computed_error: SourcedValue
    #: The temperature the Ki fold was judged at: the mean assay
    #: temperature of the rows used, or the command's 25 °C default.
    temperature_c: SourcedValue


class BindSurveyRow(TypedDict):
    """One (compound, organism, isoform) of `caterva bind --survey`: the
    library's survey row with the band as numbers that carry their origin."""

    compound: str
    organism: str
    isoform: Optional[str]
    rows: int
    used: int
    references: List[str]
    band_low: Optional[SourcedValue]
    band_high: Optional[SourcedValue]
    benchmark: bool
    why_not: List[str]


class BindResult(TypedDict):
    mode: str
    compounds: List[str]
    #: One row per compound, organism and isoform, for mode "survey".
    survey: List[BindSurveyRow]
    target: Optional[BindTarget]
    verdict: Optional[BindVerdict]
    report_text: str


# ---------------------------------------------------------------------------
# Structure kinds (owner: sci-structure). structure, prepare, md.setup,
# md.summarise, analyze, fep.status, complex.check, and coordinates.
# ---------------------------------------------------------------------------


class _StructureRequestRequired(TypedDict):
    subject: str


class StructureRequest(_StructureRequestRequired, total=False):
    organism: str
    gene: str
    uniprot: str
    ligand: str
    top: int
    chimerax: bool


class BoundMoleculeView(TypedDict):
    component: str
    name: str
    role: str


class ProteinRow(TypedDict):
    accession: str
    gene: Optional[str]
    name: str
    organism: str
    entries: int
    chosen: bool


class StructureRow(TypedDict):
    pdb_id: str
    title: str
    method: str
    resolution: Optional[SourcedValue]
    organisms: List[str]
    uniprot: List[str]
    bound: List[BoundMoleculeView]
    citation: Citation
    binds_ligand: Optional[bool]


class StructureResult(TypedDict):
    ec: str
    organism: Optional[str]
    ligand: Optional[str]
    proteins: List[ProteinRow]
    chosen: Optional[str]
    undecided: Optional[str]
    entries: List[StructureRow]
    total: int
    report_markdown: str
    chimerax_artifact: Optional[str]


class AtomColumns(TypedDict):
    x: List[float]
    y: List[float]
    z: List[float]
    element: List[str]
    atom_name: List[str]
    resname: List[str]
    chain: List[str]
    resseq: List[int]
    hetero: List[bool]


class CoordinatesResponse(TypedDict):
    pdb_id: str
    citation: Citation
    atoms: AtomColumns
    count: int
    #: True when the entry had more atoms than MAX_VIEWER_ATOMS and the
    #: viewer was sent the first model's protein and ligand atoms only.
    truncated: bool


class _PrepareRequestRequired(TypedDict):
    #: A PDB id (1I10) or an absolute path to a local .cif file.
    entry: str


class PrepareRequest(_PrepareRequestRequired, total=False):
    ph: float
    no_cache: bool


class ChainSummaryRow(TypedDict):
    chain: str
    blocks: int
    near_site: int
    catalytic_intact: bool


class FindingRow(TypedDict):
    severity: str
    chain: Optional[str]
    residues: List[str]
    distance: Optional[SourcedValue]
    what: str
    source: str


class PrepareResult(TypedDict):
    pdb_id: str
    title: str
    method: str
    resolution: Optional[SourcedValue]
    r_free: Optional[SourcedValue]
    chains: List[str]
    clean: bool
    chain_summary: List[ChainSummaryRow]
    findings: List[FindingRow]
    catalytic: List[Dict[str, Any]]
    reference: Optional[Dict[str, Any]]
    protonation: Optional[List[Dict[str, Any]]]
    not_checked: List[str]
    report_markdown: str
    #: The CLI's --json document (dataclasses.asdict of the Audit).
    audit: Dict[str, Any]


class _MdSetupRequestRequired(TypedDict):
    pdb: str


class MdSetupRequest(_MdSetupRequestRequired, total=False):
    chain: str
    #: Absolute path; default <data dir>/runs/<run id>/md-setup.
    out: str
    subject: str
    organism: str
    substrate: str
    temperature_k: float
    ph: float
    ns: float
    ionic_strength_m: float
    seed: int
    replicas: int


class MdParameterRow(TypedDict):
    name: str
    value: str
    origin: str
    source: str


class MdSetupResult(TypedDict):
    out_dir: str
    pdb: str
    chain: Optional[str]
    temperature: SourcedValue
    ph: Optional[SourcedValue]
    parameters: List[MdParameterRow]
    files: List[str]
    note: Optional[str]
    report_text: str


class DirectoryRequest(TypedDict):
    #: An absolute path to a directory `caterva md` (or fep, complex) wrote.
    directory: str


class ReplicaRow(TypedDict):
    name: str
    mean: SourcedValue
    error: SourcedValue
    verdict: str


class ConvergenceResult(TypedDict):
    quantity: str
    unit: str
    verdict: str
    replicas: List[ReplicaRow]
    report_markdown: str
    #: convergence.Summary through `jsonable`.
    summary: Dict[str, Any]


class _AnalyzeRequestRequired(TypedDict):
    directory: str


class AnalyzeRequest(_AnalyzeRequestRequired, total=False):
    mode: Literal["native", "gromacs", "no_run", "script_only"]


class DistanceRow(TypedDict):
    label: str
    crystal: Optional[SourcedValue]
    mean: SourcedValue
    drift: Optional[SourcedValue]
    moved: bool
    verdict: str


class AnalyzeResult(TypedDict):
    pdb: str
    chain: Optional[str]
    source: str
    all_consistent: bool
    distances_consistent: bool
    distances: List[DistanceRow]
    flexibility: Optional[Dict[str, Any]]
    hbonds: Optional[List[Dict[str, Any]]]
    rotamers: Optional[List[Dict[str, Any]]]
    angles: List[Dict[str, Any]]
    water: Optional[List[Dict[str, Any]]]
    faces: Optional[List[Dict[str, Any]]]
    script_written: bool
    report_markdown: str


class FepReplicaRow(TypedDict):
    rep: int
    complex_kj: SourcedValue
    solvent_kj: SourcedValue
    dg_kcal: SourcedValue


class FepStatusResult(TypedDict):
    compound: str
    organism: str
    temperature_k: Optional[SourcedValue]
    restraint_correction: Optional[SourcedValue]
    replicas: List[FepReplicaRow]
    band_low: Optional[SourcedValue]
    band_high: Optional[SourcedValue]
    computed: Optional[SourcedValue]
    verdict: Optional[BindVerdict]
    not_a_result: Optional[str]
    warnings: List[str]
    report_text: str


class ComplexCheckRequest(TypedDict):
    #: `caterva complex --check DIR --ligand RES`. There is no ligand_itp:
    #: the CLI accepts --ligand-itp beside --check and does not pass it to
    #: `check()` (CONTRACT.md, "Gaps"), and the studio does not offer a
    #: field the command would ignore.
    directory: str
    ligand: str


class ComplexCheckResult(TypedDict):
    kept: bool
    values: Dict[str, SourcedValue]
    report_text: str


#: The `rates` kind arrives from another branch; its shapes are declared
#: when it is integrated. Until then a request is an untyped object and the
#: kind reports itself unavailable.
RatesRequest = Dict[str, Any]
RatesResult = Dict[str, Any]

#: Kind -> (request type name, result type name). The server validates
#: nothing by these names; they exist so the page and the tests agree which
#: shape belongs to which kind.
KIND_SHAPES: Mapping[str, Tuple[str, str]] = {
    "compose": ("ComposeRequest", "ComposeResult"),
    "constants": ("ConstantsRequest", "ConstantsResult"),
    "sim": ("SimRequest", "SimResult"),
    "bind": ("BindRequest", "BindResult"),
    "structure": ("StructureRequest", "StructureResult"),
    "prepare": ("PrepareRequest", "PrepareResult"),
    "md.setup": ("MdSetupRequest", "MdSetupResult"),
    "md.summarise": ("DirectoryRequest", "ConvergenceResult"),
    "analyze": ("AnalyzeRequest", "AnalyzeResult"),
    "fep.status": ("DirectoryRequest", "FepStatusResult"),
    "complex.check": ("ComplexCheckRequest", "ComplexCheckResult"),
    "rates": ("RatesRequest", "RatesResult"),
}

#: The viewer is sent at most this many atoms (CoordinatesResponse).
MAX_VIEWER_ATOMS = 60_000

# ---------------------------------------------------------------------------
# Exceptions an adapter raises, and what the server turns them into
# ---------------------------------------------------------------------------


class Malformed(ValueError):
    """The request is not a well-formed question: HTTP 400, code
    "malformed", the CLI's exit 2. Raised before any work is done."""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        super().__init__(message)
        self.field = field


class Unavailable(RuntimeError):
    """The kind cannot run in this installation at all (the literature
    layer is absent from the app folder, a module is not integrated):
    HTTP 503 "unavailable" at submission, with the reason. A run that
    STARTS and then meets a missing capability (the network drops, gmx is
    not found half way) is a refusal (exit 3) inside the run instead."""


class NotFound(LookupError):
    """An adapter-owned endpoint's subject does not exist (a PDB id the RCSB
    does not have): HTTP 404 "not_found", with the library's words."""


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

#: Recursion ceiling for `jsonable`. The library's reports nest a few
#: levels; anything deeper is a cycle or a whole object graph, and a
#: refusal names it rather than serialising a model's internals.
MAX_DEPTH = 24


def finite(value: Any) -> Tuple[Optional[float], Optional[str]]:
    """(value, None) for a finite number, (None, "nan"|"inf"|"-inf") otherwise.

    JSON has no NaN or Infinity, and Python's json module writes them
    anyway as bare tokens a browser's JSON.parse rejects. A non-finite
    number is kept as a named fact rather than dropped.
    """
    number = float(value)
    if math.isnan(number):
        return None, "nan"
    if math.isinf(number):
        return None, "inf" if number > 0 else "-inf"
    return number, None


def jsonable(obj: Any, *, properties: bool = True, _depth: int = 0) -> Any:
    """A JSON-ready copy of a library value, without rounding anything.

    Dataclasses become objects of their fields and, with `properties`, of
    their public read-only properties (the library puts judgements there:
    `stable`, `negligible`, `held`), each evaluated once and skipped if it
    raises. Tuples and sets become lists, mappings get string keys,
    complex numbers become {"re", "im"}, non-finite floats become None,
    numpy scalars and arrays become Python numbers and lists, pydantic
    models go through `model_dump`. Anything else raises TypeError naming
    the type: an adapter must decide what an unfamiliar object means, not
    have its attributes dumped.
    """
    if _depth > MAX_DEPTH:
        raise TypeError(f"jsonable: nesting deeper than {MAX_DEPTH}; a cycle or a whole object graph")
    nxt = _depth + 1
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        return int(obj)
    if isinstance(obj, float):
        return finite(obj)[0]
    if isinstance(obj, complex):
        return {"re": finite(obj.real)[0], "im": finite(obj.imag)[0]}
    if isinstance(obj, enum.Enum):
        return jsonable(obj.value, properties=properties, _depth=nxt)
    if isinstance(obj, (pathlib.PurePath,)):
        return str(obj)
    if isinstance(obj, (_dt.datetime, _dt.date)):
        return obj.isoformat()
    numpy_value = _from_numpy(obj)
    if numpy_value is not _NOT_NUMPY:
        return jsonable(numpy_value, properties=properties, _depth=nxt)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out: Dict[str, Any] = {}
        for f in dataclasses.fields(obj):
            out[f.name] = jsonable(getattr(obj, f.name), properties=properties, _depth=nxt)
        if properties:
            for name in _public_properties(type(obj)):
                if name in out:
                    continue
                try:
                    value = getattr(obj, name)
                except Exception:  # noqa: BLE001 - a property that cannot be read is omitted, not guessed
                    continue
                try:
                    out[name] = jsonable(value, properties=properties, _depth=nxt)
                except TypeError:
                    continue
        return out
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        return jsonable(obj.model_dump(mode="python"), properties=properties, _depth=nxt)
    if isinstance(obj, Mapping):
        return {str(k): jsonable(v, properties=properties, _depth=nxt) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v, properties=properties, _depth=nxt) for v in obj]
    if isinstance(obj, (set, frozenset)):
        items = [jsonable(v, properties=properties, _depth=nxt) for v in obj]
        try:
            return sorted(items)
        except TypeError:
            return items
    raise TypeError(
        f"jsonable: no rule for {type(obj).__module__}.{type(obj).__qualname__}; "
        f"the adapter must say what this object means"
    )


_NOT_NUMPY = object()


def _from_numpy(obj: Any) -> Any:
    """The Python equivalent of a numpy scalar or array, or _NOT_NUMPY."""
    module = type(obj).__module__
    if not module.startswith("numpy"):
        return _NOT_NUMPY
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if hasattr(obj, "item"):
        return obj.item()
    return _NOT_NUMPY


def _public_properties(cls: type) -> List[str]:
    names: List[str] = []
    for klass in cls.__mro__:
        for name, attr in vars(klass).items():
            if isinstance(attr, property) and not name.startswith("_") and name not in names:
                names.append(name)
    return names


# ---------------------------------------------------------------------------
# Building SourcedValues
# ---------------------------------------------------------------------------


def sourced(
    value: Any,
    unit: str,
    provenance: Provenance,
    *,
    ident: Optional[str] = None,
    label: Optional[str] = None,
    interval: Optional[Interval] = None,
) -> SourcedValue:
    """A SourcedValue from a library number, unrounded, non-finite named."""
    if provenance.get("kind") not in PROVENANCE_KINDS:
        raise ValueError(f"provenance kind {provenance.get('kind')!r} is not one of {PROVENANCE_KINDS}")
    out: SourcedValue
    if value is None:
        if interval is None:
            raise ValueError("a SourcedValue with no value must carry an interval saying why")
        out = {"value": None, "unit": unit, "provenance": provenance}
    else:
        number, nonfinite = finite(value)
        out = {"value": number, "unit": unit, "provenance": provenance}
        if nonfinite is not None:
            out["nonfinite"] = nonfinite  # type: ignore[typeddict-item]
    if ident is not None:
        out["id"] = ident
    if label is not None:
        out["label"] = label
    if interval is not None:
        out["interval"] = interval
    return out


def computed(method: str, inputs: Sequence[str] = (), note: Optional[str] = None) -> Provenance:
    """Provenance of a number Caterva derived. `method` names the derivation
    in the words the library or its report uses."""
    p: Provenance = {"kind": "computed", "method": method, "inputs": list(inputs)}
    if note:
        p["note"] = note
    return p


def chosen(by: str, reason: Optional[str] = None) -> Provenance:
    """Provenance of a number somebody chose: the person (`user`) or a
    stated default of the command (`default`)."""
    if by not in CHOSEN_BY:
        raise ValueError(f"chosen by {by!r}; expected one of {CHOSEN_BY}")
    p: Provenance = {"kind": "chosen", "by": by}  # type: ignore[typeddict-item]
    if reason:
        p["reason"] = reason
    return p


def placeholder(reason: str, table: Optional[str] = None) -> Provenance:
    """Provenance of a number nobody measured that stands in for one that
    could be. `reason` is the library's sentence, never a summary of it."""
    if not reason or not reason.strip():
        raise ValueError("a placeholder without a reason is the thing this contract exists to prevent")
    p: Provenance = {"kind": "placeholder", "reason": reason}
    if table:
        p["table"] = table
    return p


def fitted(method: str, **fit: Any) -> Provenance:
    info: FitInfo = {"method": method}
    for key in ("n_points", "residual", "stderr", "r_squared"):
        if key in fit and fit[key] is not None:
            info[key] = fit[key]  # type: ignore[literal-required]
    return {"kind": "fitted", "fit": info}


def measured_from_measurement(
    m: Any,
    *,
    scope: Sequence[str] = (),
    registry: Optional[str] = None,
    url: Optional[str] = None,
) -> Provenance:
    """Provenance of a compose `export.Measurement`.

    `registry` and `url` are passed by the adapter, which knows which
    database its search read; neither is parsed out of the citation text.
    """
    citation: Citation = {"text": str(m.citation)}
    reg = getattr(m, "citation_source", None) or registry
    if reg:
        citation["registry"] = str(reg)
    if getattr(m, "reference_id", None):
        citation["reference_id"] = str(m.reference_id)
    if url:
        citation["url"] = url
    if getattr(m, "source", None):
        citation["via"] = str(m.source)
    p: Provenance = {
        "kind": "measured",
        "citation": citation,
        "organism": getattr(m, "organism", None),
        "cross_species": bool(getattr(m, "cross_species", False)),
        "conditions": {
            "ph": _maybe_float(getattr(m, "assay_ph", None)),
            "temperature_c": _maybe_float(getattr(m, "assay_temperature_c", None)),
            "buffer": getattr(m, "assay_buffer", None),
            "unreported": [str(x) for x in (getattr(m, "assay_unreported", ()) or ())],
        },
        "commentary": getattr(m, "commentary", None),
        "scope": [str(s) for s in scope],
        "chosen_because": getattr(m, "chosen_because", None),
    }
    spread = getattr(m, "spread", None)
    p["spread"] = None if spread is None else {
        "low": float(spread.low),
        "high": float(spread.high),
        "unit": str(spread.unit),
        "carried": float(spread.carried),
        "n_values": int(spread.n_values),
        "references": [str(r) for r in spread.references],
        "sentence": spread.sentence(),
    }
    return p


def from_parameter_origin(
    origin: Any,
    *,
    reason: Optional[str] = None,
    registry: Optional[str] = None,
    url: Optional[str] = None,
) -> SourcedValue:
    """One number of a composed model, from `export.ParameterOrigin`.

    `export.provenance_of` is the one place compose decides whether a number
    is measured, a placeholder or chosen; this only transcribes it. The
    reason text for a placeholder or a chosen value is `reason` when the
    adapter has the resolver's words for it (ComposedModel.not_found),
    otherwise the origin's own `sentence()`, the same sentence the SBML,
    Antimony and CSV exports carry.
    """
    kind = origin.origin
    if kind == "measured":
        scope_obj = getattr(origin, "scope", None)
        concerns = [getattr(c, "plain", str(c)) for c in (scope_obj.concerns if scope_obj is not None else ())]
        prov = measured_from_measurement(origin.measurement, scope=concerns, registry=registry, url=url)
    elif kind == "placeholder":
        prov = placeholder(reason or origin.sentence(), table=getattr(origin, "table", None))
    elif kind == "chosen":
        prov = chosen("default", reason or origin.sentence())
    else:  # export.ParameterOrigin refuses any other origin at construction
        raise ValueError(f"unknown origin {kind!r} on {origin.identifier!r}")
    label = getattr(origin, "symbol", "") or None
    return sourced(origin.value, str(origin.unit or ""), prov, ident=str(origin.identifier), label=label)


def _maybe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return finite(value)[0]


def outcome_for(kind: str, exit_code: int, summary: str, refusal: Optional[str] = None) -> Outcome:
    """The Outcome for a finished run's CLI-equivalent exit code.

    `refusal` is the CLI's own refusal text and is required for exit 3: a
    refusal the page cannot explain is the silent failure this contract
    exists to prevent. For exit 4 the reason is the kind's NEGATIVE_MEANING.
    """
    if exit_code not in EXIT_MEANING:
        raise ValueError(
            f"exit code {exit_code} is not a finished run's: 2 is a 400 at submission, 1 is status failed"
        )
    reason: Optional[str] = None
    if exit_code == 3:
        if not refusal or not refusal.strip():
            raise ValueError(f"{kind}: a refusal (exit 3) must carry the CLI's reason")
        reason = refusal
    elif exit_code == 4:
        if kind not in NEGATIVE_MEANING:
            raise ValueError(f"{kind}: the command it mirrors never exits 4")
        reason = NEGATIVE_MEANING[kind]
    return {"exit_code": exit_code, "meaning": EXIT_MEANING[exit_code],  # type: ignore[typeddict-item]
            "summary": summary, "reason": reason}


#: Every TypedDict the page mirrors, by name. The mirror test walks this.
MIRRORED_TYPES: Tuple[str, ...] = tuple(
    name for name, value in list(globals().items())
    if isinstance(value, type) and issubclass(value, dict) and hasattr(value, "__required_keys__")
    and not name.startswith("_")
)

#: Every string union the page mirrors: TS type name -> members.
MIRRORED_UNIONS: Mapping[str, Tuple[str, ...]] = {
    "RunKind": RUN_KINDS,
    "RunStatus": RUN_STATUSES,
    "OutcomeMeaning": OUTCOME_MEANINGS,
    "ProvenanceKind": PROVENANCE_KINDS,
    "ChosenBy": CHOSEN_BY,
    "Nonfinite": NONFINITE,
    "ErrorCode": ERROR_CODES,
    "Need": NEEDS,
    "Theme": THEMES,
    "EventName": EVENT_NAMES,
    "SectionStatus": SECTION_STATUSES,
}

#: Constants the page mirrors, by name.
MIRRORED_CONSTANTS: Mapping[str, Any] = {
    "STUDIO_API_VERSION": STUDIO_API_VERSION,
    "SESSION_HEADER": SESSION_HEADER,
    "SESSION_META_NAME": SESSION_META_NAME,
    "TOKEN_PLACEHOLDER": TOKEN_PLACEHOLDER,
    "MAX_BODY_BYTES": MAX_BODY_BYTES,
    "MAX_VIEWER_ATOMS": MAX_VIEWER_ATOMS,
}
