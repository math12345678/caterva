/**
 * The studio's HTTP contract, mirrored from caterva/studio/contract.py.
 *
 * Every name, key and string union here must match that module exactly:
 * caterva/tests/test_studio_contract.py reads this file and fails on any
 * difference in a type's keys, in which keys are optional, or in a union's
 * members. `field?: T` is a key Python declares in a `total=False` class;
 * `T | null` is Python's `Optional[T]`. Change the two together, in one
 * commit, and only in the section you own (docs/studio/CONTRACT.md,
 * "Ownership map").
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const STUDIO_API_VERSION = 1;
export const SESSION_HEADER = "X-Caterva-Session";
export const TOKEN_FRAGMENT_KEY = "token";
export const PAGE_MARKER_NAME = "caterva-studio-page";
export const PAGE_MARKER_CONTENT = "token-in-url-fragment";
export const MAX_BODY_BYTES = 1048576;
export const MAX_VIEWER_ATOMS = 60000;
export const MAX_SSA_EVENTS = 200000;

// ---------------------------------------------------------------------------
// String unions
// ---------------------------------------------------------------------------

export type RunKind =
  | "compose"
  | "constants"
  | "sim"
  | "bind"
  | "structure"
  | "prepare"
  | "md.setup"
  | "md.summarise"
  | "analyze"
  | "fep.status"
  | "complex.check"
  | "rates";
export type RunStatus =
  | "queued"
  | "running"
  | "cancelling"
  | "done"
  | "failed"
  | "cancelled"
  | "abandoned"
  | "interrupted";
export type OutcomeMeaning = "produced" | "refused" | "negative" | "network";
/** The five kinds the engine emits (CONTRACT.md 9); mirrored by contract.PROVENANCE_KINDS. */
export type ProvenanceKind = "measured" | "fitted" | "computed" | "placeholder" | "chosen";
/**
 * The marks the page draws: the engine's five and `ai`, "suggested by an assistant, not a measurement"
 * (CONTRACT.md 9 and 17.3). No server answer carries `ai`: it marks assistant text and unconfirmed suggestions.
 */
export type MarkKind = ProvenanceKind | "ai";
export type ChosenBy = "user" | "default";
export type Nonfinite = "nan" | "inf" | "-inf";
export type ErrorCode =
  | "malformed"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "method_not_allowed"
  | "conflict"
  | "too_large"
  | "unsupported_media_type"
  | "unavailable"
  | "crash";
export type Need = "network" | "literature" | "gromacs";
export type Theme = "system" | "light" | "dark";
export type EventName = "status" | "stage" | "log" | "result" | "error" | "end";
export type SectionStatus = "answered" | "refused" | "partly_refused";

// ---------------------------------------------------------------------------
// Provenance
// ---------------------------------------------------------------------------

export interface Citation {
  text: string;
  registry?: string | null;
  reference_id?: string | null;
  url?: string | null;
  title?: string | null;
  journal?: string | null;
  year?: number | null;
  doi?: string | null;
  pubmed?: string | null;
  via?: string | null;
}

export interface Conditions {
  ph: number | null;
  temperature_c: number | null;
  buffer: string | null;
  unreported: string[];
}

export interface Spread {
  low: number;
  high: number;
  unit: string;
  carried: number;
  n_values: number;
  references: string[];
  sentence: string;
}

export interface FitInfo {
  method: string;
  n_points?: number | null;
  residual?: number | null;
  stderr?: number | null;
  r_squared?: number | null;
}

export interface Provenance {
  kind: ProvenanceKind;
  citation?: Citation;
  organism?: string | null;
  cross_species?: boolean;
  conditions?: Conditions;
  commentary?: string | null;
  scope?: string[];
  spread?: Spread | null;
  chosen_because?: string | null;
  reason?: string | null;
  table?: string | null;
  method?: string | null;
  inputs?: string[];
  fit?: FitInfo;
  by?: ChosenBy;
  note?: string | null;
}

export interface Interval {
  low: number | null;
  high: number | null;
  meaning: string;
}

export interface SourcedValue {
  value: number | null;
  unit: string;
  provenance: Provenance;
  id?: string;
  label?: string;
  nonfinite?: Nonfinite;
  interval?: Interval;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export interface ApiError {
  code: ErrorCode;
  message: string;
  field?: string | null;
  details?: Record<string, unknown>;
}

export interface ErrorBody {
  error: ApiError;
}

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

export interface Health {
  ok: boolean;
  version: string;
  api_version: number;
  started_at: string;
}

export interface LiteratureCapability {
  available: boolean;
  reason: string | null;
}

/** One host's own latest outcome. */
export interface HostStatus {
  reachable: boolean | null;
  checked_at: string | null;
  /** "use" (a real request) or "probe" (the explicit check). */
  source: string | null;
  /** Why the host did not answer. */
  reason: string | null;
}

export interface NetworkCapability {
  checked: boolean;
  /** What was checked adds up to: every host with an outcome answered (true), one did not (false), none checked (null). */
  reachable: boolean | null;
  hosts: Record<string, boolean | null>;
  /** Each host's own latest outcome; read a host's entry, not `reachable`, to know whether it can be asked. */
  host_status: Record<string, HostStatus>;
  checked_at: string | null;
  reason: string | null;
  /**
   * Where the answer came from: "use" (a real BRENDA, UniProt, NCBI or RCSB
   * request just worked or failed), "probe" (the explicit check), or null
   * while nothing has happened yet (`checked` is false only then).
   */
  source: string | null;
}

export interface GromacsCapability {
  found: boolean;
  path: string | null;
  version: string | null;
  reason: string | null;
}

export interface RatesCapability {
  available: boolean;
  reason: string | null;
}

export interface UiCapability {
  built: boolean;
  static_dir: string;
  reason: string | null;
}

export interface DataDirCapability {
  path: string;
  writable: boolean;
  runs: number;
  reason: string | null;
}

export interface KindCapability {
  available: boolean;
  title: string;
  command: string;
  needs: Need[];
  reason: string | null;
}

export interface Capabilities {
  version: string;
  api_version: number;
  python: string;
  platform: string;
  frozen: boolean;
  literature: LiteratureCapability;
  network: NetworkCapability;
  gromacs: GromacsCapability;
  rates: RatesCapability;
  ui: UiCapability;
  data_dir: DataDirCapability;
  kinds: Record<string, KindCapability>;
  dev_origin: string | null;
}

export interface Settings {
  theme: Theme;
  max_parallel_runs: number;
  confirm_delete: boolean;
  /** Optional on PUT (kept when omitted); always present on GET. */
  gromacs_path?: string | null;
  /** True: no network probe, and runs of kinds that need the network are refused (503). */
  offline?: boolean;
  /** How many finished runs History keeps (10 to 5000, default 200); older ones go to the trash folder. */
  keep_runs?: number;
}

export interface NormaliseOrganismRequest {
  name: string;
}

export interface NormaliseOrganismResponse {
  organism: string | null;
  note: string | null;
}

export interface ShapesResponse {
  shapes: string[];
}

export interface DevSession {
  token: string;
  api_version: number;
}

// ---------------------------------------------------------------------------
// The enzyme finder (GET /api/enzymes/find, GET /api/enzymes/{ec})
// ---------------------------------------------------------------------------

/** One UniProt entry the enzyme nomenclature lists under an EC number. */
export interface EnzymeProteinView {
  accession: string;
  /** HXK1_HUMAN */
  entry_name: string;
  /** The entry name without its organism suffix: HXK1. A UniProt mnemonic, which is not the gene symbol. */
  symbol: string;
  /** The gene symbol (HK1 for HXK1_HUMAN), or null when UniProt gives none. */
  gene?: string | null;
  /** What to show and put in the isoform field: the gene symbol, else the mnemonic. */
  label?: string;
  /** The names UniProt gives the protein, gene symbol first. */
  names?: string[];
  /** True when the isoform engine knows this label (rows naming the isozyme in other words match it). */
  engine_matches?: boolean;
}

/** A finder candidate; the required keys are what `caterva enzyme --json` prints. */
export interface EnzymeCandidate {
  ec: string;
  name: string;
  /** One plain line: why this enzyme is in the list. */
  why: string;
  /** Lower is stronger. */
  tier: number;
  reaction: string;
  class_path: string;
  alternative_names: string[];
  /** The organism code the proteins are for (HUMAN), or null. */
  organism: string | null;
  organism_proteins: EnzymeProteinView[];
  organism_protein_count: number;
  has_organism_protein: boolean;
  /** active, transferred or deleted. */
  status: string;
  superseded_by: string[];
  partial_match: boolean;
  /** How it matched: name, abbreviation, mnemonic, typo, ec or class. */
  matched_by: string;
  /** "EC 1.1.1.27 L-lactate dehydrogenase (human: LDHA, LDHB, LDHC)"; on a refusal's candidates. */
  label?: string;
  /** The `caterva compose` command that would use this enzyme. */
  compose?: string;
  /** The finder's recommendation. Never chosen for the person. */
  recommended?: boolean;
  /** What the finder says to check, on the candidate a query resolved to. */
  caution?: string | null;
}

export interface UniprotSuggestion {
  ec: string;
  name: string | null;
}

/** UniProt's protein-name search, asked only when the finder found nothing and the network was reachable. */
export interface EnzymeFallback {
  kind: string;
  suggestions: UniprotSuggestion[];
  note: string;
}

export interface EnzymeFindResponse {
  query: string;
  organism: string | null;
  organism_code: string | null;
  organism_label: string | null;
  release: string;
  /** resolved, ambiguous, partial, suggestions or none. */
  outcome: string;
  resolved_ec: string | null;
  how: string | null;
  cautions: string[];
  reason: string | null;
  recommended_ec: string | null;
  /** True when the query is an abbreviation or symbol: the candidates are what it can mean, even when there is one. */
  confirm_only: boolean;
  candidates_total: number;
  candidates: EnzymeCandidate[];
  fallback: EnzymeFallback | null;
  /** Why no fallback was offered when it could have been. */
  fallback_unavailable?: string;
  /** What the organism code covers when narrower than the name ("E. coli" is K-12). */
  organism_scope?: string;
}

export interface IsozymeList {
  organism: string | null;
  organism_label: string | null;
  count: number;
  proteins: EnzymeProteinView[];
  /** False for an organism the finder does not know: zero proteins then means "not known". */
  organism_known: boolean;
  /** True above 12 proteins: a broad class of different proteins, not isozymes of one enzyme. */
  broad: boolean;
  /** The notice for this EC number and organism, in words, or null for one protein or none. */
  note: string | null;
  /** What the organism code covers when narrower than the name ("E. coli" is K-12), or null. */
  organism_scope: string | null;
  /** Proteins of this family filed under other EC numbers, which this list may leave out, or null. */
  filed_elsewhere: string | null;
}

export interface EnzymeReplacement {
  ec: string;
  name: string;
}

export interface EnzymeDetail {
  ec: string;
  /** The nomenclature's name; for a transferred number the replacement's, for a deleted one "Deleted entry". */
  name: string;
  /** Why `name` is what it is for a transferred or deleted entry, else null. */
  name_note: string | null;
  replaced_by: EnzymeReplacement[];
  alternative_names: string[];
  reaction: string;
  class_path: string;
  status: string;
  superseded_by: string[];
  release: string;
  isozymes: IsozymeList;
}

/** A name that is not exactly one enzyme, refused by the one policy, as data. */
export interface NameRefusal {
  /** ambiguous, suggestions, none, lookup_failed or unknown_ec. */
  kind: string;
  /** True when the name is an abbreviation or symbol: the candidates are what it can mean. */
  confirm_only: boolean;
  /** The policy's own sentence, as the CLI prints it. */
  message: string;
  named_candidates: EnzymeCandidate[];
  /** The EC number the finder recommends, or null. */
  recommended: string | null;
  /** The flag that accepts a candidate, with {ec}: "--subject {ec}". */
  rerun_flag: string;
}

// ---------------------------------------------------------------------------
// Runs, jobs and events
// ---------------------------------------------------------------------------

export interface CreateRunBody {
  kind: RunKind;
  request: Record<string, unknown>;
  title?: string;
}

export interface Outcome {
  exit_code: number;
  meaning: OutcomeMeaning;
  summary: string;
  /** refused: the CLI's stderr text, verbatim; negative: NEGATIVE_MEANING[kind]; produced: null. */
  reason: string | null;
  /** Present on a refusal that was a name that is not exactly one enzyme. */
  name_refusal?: NameRefusal;
  /** Present when `meaning` is "network": which host, and what it answered. */
  network?: NetworkFailure;
  /** False when the run finished without a result (its /result is 404), so the page does not ask. */
  has_result?: boolean;
}

/** An upstream database that did not answer, read from a refusal's text. */
export interface NetworkFailure {
  /** "rest.uniprot.org", or null when the text names none. */
  host: string | null;
  /** The HTTP status of an error answer, or null for a timeout or a connection never made. */
  status: number | null;
  /** True when the request timed out rather than being refused. */
  timed_out: boolean;
}

export interface RunError {
  type: string;
  message: string;
  traceback?: string | null;
}

export interface ArtifactInfo {
  name: string;
  content_type: string;
  bytes: number;
  description: string;
}

export interface ProgressState {
  stage: string;
  label: string;
  fraction: number | null;
}

export interface RunRecord {
  schema: string;
  id: string;
  kind: RunKind;
  title: string;
  status: RunStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  caterva_version: string;
  cli: string[];
  request: Record<string, unknown>;
  outcome: Outcome | null;
  error: RunError | null;
  artifacts: ArtifactInfo[];
  progress: ProgressState | null;
}

export interface RunSummary {
  id: string;
  kind: RunKind;
  title: string;
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
  outcome: Outcome | null;
}

export interface RunList {
  runs: RunSummary[];
  next_cursor: string | null;
}

export interface RunCreated {
  run: RunRecord;
}

export interface StatusEvent {
  run_id: string;
  seq: number;
  at: string;
  status: RunStatus;
  outcome?: Outcome | null;
}

export interface StageEvent {
  run_id: string;
  seq: number;
  at: string;
  stage: string;
  label: string;
  fraction: number | null;
}

export interface LogEvent {
  run_id: string;
  seq: number;
  at: string;
  line: string;
}

export interface ResultEvent {
  run_id: string;
  seq: number;
  at: string;
  outcome: Outcome;
}

export interface ErrorEvent {
  run_id: string;
  seq: number;
  at: string;
  error: RunError;
}

export interface EndEvent {
  run_id: string;
  seq: number;
  at: string;
  status: RunStatus;
}

export interface StructuredSection {
  key: string;
  title: string;
  status: SectionStatus;
  text: string;
  refusals: string[];
  data: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// Kinetics kinds (owner: sci-kinetics)
// ---------------------------------------------------------------------------

/** The most rows of an event table a result carries; more are sent as every n-th row and the last (`rows`, `every`). */
export const SERIES_ROW_LIMIT = 20000;

export interface SweepRequest {
  parameters: string[];
  low?: number;
  high?: number;
  steps?: number;
}

export interface RobustnessRequest {
  samples: number | null;
}

export interface StochasticRequest {
  volume_l: number;
  end_s?: number | null;
  seed?: number | null;
}

export interface ComposeAnalyses {
  scale?: boolean;
  predictions?: boolean;
  crnt?: boolean;
  reduction?: boolean;
  identifiability?: boolean;
  design?: boolean;
  validate?: boolean;
  screen?: boolean;
  knockout?: string[];
  overexpress?: string[];
  robustness?: RobustnessRequest;
  stochastic?: StochasticRequest;
}

export interface ComposeRequest {
  description: string;
  subject?: string;
  organism?: string;
  substrate?: string;
  inhibitor?: string;
  product?: string;
  isoform?: string;
  any_mode?: boolean;
  compounds?: Record<string, string>;
  rank_against?: string;
  sweep?: SweepRequest;
  no_analysis?: boolean;
  no_simulate?: boolean;
  no_ranking?: boolean;
  analyses?: ComposeAnalyses;
}

export interface Recognition {
  rule: string;
  reading: string;
}

export interface SpeciesRow {
  id: string;
  initial: SourcedValue;
}

export interface ReactionRow {
  id: string;
  rate_law: string;
}

export interface MotifRow {
  name: string;
  basis: string;
  copies: number;
}

export interface ModelStructure {
  species: SpeciesRow[];
  reactions: ReactionRow[];
  parameters: SourcedValue[];
  conservation_laws: string[];
  unconserved: string[];
  concentration_unit: string;
  motifs: MotifRow[];
}

export interface SearchSummary {
  asked: boolean;
  refused: boolean;
  note: string | null;
  subject: string | null;
  ec: string | null;
  organism: string | null;
  substrate: string | null;
  isoform: string | null;
  /** Compounds a constant of this mechanism was looked up under. */
  compounds: Record<string, string>;
  /** Compounds the request named that the mechanism has no constant for; not searched. */
  unused_compounds: Record<string, string>;
  measured: number;
  placeholders: number;
}

export interface Concern {
  source: string;
  severity: string;
  detail: string;
  remedy: string;
  /** The "Qualified:" sentence of the verdict, on a concern that narrows what it licenses (the isozyme notice). */
  qualifier?: string;
}

export interface VerdictView {
  verdict: string;
  licence: string;
  behaviour: string | null;
  conclusion: string | null;
  concerns: Concern[];
  next_step: string | null;
  consulted: Record<string, string>;
  unavailable: Record<string, string>;
  text: string;
}

export interface ComplexNumber {
  re: number;
  im: number;
}

export interface FixedPointView {
  state: Record<string, number | null>;
  residual: number | null;
  eigenvalues: ComplexNumber[];
  classification: string;
  physical: boolean;
  stable: boolean;
  oscillatory: boolean;
  slowest_timescale: number | null;
  /** The engine's own line for this point, as the report prints it. */
  description?: string;
}

export interface StabilityView {
  /** An amount below zero by less than this is rounding, not a negative amount. */
  rounding_tolerance: number;
  /** The engine's sentence that the count of points found is an artefact of where the starts fell; null when not a line of equilibria. */
  count_caveat: string | null;
  starts_tried: number;
  species: string[];
  notes: string[];
  fixed_points: FixedPointView[];
  text: string;
}

export interface InvariantView {
  law: string;
  initial: number | null;
  final: number | null;
  worst_drift: number | null;
  held: boolean;
}

export interface TrajectoryView {
  times: (number | null)[];
  columns: Record<string, (number | null)[]>;
  end: number | null;
  points: number;
  window_basis: string;
  invariants: InvariantView[];
  checked: boolean;
  sound: boolean;
  unmeasured: string[];
  text: string;
}

export interface SensitivityRow {
  parameter: string;
  value: number | null;
  relative: number | null;
  absolute: number | null;
  negligible: boolean;
  unresolvable: boolean;
}

export interface SensitivityView {
  quantity: string;
  base_value: number | null;
  sensitivities: SensitivityRow[];
  skipped: Record<string, string>;
  conserved_by: string | null;
  resolution: number | null;
}

export interface ExportInfo {
  available: boolean;
  artifact: string | null;
  refused: string | null;
}

export interface ComposeResult {
  query: string;
  recognition: Recognition;
  model: ModelStructure;
  search: SearchSummary;
  verdict: VerdictView | null;
  stability: StabilityView | null;
  trajectory: TrajectoryView | null;
  sensitivity: SensitivityView | null;
  sweeps: Record<string, unknown>[];
  sections: StructuredSection[];
  notes: string[];
  report_markdown: string;
  exports: Record<string, ExportInfo>;
}

export interface ConstantsRequest {
  substrate: string;
  ec?: string;
  enzyme?: string;
  organism?: string;
  quantities?: string[];
  s0?: number;
  vmax?: number;
  concentration_unit?: string;
  basis?: string;
  title?: string;
  question?: string;
  seed?: number | null;
}

export interface ConstantRow {
  name: string;
  quantity: string;
  found: boolean;
  source: string;
  value: SourcedValue | null;
  alternatives: SourcedValue[];
  organisms_available: string[];
  isoforms_available: string[];
  modes_available: string[];
  variants_available: string[];
  raw: Record<string, unknown>;
}

export interface ConstantsResult {
  document_markdown: string;
  constants: ConstantRow[];
  supplied: SourcedValue[];
  sourced: string[];
  derived: string[];
  refusals: string[];
  disagreements: unknown[];
  defensible: boolean;
  /** How cite.py read the organism typed, which it prints to stderr; null when used as typed. */
  organism_note?: string | null;
  /** The isozyme notice compose carries, when the EC number is several proteins in the organism; null otherwise. */
  isozyme_notice?: IsozymeNoticeView | null;
}

export interface IsozymeNoticeView {
  ec: string;
  organism: string;
  organism_label: string;
  count: number;
  /** Gene symbols (or entry-name stems where UniProt gives none). */
  symbols: string[];
  /** True above 12 proteins: a broad class, not isozymes of one enzyme. */
  broad: boolean;
  headline: string;
  detail: string;
  remedy: string;
  text: string;
}

export interface SimRequest {
  seed: number;
  bimolecular?: boolean;
  a0?: number;
  b0?: number;
  k?: number;
  end?: number;
}

export interface SimResult {
  columns: string[];
  series: Record<string, (number | null)[]>;
  events: number;
  seed: number;
  parameters: Record<string, SourcedValue>;
  final: Record<string, SourcedValue>;
  expected: SourcedValue;
  report_text: string;
  /** Rows in the run's event table (initial, one per event, final). */
  rows?: number;
  /** `series` holds every `every`-th row and the last one; 1 when it holds them all. */
  every?: number;
}

export interface ComputedDG {
  value: number;
  error?: number | null;
  unit?: "kcal" | "kj";
}

export interface BindRequest {
  ec: string;
  mode: "inhibitor" | "list" | "survey";
  organism?: string;
  inhibitor?: string;
  state?: "free" | "ternary";
  isoform?: string;
  computed?: ComputedDG;
}

export interface KiRow {
  ki: SourcedValue;
  dg: SourcedValue;
  compound: string;
  organism: string;
  reference: string | null;
  commentary: string | null;
  mode: string;
  versus: string | null;
  preparation: string | null;
  isoform: string | null;
  excluded: string | null;
}

export interface BindTarget {
  compound: string;
  organism: string;
  state: string;
  used: KiRow[];
  excluded: KiRow[];
  band_low: SourcedValue | null;
  band_high: SourcedValue | null;
  references: string[];
  caveats: string[];
}

export interface BindVerdict {
  word: string;
  gap_kcal: SourcedValue;
  ki_fold: SourcedValue;
  detail: string;
  computed: SourcedValue;
  /** The computed value's stated error (sigma), in kcal/mol like `computed`. */
  computed_error?: SourcedValue;
  /** The temperature the Ki fold was judged at: the rows' mean assay temperature, or the 25 C default. */
  temperature_c?: SourcedValue;
}

export interface BindSurveyRow {
  compound: string;
  organism: string;
  isoform: string | null;
  rows: number;
  used: number;
  references: string[];
  band_low: SourcedValue | null;
  band_high: SourcedValue | null;
  benchmark: boolean;
  why_not: string[];
}

export interface BindResult {
  mode: string;
  compounds: string[];
  /** One row per compound, organism and isoform, for mode "survey". */
  survey: BindSurveyRow[];
  target: BindTarget | null;
  verdict: BindVerdict | null;
  report_text: string;
}

// ---------------------------------------------------------------------------
// Structure kinds (owner: sci-structure)
// ---------------------------------------------------------------------------

export interface StructureRequest {
  subject: string;
  organism?: string;
  gene?: string;
  uniprot?: string;
  ligand?: string;
  top?: number;
  chimerax?: boolean;
}

export interface BoundMoleculeView {
  component: string;
  name: string;
  role: string;
}

export interface ProteinRow {
  accession: string;
  gene: string | null;
  name: string;
  organism: string;
  entries: number;
  chosen: boolean;
  /** The protein's UniProt entry page. */
  url?: string;
}

export interface StructureRow {
  pdb_id: string;
  title: string;
  method: string;
  resolution: SourcedValue | null;
  organisms: string[];
  uniprot: string[];
  bound: BoundMoleculeView[];
  citation: Citation;
  binds_ligand: boolean | null;
  /** Every PDB entry's own DOI (10.2210/pdbXXXX/pdb), paper or not. */
  entry_doi?: string;
  entry_url?: string;
  /** False when the primary citation is "To Be Published". */
  published?: boolean;
}

export interface StructureResult {
  ec: string;
  organism: string | null;
  ligand: string | null;
  proteins: ProteinRow[];
  chosen: string | null;
  undecided: string | null;
  entries: StructureRow[];
  total: number;
  report_markdown: string;
  chimerax_artifact: string | null;
  organism_note?: string | null;
  /** How many entries the report lists; `entries` holds every ranked one. */
  top?: number;
  /** The databases the search read, cited. */
  sources?: Citation[];
  /** The name `subject` was, when it was a name; `ec` is what it resolved to. */
  subject_name?: string | null;
  /** The sentences the one name policy wants read before the report, as the command prints them. */
  subject_notes?: string[];
}

export interface AtomColumns {
  x: number[];
  y: number[];
  z: number[];
  element: string[];
  atom_name: string[];
  resname: string[];
  chain: string[];
  resseq: number[];
  hetero: boolean[];
}

/** A catalytic residue as `caterva prepare` places it on one chain. */
export interface CatalyticSite {
  chain: string;
  /** Author numbering, as atoms.resseq gives it. */
  resseq: string;
  resname: string | null;
  expected: string;
  conserved: boolean;
  roles: string;
  /** "His194 of P00341": the reference residue it was mapped from. */
  reference: string;
}

/** Which M-CSA mechanism the catalytic residues come from, and why. */
export interface CatalyticReference {
  mcsa_id: number;
  enzyme: string;
  uniprot: string;
  how: string;
  identity: SourcedValue;
  citation: Citation;
  rejected: string[];
}

export interface CoordinatesResponse {
  pdb_id: string;
  citation: Citation;
  atoms: AtomColumns;
  count: number;
  truncated: boolean;
  title?: string;
  method?: string;
  resolution?: SourcedValue | null;
  omitted?: string | null;
  chains?: string[];
  catalytic?: CatalyticSite[];
  catalytic_reference?: CatalyticReference | null;
  /** Why no catalytic residue is given, in the audit's words. */
  catalytic_reason?: string | null;
  /** The same audit's findings, as `caterva prepare ENTRY` lists them (no pH). */
  findings?: FindingRow[];
}

export interface PrepareRequest {
  entry: string;
  ph?: number;
  no_cache?: boolean;
}

export interface ChainSummaryRow {
  chain: string;
  blocks: number;
  near_site: number;
  catalytic_intact: boolean;
}

export interface FindingRow {
  severity: string;
  chain: string | null;
  residues: string[];
  distance: SourcedValue | null;
  what: string;
  source: string;
  check?: string;
  catalytic?: boolean;
  near_active_site?: boolean;
}

export interface PrepareResult {
  pdb_id: string;
  title: string;
  method: string;
  resolution: SourcedValue | null;
  r_free: SourcedValue | null;
  chains: string[];
  clean: boolean;
  chain_summary: ChainSummaryRow[];
  findings: FindingRow[];
  catalytic: Record<string, unknown>[];
  reference: Record<string, unknown> | null;
  protonation: Record<string, unknown>[] | null;
  not_checked: string[];
  report_markdown: string;
  audit: Record<string, unknown>;
  entry_citation?: Citation;
  clean_chains?: string[];
  ph?: SourcedValue | null;
  active_site_radius?: SourcedValue;
}

export interface MdSetupRequest {
  pdb: string;
  chain?: string;
  out?: string;
  subject?: string;
  organism?: string;
  substrate?: string;
  temperature_k?: number;
  ph?: number;
  ns?: number;
  ionic_strength_m?: number;
  seed?: number;
  replicas?: number;
}

export interface MdParameterRow {
  name: string;
  value: string;
  origin: string;
  source: string;
  /** For a `chosen` row: `user` when this request set it, else `default`. */
  by?: "user" | "default";
  /** For a `method` or `measured` row: its source as a Citation (the METHODS entry, or the PDB entry). */
  citation?: Citation;
}

export interface MdSetupResult {
  out_dir: string;
  pdb: string;
  chain: string | null;
  temperature: SourcedValue;
  ph: SourcedValue | null;
  parameters: MdParameterRow[];
  files: string[];
  note: string | null;
  report_text: string;
  ns?: SourcedValue;
  ionic_strength?: SourcedValue;
  replicas?: number;
  seeds?: number[];
  /** PROVENANCE.md as written. */
  provenance_markdown?: string;
}

export interface DirectoryRequest {
  directory: string;
}

export interface ReplicaRow {
  name: string;
  mean: SourcedValue;
  error: SourcedValue;
  verdict: string;
  frames?: number;
  kept?: number;
  plateaued?: boolean;
  effective_samples?: SourcedValue | null;
}

export interface ConvergenceResult {
  quantity: string;
  unit: string;
  verdict: string;
  replicas: ReplicaRow[];
  report_markdown: string;
  summary: Record<string, unknown>;
  mean?: SourcedValue;
  spread?: SourcedValue | null;
  ci95?: SourcedValue | null;
  reasons?: string[];
  written?: string | null;
}

export interface AnalyzeRequest {
  directory: string;
  mode?: "native" | "gromacs" | "no_run" | "script_only";
}

export interface DistanceRow {
  label: string;
  crystal: SourcedValue | null;
  mean: SourcedValue;
  drift: SourcedValue | null;
  moved: boolean;
  verdict: string;
  spread?: SourcedValue | null;
  ci95?: SourcedValue | null;
  /** "held" or "moved" once the distance is a consistent result, else null. */
  change?: string | null;
  reasons?: string[];
  per_replica?: Record<string, unknown>[];
}

export interface AnalyzeResult {
  pdb: string;
  chain: string | null;
  source: string;
  all_consistent: boolean;
  distances_consistent: boolean;
  distances: DistanceRow[];
  flexibility: Record<string, unknown> | null;
  hbonds: Record<string, unknown>[] | null;
  rotamers: Record<string, unknown>[] | null;
  angles: Record<string, unknown>[];
  water: Record<string, unknown>[] | null;
  faces: Record<string, unknown>[] | null;
  script_written: boolean;
  report_markdown: string;
  mode?: string;
  /** Solvent-accessible area of each catalytic residue; null when not measured (see exposure_not_measured). */
  exposure?: Record<string, unknown>[] | null;
  exposure_not_measured?: string | null;
  /** Principal motions of the catalytic residues' heavy atoms; null when not measured. */
  motions?: Record<string, unknown> | null;
  measured?: boolean;
  written?: string[];
  replicas?: string[];
  catalytic?: Record<string, unknown>[];
  notes?: string[];
  counts?: Record<string, number>;
  gmx?: string | null;
  /** Sections a newer Analysis carries that the adapter does not name. */
  extra?: Record<string, unknown>;
  /** The library's verdict thresholds by the section they judge, each a value the command chose. */
  thresholds?: Record<string, SourcedValue[]>;
}

export interface FepReplicaRow {
  rep: number;
  complex_kj: SourcedValue;
  solvent_kj: SourcedValue;
  dg_kcal: SourcedValue;
  complex_err_kj?: SourcedValue;
  solvent_err_kj?: SourcedValue;
  complex_estimator?: string;
  solvent_estimator?: string;
}

export interface FepStatusResult {
  compound: string;
  organism: string;
  temperature_k: SourcedValue | null;
  restraint_correction: SourcedValue | null;
  replicas: FepReplicaRow[];
  band_low: SourcedValue | null;
  band_high: SourcedValue | null;
  computed: SourcedValue | null;
  verdict: BindVerdict | null;
  not_a_result: string | null;
  warnings: string[];
  report_text: string;
  replicas_planned?: number;
  lines?: string[];
  references?: string[];
  caveats?: string[];
  state?: string;
  sigma?: SourcedValue | null;
  sem?: SourcedValue | null;
}

export interface ComplexCheckRequest {
  directory: string;
  ligand: string;
}

export interface ComplexCheckResult {
  kept: boolean;
  values: Record<string, SourcedValue>;
  report_text: string;
  ligand?: string;
  ca_atoms?: number;
  frames?: number | null;
}

/** Reserved until `caterva rates` is integrated (contract.py RatesRequest). */
export type RatesRequest = Record<string, unknown>;
export type RatesResult = Record<string, unknown>;

/** Kind -> what exit 4 means for its command, as contract.NEGATIVE_MEANING. */
export const NEGATIVE_MEANING: Partial<Record<RunKind, string>> = {
  bind: "the computed value disagrees with the measured band",
  prepare: "every chain has a blocking defect",
  "md.summarise": "the replicas are not (yet) a consistent result",
  analyze: "at least one quantity is not a result (unconverged, replicas disagree, one sample)",
  "fep.status": "disagrees, or not yet a result (one replica, missing legs)",
  "complex.check": "the ligand left its pose",
};

/** Kind -> [request type name, result type name], as contract.KIND_SHAPES. */
export const KIND_SHAPES: Record<RunKind, readonly [string, string]> = {
  compose: ["ComposeRequest", "ComposeResult"],
  constants: ["ConstantsRequest", "ConstantsResult"],
  sim: ["SimRequest", "SimResult"],
  bind: ["BindRequest", "BindResult"],
  structure: ["StructureRequest", "StructureResult"],
  prepare: ["PrepareRequest", "PrepareResult"],
  "md.setup": ["MdSetupRequest", "MdSetupResult"],
  "md.summarise": ["DirectoryRequest", "ConvergenceResult"],
  analyze: ["AnalyzeRequest", "AnalyzeResult"],
  "fep.status": ["DirectoryRequest", "FepStatusResult"],
  "complex.check": ["ComplexCheckRequest", "ComplexCheckResult"],
  rates: ["RatesRequest", "RatesResult"],
};

/** The request type each kind takes, for typed submission. */
export interface RunRequests {
  compose: ComposeRequest;
  constants: ConstantsRequest;
  sim: SimRequest;
  bind: BindRequest;
  structure: StructureRequest;
  prepare: PrepareRequest;
  "md.setup": MdSetupRequest;
  "md.summarise": DirectoryRequest;
  analyze: AnalyzeRequest;
  "fep.status": DirectoryRequest;
  "complex.check": ComplexCheckRequest;
  rates: RatesRequest;
}

/** The result type each kind returns from /api/runs/{id}/result. */
export interface RunResults {
  compose: ComposeResult;
  constants: ConstantsResult;
  sim: SimResult;
  bind: BindResult;
  structure: StructureResult;
  prepare: PrepareResult;
  "md.setup": MdSetupResult;
  "md.summarise": ConvergenceResult;
  analyze: AnalyzeResult;
  "fep.status": FepStatusResult;
  "complex.check": ComplexCheckResult;
  rates: RatesResult;
}
