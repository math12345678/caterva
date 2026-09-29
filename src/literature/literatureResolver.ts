/**
 * Bridge from this tree to the real literature resolution layer.
 *
 * WHY THIS EXISTS
 *
 * `LiteratureService` is an in-memory `Map`. A caller must hand it
 * `Literature` objects before it can recommend anything, and it reaches no
 * database, registry or API of its own -- despite the name, and despite
 * `LITERATURE_INTEGRATION_GUIDE.md` describing a literature integration.
 * Everything it "recommends" is something the caller already had.
 *
 * Caterva's actual literature layer is `Tests/fallback_logic.py`
 * (`resolve_kinetic_value`), which walks BRENDA exact match -> BRENDA
 * cross-species -> PubMed candidates, and returns a value, its unit, the
 * organism it was measured in, a citation, and the STRENDA assay
 * conditions (pH, temperature, buffer) -- or an honest `found: false`. It
 * never fabricates a number.
 *
 * The production API server already reaches it through a JSON bridge,
 * `science_agent_runner.py`, spawned by `lib/scienceAgent.ts`. This module
 * spawns the SAME script over the SAME protocol. A third path to the same
 * data would be a third thing to keep in sync, and this repository has
 * already been bitten by duplicate sources of truth more than once.
 */

import { spawn } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

import { logger } from '../logger';
import { REPO_ROOT, resolvePythonExecutable } from '../engine/catervaBridge';

/** Which kinetic constant to resolve. Each call resolves exactly one, so a
 *  cross-species Ki can never borrow a verified Km's provenance (ADR 0008). */
export type KineticQuantity = 'km' | 'ki' | 'kcat';

export interface ResolverQuery {
  enzymeName?: string;
  substrate: string;
  organism: string;
  /** Optional: resolved live via UniProt when omitted. */
  ecNumber?: string;
  quantity?: KineticQuantity;
  /**
   * Total enzyme concentration [E]0, **in mM**, supplied by the caller.
   *
   * Only meaningful with `quantity: 'kcat'`, where it bridges a resolved
   * turnover number to a simulable Vmax = kcat * [E]0. BRENDA does not
   * report [E]0 per row, and ADR 0013 rules that it is an explicit caller
   * input -- never defaulted, never inferred, never resolved from
   * literature. Omitting it means a resolved kcat stays a citable number
   * that no simulation can use, which is the honest outcome rather than a
   * guessed enzyme concentration.
   */
  enzymeConc?: number;
  /**
   * Opt in to a value measured in a different, sufficiently related
   * organism (ADR 0024). Defaults to false.
   *
   * Lisa Jeske (BRENDA/DSMZ) asked for this to be an active decision --
   * "the student/teacher must actively check a box" -- and a checkbox that
   * exists only in a subprocess payload is not one. Two further things
   * must stay true for it to mean anything: absent must read as false, and
   * enabling it must not disable the relatedness check, which continues to
   * reject candidates that are not plausibly comparable.
   */
  allowCrossSpecies?: boolean;
  /**
   * The conditions the model is meant to represent, for Bakker's
   * condition-proximity axis.
   *
   * All five fields or none. A partial reference is refused rather than
   * completed: supplying a pH and no temperature states half of what the
   * model represents, and filling the other half with 37 C would silently
   * assume a mammal -- the exact assumption this axis exists not to make.
   */
  physiologicalReference?: {
    ph: number;
    temperatureC: number;
    basis: string;
    phTolerance: number;
    temperatureToleranceC: number;
  };
}

export interface ReliabilityAxis {
  grade: string;
  reason: string;
}

/** Mirrors protein_variant.VariantVerdict (ADR 0029). snake_case because it
 * crosses the wire as Python emits it. */
export interface VariantVerdict {
  /** "wild_type" | "variant" | "unstated" | "absent" */
  status: string;
  /** "mutant" | "isozyme" when status is "variant". */
  kind?: string | null;
  /** The exact substring that decided it. A verdict with no evidence is an
   * assertion; this is what lets a reader check the classifier. */
  evidence?: string | null;
  recombinant?: boolean;
  reason: string;
}

/** Mirrors buffer_identity.BufferIdentity (ADR 0028). */
export interface BufferIdentity {
  raw: string;
  species?: string | null;
  cid?: number | null;
  /** Parent (neutral form) compound — what identity is compared on, so a
   * salt and its free base read as one buffer system. */
  parent_cid?: number | null;
  /** Concentration text, stripped for the lookup and NOT compared. */
  concentration_text?: string | null;
  status: string;
  reason?: string | null;
}

/** Mirrors effector.Effector (ADR 0032). */
export interface Effector {
  raw: string;
  compound_text: string;
  /** "present" | "absent" | "unstated" */
  presence: string;
  concentration_text?: string | null;
  identity?: BufferIdentity | null;
}

export interface ReliabilityAxes {
  assayCompleteness: ReliabilityAxis;
  conditionProximity: ReliabilityAxis;
  organismMatch: ReliabilityAxis;
  /** Why no single number is offered. Carried rather than documented, so a
   * caller that goes looking for a total finds an explanation. */
  noAggregateReason: string;
}

export interface ResolvedCitation {
  source: string;
  reference_id?: string;
  url?: string;
  [key: string]: unknown;
}

export interface ResolvedKinetic {
  found: true;
  quantity: KineticQuantity;
  value: number;
  /** The unit the SOURCE reported, never assumed from the parameter name. */
  unit: string;
  organism: string | null;
  /** brenda_exact | brenda_cross_species | literature_candidates */
  source: string;
  citation: ResolvedCitation | null;
  crossSpecies: boolean;
  /**
   * NCBI Taxonomy id of the organism the value was MEASURED in, and of the
   * one the caller ASKED about. Null when the lookup could not be made --
   * never a default, and never derived from the organism NAME, which is not
   * an identifier.
   *
   * Carried so the SBML export can write `bqbiol:hasTaxon` on the model and
   * on each parameter. When the two differ, any tool that reads SBML can
   * detect the cross-species substitution from the file alone, without
   * knowing anything about Caterva. Prose in a note cannot do that.
   */
  taxonId?: string | null;
  requestedTaxonId?: string | null;
  /**
   * Bakker's three reliability axes, graded by the Python resolver
   * (Tests/reliability.py) — the only implementation, since ADR 0027.
   *
   * This comment used to say the CLI and the API "report identical grades
   * for identical inputs. Both implementations are asserted against
   * Tests/reliability_cases.json." Every clause was true and the
   * conclusion was false: there were two implementations, they did agree
   * on the fixture, and the API server still could not produce a graded
   * `conditionProximity` because its call site had no reference to pass.
   * A parity test pins implementations, not call sites.
   *
   * Behaviour is pinned by Tests/reliability_cases.json (16 cases).
   *
   * Deliberately has no total: see ADR 0024, Decision 3.
   */
  reliability?: ReliabilityAxes;
  /**
   * Facts about the candidate POOL rather than the winning value (ADR 0039).
   *
   * Consumed here as well as by the API server, deliberately. ADR 0027 was
   * written because the two front ends disagreed about a third of Bakker's
   * score while a parity test asserted they agreed; shipping a finding to
   * one of them and not the other would rebuild that divergence from
   * scratch.
   */
  poolFindings?: {
    effectorContrasts?: Array<{ compound: string; reason: string }>;
    formMixtures?: Array<{ base: string; reason: string }>;
    organismDiscrepancies?: Array<{
      column_organism: string;
      commentary_organism: string;
      reason: string;
    }>;
    sourceMixtures?: Array<{ organism: string; reason: string }>;
  };
  /** Assay conditions the value was measured under (STRENDA, ADR 0010). */
  assayConditions?: {
    ph?: number | null;
    temperatureC?: number | null;
    buffer?: string | null;
    /** The buffer resolved to a PubChem compound (ADR 0028).
     *
     * This field is why the cast below is now typed rather than blanket.
     * `assayConditions` was copied through with
     * `as ResolvedKinetic['assayConditions']`, and because the target type
     * had no `bufferIdentity`, the resolution arrived at runtime and was
     * invisible to every typed consumer. Present, correct, unreachable. */
    bufferIdentity?: BufferIdentity | null;
    unreported?: string[];
  };
  /**
   * Which protein the winning row measured (ADR 0029).
   *
   * Carried on FOUND results, not only refusals. `unstated` is the majority
   * of BRENDA and it is not wild-type, so a reader who sees nothing would
   * assume the row was the enzyme as found — the assumption ADR 0029 exists
   * to stop being made silently.
   */
  variant?: VariantVerdict;
  /**
   * Cofactors and effectors reported for the winning row (ADR 0032).
   *
   * An empty array means the commentary named none. That is distinct from
   * the field being absent, which means nothing looked.
   */
  effectors?: Effector[];
  /**
   * Vmax = kcat * [E]0, present only for a kcat query with `enzymeConc`.
   *
   * Computed in PYTHON by the same
   * `caterva.core.validation.vmax_from_kcat()` the engine itself uses --
   * one implementation of the arithmetic and its Rule 2 bounds, not a
   * second copy in TypeScript. The [E]0/Km flag in particular carries a
   * threshold that must not be duplicated here and allowed to drift.
   */
  bridgedVmax?: number;
  vmaxValidation?: { ok: boolean; flagged: boolean; reason?: string };
  /**
   * The rows the evidence ranked EQUAL, when a tie-break picked among them.
   *
   * BARBARA BAKKER'S FINDING, DELIVERED TO HALF THE USERS.
   *
   * `evidence_rank.py` narrows candidates to the non-dominated frontier --
   * a row is dropped only when another beats it on EVERY axis, which needs
   * no weights and so could be built without inventing any. Among what
   * survives, nothing is beaten outright, and `min()` chooses. That choice
   * is arbitrary and `selection_tie.py` exists to say so out loud.
   *
   * The API path renders it: `selectionTieFlags` puts the alternatives and
   * their reference ids into `provenance.flags`. **The CLI never mentioned
   * it.** On the LDH turnover table that means a CLI user is handed 21.1 --
   * the lowest of six equally well-evidenced rows spanning to 6467, a
   * 306-fold range, every one wild-type with pH and temperature reported --
   * with nothing saying the evidence found 6467 equally credible.
   *
   * Found by `check_both_front_ends_read_it.py` (ADR 0110/0112), which
   * counted 24 keys read by one front end and not the other. This is the
   * first of them paid off.
   *
   * Absent means no tie was found, which is different from a tie with no
   * candidates -- hence `candidates` is what gets checked, never presence.
   */
  selectionTie?: SelectionTie | null;
  /**
   * Every surviving row with the grades that weight it (ADR 0137).
   *
   * `selectionTie` says the evidence could not choose. This says what each
   * alternative is WORTH, and it is carried on the ordinary `resolve` path
   * — not only inside `scientific ensemble` — because a finding built for
   * one front end reaches half the users. That has been recorded four times
   * here and is what `check_both_front_ends_read_it.py` exists to stop.
   */
  ensembleCandidates?: EnsembleCandidate[];
  /**
   * The winning row's commentary, verbatim, and what it says was measured:
   * the isoform, and for a Ki the inhibition mode and what the inhibitor
   * was measured against.
   *
   * Parsed in Python by `caterva.bind.core` (the reader `caterva bind` and
   * `caterva compose` use) and reported here as is, never re-derived. On
   * human LDH the gossypol Ki the resolver returns is LDH-B's, from a paper
   * that also gives LDH-A's and LDH-C's and states no mode for any.
   */
  commentary?: string | null;
  rowScope?: RowScope | null;
  logs: string[];
}

/** What the winning row says it measured (runner key `rowScope`). */
export interface RowScope {
  isoform: string | null;
  /** "competitive", "noncompetitive", ..., or "unstated". */
  inhibitionMode: string | null;
  versus: string | null;
}

/**
 * Plain sentences about what the row measured, for a quantity. A Km row is
 * never told it "states no inhibition mode": that is true of every Km and
 * says nothing. Empty when the scope has nothing to say.
 */
export function rowScopeLines(quantity: string, scope: RowScope | null | undefined): string[] {
  if (!scope) return [];
  const lines: string[] = [];
  if (scope.isoform) {
    lines.push(
      `The row measured isoform ${scope.isoform}. If the enzyme you mean is another isoform, this is a different protein's constant.`,
    );
  }
  if (quantity.toLowerCase() === 'ki' && scope.inhibitionMode) {
    if (scope.inhibitionMode === 'unstated') {
      lines.push(
        'The row states no inhibition mode, so which mechanism this Ki belongs to is unknown.',
      );
    } else {
      lines.push(
        `The row measured ${scope.inhibitionMode} inhibition` +
          (scope.versus ? ` versus ${scope.versus}` : '') +
          '. A Ki belongs to that mode and that assay.',
      );
    }
  }
  return lines;
}

function parseRowScope(raw: unknown): RowScope | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const text = (v: unknown) => (typeof v === 'string' && v.trim() ? v : null);
  const scope = {
    isoform: text(r['isoform']),
    inhibitionMode: text(r['inhibitionMode']),
    versus: text(r['versus']),
  };
  return scope.isoform || scope.inhibitionMode || scope.versus ? scope : null;
}

/** One row the evidence could not rank below another. */
export interface TiedCandidate {
  value: number;
  unit: string | null;
  organism: string | null;
  /** The BRENDA reference, so a named alternative is checkable. */
  reference_id: string | null;
  /** The row's own commentary, verbatim -- what a reader needs to judge. */
  conditions: string | null;
  /** Whether this is the row that was returned. */
  selected: boolean;
}

/** One published measurement with the three axes that weight its sampling. */
export interface EnsembleCandidate {
  value: number;
  unit: string | null;
  organism: string | null;
  reference_id: string | null;
  conditions: string | null;
  grades: {
    assay_completeness: string;
    condition_proximity: string;
    organism_match: string;
  };
}

export interface SelectionTie {
  candidates: TiedCandidate[];
  low: number | null;
  high: number | null;
  fold_range: number | null;
  reason: string;
}

/**
 * A paper the fallback search turned up, offered rather than used.
 *
 * Caterva does not extract numbers from full text. These are places to
 * look, which is why each carries a locator: a title alone is a claim, a
 * title with a PMID or DOI is checkable. PubMed's esummary never supplies a
 * DOI and CORE has no PMID, so neither field alone covers both sources.
 */
export interface KineticCandidatePaper {
  title: string;
  url: string | null;
  source: string;
  pmid: string | null;
  doi: string | null;
}

export interface UnresolvedKinetic {
  found: false;
  quantity: KineticQuantity;
  /** Why nothing was found -- the resolver's own search log. */
  logs: string[];
  /**
   * Papers the PubMed/CORE fallback found, which nobody was shown.
   *
   * THIS FIELD DID NOT EXIST, AND ITS ABSENCE MADE THE CLI LIE.
   *
   * When BRENDA holds nothing, the Python resolver searches PubMed and CORE
   * and returns `source: "literature_candidates"` with the list. The runner
   * emits it. This file parsed the response and built
   * `{ found: false, quantity, logs }` -- dropping the list at the boundary
   * without reading it -- and `commandResolve` then printed:
   *
   *     "BRENDA and PubMed were searched and returned nothing."
   *
   * PubMed did not return nothing. It returned papers. That sentence is
   * FALSE precisely when the fallback did its job, and it is the most
   * reassuring sentence the CLI prints.
   *
   * Fixed on the API path first (ADR 0106) and found here one pass later,
   * which is the standing lesson: a lesson applied only where it was first
   * learned is a lesson half-taken.
   *
   * Empty when the search genuinely found nothing -- which is a different
   * fact, and the one the old sentence was true about.
   */
  candidates: KineticCandidatePaper[];
}

export type ResolverResult = ResolvedKinetic | UnresolvedKinetic;

/**
 * Read the runner's `literatureCandidates`, keeping only usable entries.
 *
 * A candidate with no title is not showable and a candidate with no locator
 * is not checkable, so both are dropped rather than rendered as a blank
 * line or an unverifiable claim. Dropping is safe here in a way it is not
 * elsewhere: the count printed to the user comes from this filtered list,
 * so it can never promise more papers than it names.
 *
 * Anything unparseable yields an empty list rather than throwing. A
 * malformed candidate block is a worse reason to fail a lookup than to
 * fall back to the plain "nothing found" message -- but note that empty
 * then means "none usable", which the caller must not restate as "PubMed
 * returned nothing". That distinction is the whole point of this field.
 */
/**
 * Read the runner's `selectionTie`, or null when there is no tie to report.
 *
 * FEWER THAN TWO CANDIDATES IS NOT A TIE. `selection_tie.py` returns None
 * when fewer than two rows survived or when every surviving value is
 * identical -- in the first the evidence did choose, in the second nothing
 * turned on the choice. Both of those are already filtered on the Python
 * side, and this repeats the two-candidate check rather than trusting it,
 * because the cost of the two disagreeing is a CLI line announcing a tie
 * that did not happen.
 *
 * `reason` is required and NOT reconstructed here. It is the sentence
 * `selection_tie.py` argued over -- naming the axes, the spread and the
 * fact that the tie-break is unjustified -- and a client that paraphrases a
 * finding becomes a second place the wording can drift, which
 * `queryResolver.ts` explicitly refuses to be.
 */
/**
 * Read the runner's `ensembleCandidates`, keeping only usable rows.
 *
 * A row needs a finite value and all three grades. One missing either is not
 * a measurement this can weight, and passing it through would either crash
 * the sampler or render as a blank entry — both worse than dropping it, and
 * the count shown to a reader comes from the filtered list so it can never
 * promise more values than it names.
 */
function parseEnsembleCandidates(raw: unknown): EnsembleCandidate[] {
  if (!Array.isArray(raw)) return [];
  const out: EnsembleCandidate[] = [];
  for (const entry of raw) {
    if (typeof entry !== 'object' || entry === null) continue;
    const row = entry as Record<string, unknown>;
    const value = row['value'];
    if (typeof value !== 'number' || !Number.isFinite(value)) continue;
    const grades = row['grades'];
    if (typeof grades !== 'object' || grades === null) continue;
    const g = grades as Record<string, unknown>;
    const named = ['assay_completeness', 'condition_proximity', 'organism_match'];
    if (!named.every((k) => typeof g[k] === 'string')) continue;
    const str = (k: string): string | null =>
      typeof row[k] === 'string' && row[k] !== '' ? (row[k] as string) : null;
    out.push({
      value,
      unit: str('unit'),
      organism: str('organism'),
      reference_id: str('reference_id'),
      conditions: str('conditions'),
      grades: {
        assay_completeness: g['assay_completeness'] as string,
        condition_proximity: g['condition_proximity'] as string,
        organism_match: g['organism_match'] as string,
      },
    });
  }
  return out;
}

function parseSelectionTie(raw: unknown): SelectionTie | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const record = raw as Record<string, unknown>;
  const rawCandidates = record['candidates'];
  if (!Array.isArray(rawCandidates) || rawCandidates.length < 2) return null;

  const num = (value: unknown): number | null =>
    typeof value === 'number' && Number.isFinite(value) ? value : null;
  const str = (value: unknown): string | null =>
    typeof value === 'string' && value !== '' ? value : null;

  const candidates: TiedCandidate[] = [];
  for (const entry of rawCandidates) {
    if (typeof entry !== 'object' || entry === null) continue;
    const row = entry as Record<string, unknown>;
    const value = num(row['value']);
    // A candidate with no value cannot be compared or shown, and a tie
    // whose alternatives are blank is worse than no tie line at all.
    if (value === null) continue;
    candidates.push({
      value,
      unit: str(row['unit']),
      organism: str(row['organism']),
      reference_id: str(row['reference_id']),
      conditions: str(row['conditions']),
      selected: row['selected'] === true,
    });
  }
  if (candidates.length < 2) return null;

  const reason = str(record['reason']);
  if (reason === null) return null;

  return {
    candidates,
    low: num(record['low']),
    high: num(record['high']),
    fold_range: num(record['fold_range']),
    reason,
  };
}

function parseCandidatePapers(raw: unknown): KineticCandidatePaper[] {
  if (!Array.isArray(raw)) return [];
  const out: KineticCandidatePaper[] = [];
  for (const entry of raw) {
    if (typeof entry !== 'object' || entry === null) continue;
    const record = entry as Record<string, unknown>;
    const title = typeof record['title'] === 'string' ? record['title'].trim() : '';
    if (title.length === 0) continue;
    const str = (key: string): string | null =>
      typeof record[key] === 'string' && record[key] !== '' ? (record[key] as string) : null;
    const pmid = str('pmid');
    const doi = str('doi');
    const url = str('url');
    if (pmid === null && doi === null && url === null) continue;
    out.push({ title, url, source: str('source') ?? 'unknown', pmid, doi });
  }
  return out;
}

const DEFAULT_SCRIPT_PATH = path.join(
  REPO_ROOT,
  'Science-Agent-Pipeline',
  'artifacts',
  'api-server',
  'src',
  'lib',
  'science_agent_runner.py'
);

/**
 * Which runner script to spawn.
 *
 * `CATERVA_LITERATURE_RUNNER` overrides it so the subprocess path -- spawn,
 * stdin, exit code, stdout parsing -- can be exercised against a stub that
 * emits canned JSON, with no network. That path is where the bugs actually
 * are: the first version of this module threw away the runner's structured
 * `{"ok": false, "error": "403 Forbidden"}` because the process also
 * exited 1, replacing a precise cause with "exited with code 1". A mock of
 * the whole module would not have caught that; a real subprocess does.
 */
function scriptPath(): string {
  return process.env['CATERVA_LITERATURE_RUNNER'] || DEFAULT_SCRIPT_PATH;
}

/** BRENDA and PubMed are network calls; this is generous but finite. */
const RESOLVER_TIMEOUT_MS = 120_000;

/** Raised when the resolver could not be run at all. Deliberately distinct
 *  from `found: false`: "the registry says no" and "we never asked" are
 *  different facts, and collapsing them is how an unchecked value comes to
 *  look checked. */
export class ResolverUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ResolverUnavailableError';
  }
}

/**
 * The runner's JSON payload -> a `ResolvedKinetic`.
 *
 * EXTRACTED SO IT CAN BE TESTED.
 *
 * This mapping used to live inline inside `resolveKinetic`, which spawns
 * Python. That made it unreachable from any unit test, and it is exactly
 * where the defect was: the runner emitted `variant`, `effectors` and
 * `assayConditions.bufferIdentity` for months, and this function dropped
 * every one of them because `ResolvedKinetic` had no field to receive them.
 *
 * The rendering tests in `src/cli/__tests__/resolveOutput.test.ts` could not
 * catch it either — they mock `resolveKinetic`, so they assert what the CLI
 * does with an object rather than whether the object is ever populated.
 * Deleting the plumbing left all fourteen of them passing.
 *
 * A mapping only reachable through a subprocess is a mapping nothing tests.
 */
export function mapFoundResult(
  parsed: Record<string, unknown>,
  quantity: KineticQuantity,
  value: number,
  unit: string,
  logs: string[],
): ResolvedKinetic {
  return {
    found: true,
    quantity,
    value,
    unit,
    organism: (parsed['organism'] as string) ?? null,
    source: String(parsed['source'] ?? 'unknown'),
    citation: (parsed['citation'] as ResolvedCitation) ?? null,
    taxonId: (parsed['taxonId'] as string | null) ?? null,
    requestedTaxonId: (parsed['requestedTaxonId'] as string | null) ?? null,
    reliability: (parsed['reliability'] as ReliabilityAxes) ?? undefined,
    assayConditions:
      (parsed['assayConditions'] as ResolvedKinetic['assayConditions']) ?? undefined,
    // The runner has always emitted these. Nothing here read them.
    //
    // Same defect as ADR 0027, one layer out: the value is computed,
    // serialised, and dropped by a consumer whose type has no field for it.
    // There is no error, no warning, and no way to notice from either side
    // — the producer sees a successful write and the consumer sees a
    // complete object.
    variant: (parsed['variant'] as VariantVerdict | undefined) ?? undefined,
    effectors: (parsed['effectors'] as Effector[] | undefined) ?? undefined,
    // Mapped explicitly, like every field above it. A spread would carry
    // whatever the runner happens to emit, which is how a field arrives
    // untyped and unrendered -- the shape of the defect ADR 0039 fixes.
    poolFindings:
      (parsed['poolFindings'] as ResolvedKinetic['poolFindings']) ?? undefined,
    // Read through `parseSelectionTie` rather than cast, because a tie with
    // fewer than two candidates must not read as a tie. `SelectionTie()`
    // with an empty list is also what an unpopulated field looks like, and
    // `selection_tie.py` makes `is_tied` a POSITIVE test for exactly that
    // reason -- a check on presence would inherit the ambiguity it was
    // written to remove.
    selectionTie: parseSelectionTie(parsed['selectionTie']),
    // Read through rather than cast: a row with no usable value or no grades
    // is not a candidate, and letting one through would put a blank line in
    // front of a student where a measurement should be.
    ensembleCandidates: parseEnsembleCandidates(parsed['ensembleCandidates']),
    // Read through, like the tie: an all-null scope is no scope.
    commentary: typeof parsed['commentary'] === 'string' ? (parsed['commentary'] as string) : null,
    rowScope: parseRowScope(parsed['rowScope']),
    // BRENDA cross-species means the value came from a DIFFERENT organism
    // than the one asked about. Still real and citable, but the caller must
    // be able to see it rather than have it presented as a same-organism
    // measurement.
    crossSpecies: String(parsed['source'] ?? '').includes('cross_species'),
    // Only present for kcat + enzymeConc. `vmaxValidation.ok === false`
    // means the bridge REFUSED (non-positive or non-finite [E]0), and the
    // runner deliberately omits `vmax` in that case -- so an unusable Vmax
    // cannot be read as a usable one.
    ...(typeof parsed['vmax'] === 'number'
      ? { bridgedVmax: parsed['vmax'] as number }
      : {}),
    ...(parsed['vmaxValidation']
      ? {
          vmaxValidation: parsed['vmaxValidation'] as {
            ok: boolean;
            flagged: boolean;
            reason?: string;
          }
        }
      : {}),
    logs
  };
}

/**
 * Resolve one kinetic constant from the real literature layer.
 *
 * Returns `found: false` when BRENDA and PubMed genuinely have nothing --
 * that is an answer. Throws ResolverUnavailableError when the resolver
 * could not run, because a failure to look is not evidence of absence.
 */
export async function resolveKinetic(
  query: ResolverQuery,
  options: { signal?: AbortSignal } = {}
): Promise<ResolverResult> {
  if (!query.ecNumber && !query.enzymeName) {
    throw new ResolverUnavailableError(
      'Neither ecNumber nor enzymeName was supplied, so there is nothing to ' +
      'search for. The resolver will not guess an enzyme identity.'
    );
  }

  const runnerScript = scriptPath();
  if (!fs.existsSync(runnerScript)) {
    throw new ResolverUnavailableError(
      `Literature resolver not found at ${runnerScript}. This module resolves ` +
      'against BRENDA/PubMed and will not fall back to a local table.'
    );
  }

  const quantity: KineticQuantity = query.quantity ?? 'km';
  const pythonExecutable = resolvePythonExecutable(REPO_ROOT);

  const raw = await new Promise<string>((resolve, reject) => {
    if (options.signal?.aborted) {
      reject(new Error('Cancelled'));
      return;
    }

    const proc = spawn(pythonExecutable, [runnerScript], {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        // Tests/ is on the path as well as the repo root: the runner
        // imports `fallback_logic` and `enzyme_lookup` as top-level
        // modules, matching how scienceAgent.ts invokes it.
        PYTHONPATH: [
          process.env['PYTHONPATH'],
          REPO_ROOT,
          path.join(REPO_ROOT, 'Tests')
        ]
          .filter(Boolean)
          .join(path.delimiter)
      }
    });

    let settled = false;
    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (options.signal) options.signal.removeEventListener('abort', onAbort);
      fn();
    };

    const onAbort = () => {
      proc.kill('SIGTERM');
      finish(() => reject(new Error('Cancelled')));
    };
    if (options.signal) {
      options.signal.addEventListener('abort', onAbort, { once: true });
    }

    const timer = setTimeout(() => {
      proc.kill('SIGTERM');
      finish(() =>
        reject(
          new ResolverUnavailableError(
            `Literature resolver exceeded ${RESOLVER_TIMEOUT_MS}ms`
          )
        )
      );
    }, RESOLVER_TIMEOUT_MS);

    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (c: Buffer) => {
      stdout += c.toString('utf-8');
    });
    proc.stderr.on('data', (c: Buffer) => {
      stderr += c.toString('utf-8');
    });

    proc.on('error', (err: Error) => {
      finish(() =>
        reject(
          new ResolverUnavailableError(
            `Failed to spawn literature resolver: ${err.message}`
          )
        )
      );
    });

    proc.on('close', (code: number | null) => {
      const trimmed = stdout.trim();

      // A non-zero exit is not the end of the story. The runner reports
      // failures as structured JSON -- `{"ok": false, "error": "403
      // Forbidden"}` -- AND exits 1, so discarding stdout here replaced a
      // precise cause with "exited with code 1". That is the difference
      // between "BRENDA refused the request" and no information at all,
      // and it is exactly the diagnosis a caller needs.
      if (trimmed) {
        finish(() => resolve(trimmed));
        return;
      }

      finish(() =>
        reject(
          new ResolverUnavailableError(
            stderr.trim() || `Literature resolver exited with code ${code}`
          )
        )
      );
    });

    proc.stdin.write(
      JSON.stringify({
        enzymeName: query.enzymeName,
        substrate: query.substrate,
        organism: query.organism,
        ecNumber: query.ecNumber,
        quantity,
        enzymeConc: query.enzymeConc,
        allowCrossSpecies: query.allowCrossSpecies === true,
        physiologicalReference: query.physiologicalReference
      })
    );
    proc.stdin.end();
  });

  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(raw) as Record<string, unknown>;
  } catch (err) {
    throw new ResolverUnavailableError(
      'Literature resolver returned invalid JSON: ' +
      (err instanceof Error ? err.message : String(err))
    );
  }

  if (parsed['ok'] !== true) {
    throw new ResolverUnavailableError(
      String(parsed['error'] ?? 'Literature resolver reported an error')
    );
  }

  const logs = Array.isArray(parsed['logs'])
    ? (parsed['logs'] as string[])
    : [];

  if (parsed['found'] !== true) {
    const candidates = parseCandidatePapers(parsed['literatureCandidates']);
    logger.info(
      { query, quantity, candidateCount: candidates.length },
      'Literature resolver found no value; reporting absence rather than a default'
    );
    return { found: false, quantity, logs, candidates };
  }

  // The value is emitted under the key matching the quantity ("km", "ki",
  // "kcat") so a cross-species Ki cannot be read as a Km.
  const value = parsed[quantity];
  const unit = parsed['unit'];

  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ResolverUnavailableError(
      `Resolver reported found=true but no usable '${quantity}' value.`
    );
  }
  if (typeof unit !== 'string' || unit.length === 0) {
    // A number without its unit is not a measurement. Km in mM and Km in
    // uM differ by 1000x, and this tree has already been bitten twice by
    // assumed units.
    throw new ResolverUnavailableError(
      `Resolver returned a '${quantity}' value with no unit. A kinetic ` +
      'constant without its unit cannot be used.'
    );
  }

  return mapFoundResult(parsed, quantity, value, unit, logs);
}
