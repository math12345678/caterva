import { spawn } from "node:child_process";
import { access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

export type SimulationDomain = "mm" | "sir" | "seir";

export interface TelluriumPoint {
  t: number;
  [species: string]: number;
}

export interface TelluriumResult {
  ok: true;
  domain: SimulationDomain;
  parameters: Record<string, number | string | boolean>;
  trajectory: TelluriumPoint[];
  flagged: boolean;
  flagReason: string | null;
}

interface PythonError {
  ok: false;
  error: string;
}

const _dirname = path.dirname(fileURLToPath(import.meta.url));
// When running from the built dist/index.mjs, _dirname is api-server/dist/
// When running from source directly (vitest), _dirname is api-server/src/lib/
// The Terrium repo root is 4 levels up from dist/ or 5 levels up from src/lib/
const LEVELS_UP = _dirname.replace(/\\/g, "/").endsWith("/dist") ? 4 : 5;
const REPO_ROOT = path.resolve(_dirname, ...Array(LEVELS_UP).fill(".."));
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
 * This function spawns `python3` with the Tellurium runner script. The script
 * imports the Python simulation engine from the repo root, so we add the repo
 * root to PYTHONPATH and run the script with the working directory set to the
 * repo root.
 *
 * TODO(OpenCode): Replace this child_process bridge with a proper Python
 * microservice or FFI binding once the pipeline is stable. The current bridge
 * is intentionally simple so the frontend can call the engine end-to-end
 * without adding network dependencies.
 */
export async function runTellurium(
  domain: SimulationDomain,
  parameters: Record<string, number | string | boolean>,
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

    if (signal) {
      signal.addEventListener("abort", onAbort, { once: true });
    }

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
      if (signal) {
        signal.removeEventListener("abort", onAbort);
      }
      const trimmed = stdout.trim();
      if (code !== 0 || !trimmed) {
        const message = stderr || `Tellurium runner exited with code ${code}`;
        reject(new Error(message));
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
