import { spawn } from "node:child_process";
import { access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { findRepositoryRoot } from "./repoRoot";

export type SimulationDomain =
  | "mm"
  | "sir"
  | "seir"
  | "pcr"
  | "monte_carlo_pi"
  | "wright_fisher"
  | "two_locus_wright_fisher"
  | "molecular_dynamics"
  | "gillespie_ssa"
  | "sbml";

export interface TelluriumPoint {
  [species: string]: number;
}

export interface TelluriumResult {
  ok: true;
  domain: SimulationDomain;
  parameters: Record<string, number | string | boolean | null | number[]>;
  trajectory: TelluriumPoint[];
  flagged: boolean;
  flagReason: string | null;
}

interface PythonError {
  ok: false;
  error: string;
}

const _dirname = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = findRepositoryRoot(_dirname);
const SCRIPT_PATH = path.join(
  REPO_ROOT,
  "Science-Agent-Pipeline",
  "artifacts",
  "api-server",
  "src",
  "lib",
  "tellurium_runner.py",
);

let scriptChecked = false;

async function ensureRunnerScript(): Promise<void> {
  if (scriptChecked) return;
  try {
    await access(SCRIPT_PATH);
    scriptChecked = true;
  } catch {
    throw new Error(
      `Tellurium runner script not found at ${SCRIPT_PATH}. ` +
        "Did the build copy it?",
    );
  }
}

/**
 * Run the Python Tellurium engine for a given domain and parameters.
 *
 * Physical validation remains authoritative in the Python engine. This bridge
 * only transports the request and preserves the engine's stable result shape.
 */
export async function runTellurium(
  domain: SimulationDomain,
  parameters: Record<string, number | string | boolean | null | number[]>,
  signal?: AbortSignal,
): Promise<TelluriumResult> {
  await ensureRunnerScript();

  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error("Cancelled"));
      return;
    }

    const proc = spawn("python3", [SCRIPT_PATH], {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        PYTHONPATH: REPO_ROOT,
      },
    });

    const onAbort = () => {
      proc.kill("SIGTERM");
      reject(new Error("Cancelled"));
    };

    if (signal) signal.addEventListener("abort", onAbort, { once: true });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf-8");
    });

    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf-8");
    });

    proc.on("error", (err) => {
      reject(new Error(`Failed to spawn Tellurium runner: ${err.message}`));
    });

    proc.on("close", (code) => {
      if (signal) signal.removeEventListener("abort", onAbort);
      const trimmed = stdout.trim();
      if (code !== 0 || !trimmed) {
        reject(new Error(stderr || `Tellurium runner exited with code ${code}`));
        return;
      }

      try {
        const parsed = JSON.parse(trimmed) as TelluriumResult | PythonError;
        if (!parsed.ok) {
          reject(new Error(parsed.error));
          return;
        }
        resolve(parsed);
      } catch (err) {
        reject(
          new Error(
            `Tellurium runner returned invalid JSON: ${err instanceof Error ? err.message : String(err)}`,
          ),
        );
      }
    });

    proc.stdin.write(JSON.stringify({ domain, parameters }));
    proc.stdin.end();
  });
}
