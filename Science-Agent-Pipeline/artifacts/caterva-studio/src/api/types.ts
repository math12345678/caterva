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
export const SESSION_META_NAME = "caterva-session";
export const TOKEN_PLACEHOLDER = "__CATERVA_SESSION_TOKEN__";
export const MAX_BODY_BYTES = 1048576;
export const MAX_VIEWER_ATOMS = 60000;

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
export type RunStatus = "queued" | "running" | "done" | "failed" | "cancelled" | "interrupted";
export type OutcomeMeaning = "produced" | "refused" | "negative";
export type ProvenanceKind = "measured" | "fitted" | "computed" | "placeholder" | "chosen";
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

export interface NetworkCapability {
  checked: boolean;
  reachable: boolean | null;
  hosts: Record<string, boolean | null>;
  checked_at: string | null;
  reason: string | null;
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
  compounds: Record<string, string>;
  measured: number;
  placeholders: number;
}

export interface Concern {
  source: string;
  severity: string;
  detail: string;
  remedy: string;
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
}

export interface StabilityView {
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
}

export interface BindResult {
  mode: string;
  compounds: string[];
  survey: Record<string, unknown>[];
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

export interface CoordinatesResponse {
  pdb_id: string;
  citation: Citation;
  atoms: AtomColumns;
  count: number;
  truncated: boolean;
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
}

export interface DirectoryRequest {
  directory: string;
}

export interface ReplicaRow {
  name: string;
  mean: SourcedValue;
  error: SourcedValue;
  verdict: string;
}

export interface ConvergenceResult {
  quantity: string;
  unit: string;
  verdict: string;
  replicas: ReplicaRow[];
  report_markdown: string;
  summary: Record<string, unknown>;
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
}

export interface FepReplicaRow {
  rep: number;
  complex_kj: SourcedValue;
  solvent_kj: SourcedValue;
  dg_kcal: SourcedValue;
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
}

export interface ComplexCheckRequest {
  directory: string;
  ligand: string;
}

export interface ComplexCheckResult {
  kept: boolean;
  values: Record<string, SourcedValue>;
  report_text: string;
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
