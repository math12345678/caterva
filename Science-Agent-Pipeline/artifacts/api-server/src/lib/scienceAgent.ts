import { spawn } from "node:child_process";
import { access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { logger } from "./logger";
import { findRepositoryRoot } from "./repoRoot";
import { resolvePythonExecutable } from "./python";

export interface Citation {
  source: string;
  referenceId?: string;
  url?: string;
  title?: string;
  organism?: string;
  notes?: string;
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
   * caller-supplied enzyme concentration Terrium never defaults or infers
   * (ADR 0012 / 0013). See ADR 0019 for how a resolved kcat combines with
   * a user-supplied enzyme_conc override into a Vmax provenance entry. */
  kcat?: number;
  /** Only present when quantity="kcat" and enzymeConc was supplied: the
   * bridged Vmax = kcat * enzymeConc, computed in Python by the same
   * Tellurium.core.validation.vmax_from_kcat() the engine itself uses --
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
   * same Tellurium.core.validation.beta_gamma_from_r0() the engine uses.
   * Only present when parameterType="disease_parameters" was requested. */
  disease?: string;
  r0?: number;
  infectiousPeriodDays?: number;
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
    /** Fields BRENDA explicitly states the publication did not report. */
    unreported?: string[];
  };
  literatureCandidates: LiteratureCandidate[];
  logs: string[];
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
        const message = stderr || `Science agent runner exited with code ${code}`;
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
 * and Tellurium.core.validation.beta_gamma_from_r0. Returns found=false for
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
  });
}

