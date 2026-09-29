import { spawn } from "node:child_process";
import { access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { logger } from "./logger";
import { findRepositoryRoot } from "./repoRoot";
import { resolvePythonExecutable } from "./python";
import type {
  PhysiologicalReference,
  ReliabilityScore,
} from "./reliabilityScore";
import type { BufferIdentity, Effector } from "./provenance";

export interface Citation {
  source: string;
  referenceId?: string;
  url?: string;
  title?: string;
  organism?: string;
  notes?: string;
}

/** One published measurement, with the grades that decide its sampling weight. */
export interface EnsembleCandidate {
  value: number;
  unit: string | null;
  organism: string | null;
  reference_id: string | null;
  conditions: string | null;
  /** The three axes, by name. Not combined into a total — see reliability.py. */
  grades: {
    assay_completeness: string;
    condition_proximity: string;
    organism_match: string;
  };
}

export interface LiteratureCandidate {
  title: string;
  url: string;
  /** "pubmed" or "core" (open-access full text, added to supplement
   * PubMed's metadata-only search -- see ADR 0017 for the gap this
   * closes). */
  source: "pubmed" | "core";
  /** Set for source "pubmed"; null for "core" (CORE has no PMID). */
  pmid: string | null;
  /** Set when known for either source; PubMed's esummary response never
   * supplies one, so this is null there. */
  doi: string | null;
}

export interface ScienceAgentResult {
  found: boolean;
  km?: number;
  ki?: number;
  /** Turnover number (s^-1), quantity="kcat". A resolved kcat is NOT a
   * simulation-ready parameter on its own -- Vmax = kcat * [E]0 needs a
   * caller-supplied enzyme concentration Caterva never defaults or infers
   * (ADR 0012 / 0013). See ADR 0019 for how a resolved kcat combines with
   * a user-supplied enzyme_conc override into a Vmax provenance entry. */
  kcat?: number;
  /** Only present when quantity="kcat" and enzymeConc was supplied: the
   * bridged Vmax = kcat * enzymeConc, computed in Python by the same
   * caterva.core.validation.vmax_from_kcat() the engine itself uses --
   * one implementation of the arithmetic and its Rule 2 bounds, not a
   * second copy in TypeScript. See ADR 0019. */
  vmax?: number;
  vmaxValidation?: {
    ok: boolean;
    flagged: boolean;
    reason?: string;
  };
  /** ADR 0017 / ADR 0020: a resolved disease's canonical name, basic
   * reproduction number, and infectious period (from
   * Tests/epidemiology_resolver.py's hand-verified registry), plus the
   * bridged (beta, gamma) the SIR engine takes directly, computed by the
   * same caterva.core.validation.beta_gamma_from_r0() the engine uses.
   * Only present when parameterType="disease_parameters" was requested. */
  disease?: string;
  r0?: number;
  infectiousPeriodDays?: number;
  /**
   * ADR 0169: true when R0 and the serial interval come from two
   * different systematic reviews rather than one paper.
   *
   * A composite MUST reach provenance as citationStatus "flagged", never
   * "verified" — the same tier a cross-species BRENDA Km gets. Inheriting
   * COVID-19's verified status would erase the only signal telling a
   * reader that two methodologies were combined.
   */
  crossStudyComposite?: boolean;
  /** What exactly was combined, in the entry's own words. */
  compositeNote?: string;
  /**
   * The serial-interval half's citation, when it differs from the R0
   * half's. Both must reach the user: surfacing only the first would
   * present a two-paper number as if one paper supported it — the same
   * shape as the popgen defect where a genome-assembly DOI stood in for a
   * mutation rate.
   */
  secondaryCitation?: Citation;
  beta?: number;
  gamma?: number;
  betaGammaValidation?: {
    ok: boolean;
    flagged: boolean;
    reason?: string;
  };
  unit?: string;
  organism?: string;
  source?: string;
  /** True when the value came from a different organism than the query
   * asked for (BRENDA cross-species fallback). Stage 5 Part 3: first-class
   * across the boundary, previously dropped by the runner. */
  crossSpecies?: boolean;
  /** Organisms that DO hold a value when the requested organism does not,
   * and cross-species use was not opted into. Populated only when
   * `source === "cross_species_withheld"` (ADR 0024).
   *
   * Present so a refusal can name what it refused. `found: false` with an
   * empty reason is indistinguishable from "the literature has nothing",
   * and those are different facts: one is a gap in science, the other is a
   * policy this code applied. Conflating them is the same category error
   * that ADR 0012/0013 exist to prevent, one level up. */
  crossSpeciesOrganismsAvailable?: string[];
  /** Substrate labels this EC number DOES report, when the requested one
   *  matched nothing. BRENDA's label for lactate is `(S)-lactate`, so
   *  "lactate" matches by substring and "L-lactate" returns nothing —
   *  and the student is told the literature is empty when it is not. */
  substratesAvailable?: string[];
  /** EC numbers UniProt indexed under the enzyme NAME, when it matched more
   *  than one. An EC number is the identity of the protein every citation
   *  refers to, so the runner refuses to pick and names them (ADR 0127). */
  ecCandidates?: string[];
  /** Variant descriptors ("Y124C", "isozyme H4") for rows that WERE found
   * and were withheld because they measure a sequence variant rather than
   * the enzyme (ADR 0029). Populated only when
   * `source === "variant_withheld"`. */
  variantCandidatesAvailable?: string[];
  /** Which protein the winning row measured. Present on FOUND results too:
   * `unstated` is the majority case in BRENDA and it is NOT wild-type, so a
   * reader must be able to tell "the row did not say" from "the row said
   * wild-type". */
  variant?: VariantVerdict;
  /**
   * How the enzyme was PREPARED for the winning row (ADR 0092):
   * `native` | `immobilised` | `tagged` | `modified` | `unstated` | `absent`.
   *
   * TOP-LEVEL beside `variant`, because that is where the runner emits it —
   * the same check that saved `effectors` from being permanently
   * `undefined` inside `assayConditions`.
   *
   * `unstated` is the majority case and is NOT `native`. A reader must be
   * able to tell "the row did not say" from "the row said native enzyme".
   */
  /**
   * The chosen BRENDA row's commentary, verbatim ("LDH-B, pH not specified
   * ...", "competitive versus NADH, pH 7.5, 37 C ..."). Emitted by the runner
   * beside `variant`.
   */
  commentary?: string | null;
  /**
   * What `commentary` says about the measurement's scope, decided in Python
   * by caterva.bind.core (the one implementation): which isoform the row
   * measured, and for an inhibition constant which mode and against what.
   * `inhibitionMode` is "unstated" when the row gives none.
   */
  rowScope?: {
    isoform: string | null;
    inhibitionMode: string;
    versus: string | null;
  } | null;
  preparation?: {
    status: string;
    evidence?: string | null;
    /**
     * The quantity the curator explicitly says the preparation did NOT
     * change ("KM", "KCAT"), or null.
     *
     * Quantity-specific by nature: the same PEGylated AChE row carries the
     * clause for Km in one BRENDA table and Kcat in another, so it is a
     * statement about a measurement rather than about the protein.
     */
    stated_not_to_affect?: string | null;
    /**
     * Whether this preparation should be flagged for the quantity that was
     * resolved — decided by `enzyme_preparation.differs_for()` in Python,
     * which owns the rule.
     *
     * Read this rather than re-deriving from `status` and
     * `stated_not_to_affect`. Those are the INPUTS; recomputing the
     * judgement here would be a second implementation of one rule, which
     * is ADR 0027's defect exactly.
     */
    warrantsWarning?: boolean;
  };
  /**
   * Cofactors and effectors named in the winning row's commentary, resolved
   * to PubChem compounds by the runner (ADR 0032).
   *
   * TOP-LEVEL, beside `variant`, because that is where the runner emits it.
   * The first draft of this field put it inside `assayConditions`, where it
   * reads more naturally and would have been permanently `undefined` — the
   * exact shape of ADR 0027's defect, caught this time by checking the
   * emitter instead of assuming it.
   *
   * An empty array means the commentary named none. That is different from
   * a clause that WAS found and could not be resolved, which arrives
   * carrying an identity with status "unresolvable".
   */
  effectors?: Effector[];
  /**
   * Set when the evidence ranked several rows equal and a tie-break chose
   * among them (ADR 0048).
   *
   * On the LDH turnover table six non-dominated rows span 21.1 to 6467 — a
   * 306-fold range, every one wild-type with pH and temperature reported.
   * The returned value is the lowest, and without this field nothing says
   * the evidence found 6467 equally credible.
   *
   * Absent means no tie was found. That is different from a tie with no
   * candidates, which is why `candidates` is checked rather than presence.
   */
  selectionTie?: SelectionTie | null;
  /**
   * Every row on the non-dominated frontier, with the reliability grades
   * that weight it — Bakker's three axes, scored per candidate rather than
   * only for the winner.
   *
   * `selectionTie` says the evidence could not choose and names the
   * alternatives. This says what each one is WORTH, which is the input the
   * ensemble samples by and the reason the sampling could not be built until
   * the resolver started carrying it (ADR 0137).
   *
   * Empty means nothing was resolved — a resolution failure to report, never
   * a band with no members.
   */
  ensembleCandidates?: EnsembleCandidate[];
  /**
   * Which named form the returned value IS, when the candidate pool mixed
   * forms of one enzyme (ADR 0052).
   *
   * `poolFindings.formMixtures` warns that "returning the lowest would pick
   * a form rather than answer the question" — conditionally. This says
   * whether it did.
   *
   * Null in every fixture today: the pipeline selects rows carrying no
   * designator. That is luck rather than design, and a test pins it so a
   * BRENDA update that changes it fails loudly.
   */
  selectedForm?: SelectedForm | null;
  /**
   * Bakker's three axes, as computed by the PYTHON resolver
   * (Tests/reliability.py) and emitted by science_agent_runner.py.
   *
   * This field is the fix for a duplicate source of truth. The runner has
   * always computed and emitted this score; `ScienceAgentResult` had no
   * field to receive it, so the API server discarded it and recomputed the
   * same three axes in TypeScript — and the recomputation was strictly
   * worse, because its call site never passed a PhysiologicalReference and
   * `conditionProximity` was therefore permanently `not_assessed`.
   *
   * The CLI (src/literature/literatureResolver.ts) already consumed the
   * Python score. So the two front ends disagreed on a third of the score
   * while a parity test asserted they agreed — the test pinned the two
   * IMPLEMENTATIONS against a shared fixture, which cannot detect a call
   * site that passes different arguments.
   */
  reliability?: ReliabilityScore;
  /** Per-candidate relatedness verdicts from taxonomy.py (ADR 0024).
   * Includes rejected candidates, deliberately — see the runner. */
  relatedness?: RelatednessVerdict[];
  /**
   * Facts about the candidate POOL, not about the value that won it
   * (ADR 0039).
   *
   * Four detectors computed these and the runner dropped them: the
   * resolver attached them to its result, nothing emitted them, and only a
   * prose line reached the diagnostic log. Every test on every detector
   * passed throughout, because each tested the computation and none tested
   * the boundary. ADR 0027's defect, four times over.
   */
  poolFindings?: PoolFindings;
  citation?: Citation;
  /** Assay conditions the Km was measured under, parsed from the BRENDA
   * commentary by the Python client. STRENDA requires temperature and pH
   * for all reported kinetic data; Km moves with both, so a Km without
   * them cannot be reproduced or compared against another lab's figure.
   *
   * Individual fields are optional because BRENDA frequently does not
   * report them. Absence is passed through as absence and degrades the
   * citation tier downstream -- it is never filled with a default. See
   * ADR 0010. */
  assayConditions?: {
    ph?: number | null;
    temperatureC?: number | null;
    buffer?: string | null;
    /** The buffer resolved to a PubChem compound (ADR 0028). Absent when
     * no buffer was reported; `status: "unresolvable"` when one was
     * reported and could not be resolved -- those are different facts. */
    bufferIdentity?: BufferIdentity | null;
    /** Fields BRENDA explicitly states the publication did not report. */
    unreported?: string[];
  };
  literatureCandidates: LiteratureCandidate[];
  logs: string[];
}

/** Mirrors form_mixture.SelectedForm. */
export interface SelectedForm {
  base: string;
  designator: string;
  value: number;
  sibling_designators?: string[];
  reason: string;
}

/** Mirrors selection_tie.SelectionTie. snake_case inside the candidates
 * because they cross the wire as Python emits them. */
export interface SelectionTie {
  candidates: Array<{
    value: number;
    unit?: string | null;
    organism?: string | null;
    reference_id?: string | null;
    conditions?: string | null;
    selected?: boolean;
  }>;
  low?: number | null;
  high?: number | null;
  fold_range?: number | null;
  reason: string;
}

/** Mirrors protein_variant.VariantVerdict. snake_case for the same reason
 * RelatednessVerdict is: it crosses the wire as Python emits it. */
export interface VariantVerdict {
  /** "wild_type" | "variant" | "unstated" | "absent" */
  status: string;
  /** "mutant" | "isozyme" when status is "variant". */
  kind?: string | null;
  /** The exact substring that decided it, so a reader can check the
   * classifier rather than trust it. */
  evidence?: string | null;
  recombinant?: boolean;
  reason: string;
}

/** Mirrors taxonomy.Relatedness on the Python side. Field names are
 * snake_case because they cross the wire as the Python model emits them;
 * renaming here would create a second place the two halves could drift. */
/** Mirrors the runner's `poolFindings`. snake_case inside each item, for
 * the same reason RelatednessVerdict is: they cross the wire as the Python
 * models emit them, and renaming here would create a second place the two
 * halves could drift. */
export interface PoolFindings {
  /** A compound the pool reports both with and without (ADR 0033). */
  effectorContrasts?: Array<{
    compound: string;
    present_values: number[];
    absent_values: number[];
    reason: string;
  }>;
  /** One base named with several form designators (ADR 0035). */
  formMixtures?: Array<{
    base: string;
    values_by_form: Record<string, number[]>;
    reason: string;
  }>;
  /** A row whose commentary names a different organism than its column
   * (ADR 0037). */
  organismDiscrepancies?: Array<{
    value: number;
    column_organism: string;
    commentary_organism: string;
    reason: string;
  }>;
  /** One organism measured from several biological sources (ADR 0037). */
  sourceMixtures?: Array<{
    organism: string;
    values_by_source: Record<string, number[]>;
    reason: string;
  }>;
  /**
   * Set when source tokens were found and NONE could be classified, so the
   * pool was not checked for mixed sources at all.
   *
   * Without it, `sourceMixtures: []` means both "the pool was clean" and
   * "the classifier could not reach NCBI" — the conflation ADR 0024 and
   * ADR 0029 both exist to prevent, shipped inside a module written to
   * avoid it.
   */
  sourceCheckUnavailable?: { tokens: string[]; reason: string } | null;
}

export interface RelatednessVerdict {
  status: string;
  shared_rank?: string | null;
  shared_name?: string | null;
  query_organism?: string | null;
  candidate_organism?: string | null;
  reason?: string;
}

export interface EntityExtraction {
  enzymeName?: string;
  substrate?: string;
  organism: string;
  ecNumber?: string;
  /** For population genetics: parameter type to resolve (e.g., 'mutation_rate') */
  parameterType?: string;
  /** Which kinetic constant to resolve: "km" (BRENDA KM Values table) or
   * "ki" (BRENDA Ki Values table). Each call resolves exactly one quantity
   * and the runner emits the value under the matching key, so a cross-
   * species Ki never borrows a verified Km's provenance. */
  quantity?: "km" | "ki" | "kcat";
  /** Caller-supplied enzyme concentration (mM), only meaningful with
   * quantity="kcat". Never resolved or defaulted -- ADR 0013 -- so this is
   * always a value that traced back to a user override in queryResolver.ts,
   * never something this layer invents. */
  enzymeConc?: number;
  /** Opt in to values measured in a different organism (ADR 0024).
   *
   * Absent means false. The permissive reading of a missing flag is
   * precisely how the automatic cross-species fallback would come back,
   * silently, in a diff that looked like a refactor. */
  allowCrossSpecies?: boolean;
  /** Opt in to a value measured on a sequence variant (ADR 0029). Absent
   * means false, for the same reason allowCrossSpecies reads that way. */
  allowVariants?: boolean;
  /**
   * The conditions the model is meant to represent (ADR 0024, Decision 3).
   *
   * Forwarded verbatim to the runner, which grades `conditionProximity`
   * against it. Never defaulted here or anywhere else: "physiological" has
   * no organism-independent value, and baking in 7.4/37 would silently
   * assume a mammal and report a confident `far` for a thermophile assay
   * that was in fact ideal.
   *
   * Its absence is why the API server's proximity axis could only ever say
   * `not_assessed` — not because the grader was broken, but because nobody
   * had ever been able to state what the model represents.
   */
  physiologicalReference?: PhysiologicalReference;
}

interface PythonError {
  ok: false;
  error: string;
}

/**
 * Stage 5 Part 4: the runner-boundary contract, testable without spawning
 * Python. Parses the runner's stdout JSON into a ScienceAgentResult.
 * Throws on empty output, unexpected shape, or a Python-side error report.
 */
export function parseAgentOutput(stdout: string): ScienceAgentResult {
  const trimmed = stdout.trim();
  if (!trimmed) {
    throw new Error("Science agent runner returned no output");
  }
  const parsed = JSON.parse(trimmed) as ScienceAgentResult | PythonError;
  if (!("ok" in parsed)) {
    throw new Error("Science agent runner returned unexpected JSON");
  }
  if (!parsed.ok) {
    throw new Error((parsed as PythonError).error);
  }
  return parsed as unknown as ScienceAgentResult;
}

const _dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = findRepositoryRoot(_dirname);

const SCRIPT_PATH = path.join(
  REPO_ROOT,
  "Science-Agent-Pipeline",
  "artifacts",
  "api-server",
  "src",
  "lib",
  "science_agent_runner.py",
);

let scriptChecked = false;

async function ensureRunnerScript(): Promise<void> {
  if (scriptChecked) return;
  try {
    await access(SCRIPT_PATH);
    scriptChecked = true;
  } catch {
    throw new Error(
      `Science agent runner script not found at ${SCRIPT_PATH}. ` +
        "Did the build copy it?",
    );
  }
}

/**
 * The `error` of the runner's last stdout line when it is a JSON failure
 * record ({"ok": false, "error": "..."}), else null.
 */
export function runnerError(stdout: string): string | null {
  const last = stdout.trim().split("\n").pop();
  if (!last) return null;
  try {
    const parsed = JSON.parse(last) as { ok?: unknown; error?: unknown };
    return parsed.ok === false && typeof parsed.error === "string" && parsed.error
      ? parsed.error
      : null;
  } catch {
    return null;
  }
}

/**
 * Spawn the Python science-agent runner with an arbitrary JSON payload and
 * parse its stdout. Shared by resolveKineticValue() (enzyme kinetics) and
 * resolveEpidemiologyParameters() (ADR 0017 / ADR 0020) so there is exactly
 * one place that owns the spawn/PYTHONPATH/stdout-parsing contract, rather
 * than two copies that could drift.
 *
 * This function uses BRENDA/KEGG/PubMed lookups in Tests/fallback_logic.py.
 * If an EC number isn't known, the Python side resolves one live via UniProt's
 * name search (Tests/enzyme_lookup.py::fetch_ec_number_by_name) before
 * attempting BRENDA -- this lets enzyme names outside the hardcoded pattern
 * list in enzymes.ts still reach real literature lookups.
 */
async function spawnScienceAgent(
  payload: Record<string, unknown>,
): Promise<ScienceAgentResult> {
  await ensureRunnerScript();
  const pythonExecutable = resolvePythonExecutable(REPO_ROOT);

  return new Promise((resolve, reject) => {
    const proc = spawn(pythonExecutable, [SCRIPT_PATH], {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        PYTHONPATH: [
          process.env.PYTHONPATH,
          REPO_ROOT,
          path.join(REPO_ROOT, "Tests"),
        ]
          .filter(Boolean)
          .join(path.delimiter),
      },
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf-8");
    });

    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf-8");
    });

    proc.on("error", (err) => {
      reject(new Error(`Failed to spawn science agent runner: ${err.message}`));
    });

    proc.on("close", (code) => {
      const trimmed = stdout.trim();
      const hadNonZeroExit = code !== 0;
      const hadNoOutput = !trimmed;

      if (hadNonZeroExit || hadNoOutput) {
        // The runner reports a caught failure as {"ok": false, "error": ...}
        // on STDOUT and exits 1, so stderr is empty exactly when the reason
        // is known. Reading only stderr turned "BRENDA returned 500" into
        // "exited with code 1" (found 2026-09-28, BRENDA down for 2.7.1.1).
        const message =
          stderr ||
          runnerError(trimmed) ||
          `Science agent runner exited with code ${code}`;
        reject(new Error(message));
        return;
      }

      try {
        const result = parseAgentOutput(trimmed);
        resolve(result);
      } catch (err) {
        reject(err instanceof Error ? err : new Error(String(err)));
      }
    });

    proc.stdin.write(JSON.stringify(payload));
    proc.stdin.end();
  });
}

/**
 * Build a not-found result with an explanatory log message.
 */
function notFoundResult(reason: string): ScienceAgentResult {
  return {
    found: false,
    literatureCandidates: [],
    logs: [reason],
  };
}

/**
 * Resolve a disease's (R0, infectious period) golden tuple and bridge it to
 * the SIR engine's own (beta, gamma) — see Tests/epidemiology_resolver.py
 * and caterva.core.validation.beta_gamma_from_r0. Returns found=false for
 * any disease outside the hand-verified registry; never fabricates a value.
 */
export async function resolveEpidemiologyParameters(
  disease: string,
): Promise<ScienceAgentResult> {
  if (!disease) {
    return notFoundResult("No disease name provided; skipping real parameter lookup.");
  }
  return spawnScienceAgent({ parameterType: "disease_parameters", disease });
}

export async function resolveKineticValue(
  entities: EntityExtraction,
): Promise<ScienceAgentResult> {
  if (!entities.ecNumber && !entities.enzymeName) {
    return notFoundResult(
      "No enzyme name or EC number provided; skipping real parameter lookup.",
    );
  }

  return spawnScienceAgent({
    enzymeName: entities.enzymeName ?? "",
    substrate: entities.substrate ?? "",
    organism: entities.organism,
    ecNumber: entities.ecNumber,
    parameterType: entities.parameterType ?? "",
    quantity: entities.quantity ?? "km",
    enzymeConc: entities.enzymeConc,
    allowCrossSpecies: entities.allowCrossSpecies === true,
    allowVariants: entities.allowVariants === true,
    // Omitted rather than sent as undefined: the runner's
    // _parse_physiological refuses a partial reference, and an explicit
    // `undefined` in the JSON payload is indistinguishable from a partial
    // one at the far end.
    ...(entities.physiologicalReference
      ? { physiologicalReference: entities.physiologicalReference }
      : {}),
  });
}

