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
  pmid: string;
  title: string;
  url: string;
}

export interface ScienceAgentResult {
  found: boolean;
  km?: number;
  ki?: number;
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
 * Resolve real kinetic parameters for an enzyme/substrate pair.
 *
 * This function spawns a Python bridge that uses the existing BRENDA/KEGG/PubMed
 * lookup code in Tests/fallback_logic.py. If an EC number isn't already known,
 * the Python side resolves one live via UniProt's name search
 * (Tests/enzyme_lookup.py::fetch_ec_number_by_name) before attempting BRENDA --
 * this is what lets an enzyme name outside the small hardcoded pattern list in
 * enzymes.ts still reach a real literature lookup. Only skips the Python
 * bridge entirely, returning `found: false`, when there is truly nothing to
 * search for (no EC number AND no enzyme name).
 */
export async function resolveKineticValue(
  entities: EntityExtraction,
): Promise<ScienceAgentResult> {
  if (!entities.ecNumber && !entities.enzymeName) {
    return {
      found: false,
      literatureCandidates: [],
      logs: ["No enzyme name or EC number provided; skipping real parameter lookup."],
    };
  }

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
      if (code !== 0 || !trimmed) {
        const message =
          stderr || `Science agent runner exited with code ${code}`;
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

    proc.stdin.write(
      JSON.stringify({
        enzymeName: entities.enzymeName ?? "",
        substrate: entities.substrate ?? "",
        organism: entities.organism,
        ecNumber: entities.ecNumber,
        parameterType: entities.parameterType ?? "",
      }),
    );
    proc.stdin.end();
  });
}
