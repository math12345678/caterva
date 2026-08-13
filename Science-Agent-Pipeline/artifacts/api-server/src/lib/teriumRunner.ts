import { spawn } from "node:child_process";
import { access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { findRepositoryRoot } from "./repoRoot";
import { resolvePythonExecutable } from "./python";

// 15 core scientific domains + SBML escape hatch. This union must
// match terium_runner.py's DISPATCH table exactly (ADR 0007);
// Terium/tests/test_boundary_contract.py fails if they drift.
export type SimulationDomain =
  | "mm"
  | "mm_competitive_inhibition"
  | "sir"
  | "seir"
  | "wright_fisher"
  | "gillespie_ssa"
  | "pcr"
  | "molecular_dynamics"
  | "gillespie_ssa_bimolecular"
  | "two_locus_wright_fisher"
  // Both are in the engine's __all__ and its DISPATCH table (ADR 0007: the
  // engine's surface is the contract). They were briefly absent here,
  // which led to them being deleted from DISPATCH to match -- breaking
  // five boundary-contract tests. Listed here so the drift cannot recur in
  // that direction.
  | "monte_carlo_pi"
  | "gillespie_ssa_replicates"
  // Three ODE oscillator domains (ADR 0022): predator-prey (Lotka 1925 /
  // Volterra 1926), the cdc2-cyclin cell cycle relaxation oscillator
  // (Tyson 1991), and the synthetic three-gene repressilator (Elowitz &
  // Leibler 2000).
  | "lotka_volterra"
  | "cell_cycle_oscillator"
  | "repressilator"
  | "sbml";

export interface TeriumPoint {
  [species: string]: number;
}

export interface TeriumResult {
  ok: true;
  domain: SimulationDomain;
  parameters: Record<string, number | string | boolean | null | number[]>;
  trajectory: TeriumPoint[];
  flagged: boolean;
  flagReason: string | null;
}

interface PythonError {
  ok: false;
  error: string;
}

const _dirname = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = findRepositoryRoot(_dirname);

/** Preserve caller-provided import paths while adding the repository root. */
export function buildTeriumEnvironment(
  baseEnv: NodeJS.ProcessEnv,
  repoRoot: string,
): NodeJS.ProcessEnv {
  return {
    ...baseEnv,
    PYTHONPATH: [baseEnv.PYTHONPATH, repoRoot]
      .filter(Boolean)
      .join(path.delimiter),
  };
}

const SCRIPT_PATH = path.join(
  REPO_ROOT,
  "Science-Agent-Pipeline",
  "artifacts",
  "api-server",
  "src",
  "lib",
  "terium_runner.py",
);

let scriptChecked = false;

async function ensureRunnerScript(): Promise<void> {
  if (scriptChecked) return;
  try {
    await access(SCRIPT_PATH);
    scriptChecked = true;
  } catch {
    throw new Error(
      `Terium runner script not found at ${SCRIPT_PATH}. ` +
        "Did the build copy it?",
    );
  }
}

/**
 * Read the runner's stdout as its result envelope, or `undefined` if it is
 * not JSON at all.
 *
 * Separate from the reject/resolve logic so the engine's own explanation can
 * be consulted BEFORE the exit status is interpreted -- a rejected run has
 * both a nonzero status and a perfectly good reason, and only one of them is
 * worth telling a user.
 */
function parsePayload(
  stdout: string,
): TeriumResult | PythonError | undefined {
  if (!stdout) return undefined;
  try {
    const parsed = JSON.parse(stdout) as unknown;
    if (typeof parsed !== "object" || parsed === null) return undefined;
    if (typeof (parsed as { ok?: unknown }).ok !== "boolean") return undefined;
    return parsed as TeriumResult | PythonError;
  } catch {
    return undefined;
  }
}

/**
 * Run the Python Terium engine for a given domain and parameters.
 *
 * Physical validation remains authoritative in the Python engine. This bridge
 * only transports the request and preserves the engine's stable result shape.
 */
export async function runTerium(
  domain: SimulationDomain,
  parameters: Record<string, number | string | boolean | null | number[]>,
  signal?: AbortSignal,
): Promise<TeriumResult> {
  await ensureRunnerScript();

  const pythonExecutable = resolvePythonExecutable(REPO_ROOT);

  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error("Cancelled"));
      return;
    }

    const proc = spawn(pythonExecutable, [SCRIPT_PATH], {
      cwd: REPO_ROOT,
      env: buildTeriumEnvironment(process.env, REPO_ROOT),
    });

    const onAbort = () => {
      proc.kill("SIGTERM");
      reject(new Error("Cancelled"));
    };

    if (signal) signal.addEventListener("abort", onAbort, { once: true });

    let stdout = "";
    let stderr = "";
    let stdinError: Error | undefined;

    proc.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf-8");
    });

    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf-8");
    });

    proc.on("error", (err) => {
      reject(new Error(`Failed to spawn Terium runner: ${err.message}`));
    });

    // A child that dies before reading its input makes the stdin write below
    // fail with EPIPE. An 'error' event on a stream with no listener is an
    // uncaughtException in Node, so without this handler a Python process
    // that exits early did not fail the job -- it took the API server down
    // with it. Recorded rather than rejected: the 'close' handler always
    // runs afterwards and knows the exit status and signal, so it can say
    // something considerably more useful than "write EPIPE".
    proc.stdin.on("error", (err: Error) => {
      stdinError = err;
    });

    // `killedBySignal`, not `signal` -- the AbortSignal parameter of this
    // function is also called `signal` and is still needed on the next line.
    proc.on("close", (code, killedBySignal) => {
      if (signal) signal.removeEventListener("abort", onAbort);
      const trimmed = stdout.trim();
      const detail = stderr.trim();

      // THE REASON COMES FIRST.
      //
      // The engine reports a rejected run as `{"ok": false, "error": ...}`
      // on STDOUT and exits 1. This handler used to test `code !== 0`
      // before parsing anything, so it rejected with `stderr ||
      // "exited with code 1"` -- and stderr is empty, because the engine put
      // the explanation on stdout. The `if (!parsed.ok) reject(parsed.error)`
      // branch that came after was therefore unreachable for every
      // structured rejection the engine has ever produced: it could only
      // have run for a rejection reported with exit status 0, which the
      // engine never does.
      //
      // Concretely, an over-budget population returns
      //
      //   {"ok": false, "error": "a0+b0=1100000 exceeds API runtime ceiling
      //    (MAX_API_SSA_POPULATION) 1000000"}
      //
      // and the API user was told "Terium runner exited with code 1". Rule 2
      // of the constitution -- reject the impossible WITH a reason -- was
      // being honoured by the engine and thrown away one layer above it.
      // A user cannot act on an exit status; they can act on "lower a0+b0
      // below 1000000".
      const structured = parsePayload(trimmed);

      if (structured && structured.ok === false) {
        reject(new Error(structured.error));
        return;
      }

      // Three further facts used to collapse into that same message:
      //
      //   * killed by a signal        -> "exited with code null"
      //   * exited nonzero, no reason -> the only case the message fitted
      //   * exited 0 but wrote nothing-> "exited with code 0"
      //
      // The last one tells a user that a *successful* exit status is the
      // reason their simulation failed, and the first one is what an
      // out-of-memory kill on a long run looks like -- the single most
      // useful thing to know about a large simulation that vanished, and
      // the code had it in hand and threw it away.
      if (killedBySignal) {
        reject(
          new Error(
            `Terium runner was killed by ${killedBySignal} before it ` +
              "produced a result. On a long or large run this is usually the " +
              "operating system reclaiming memory." +
              (detail ? ` Runner stderr: ${detail}` : ""),
          ),
        );
        return;
      }

      if (code !== 0) {
        reject(
          new Error(
            detail ||
              `Terium runner exited with status ${code} and wrote nothing ` +
                "to stderr.",
          ),
        );
        return;
      }

      if (!trimmed) {
        reject(
          new Error(
            "Terium runner exited successfully but produced no result on " +
              "stdout." +
              (detail ? ` Runner stderr: ${detail}` : "") +
              (stdinError
                ? ` It also closed its input before the request was written (${stdinError.message}).`
                : ""),
          ),
        );
        return;
      }

      if (!structured) {
        // The output itself is the evidence, and it used to be withheld:
        // the message quoted only the parser's complaint ("Unexpected token
        // at position 0"), which cannot distinguish a traceback from an
        // empty string from a stray print().
        const excerpt =
          trimmed.length > 400 ? `${trimmed.slice(0, 400)}...` : trimmed;
        reject(
          new Error(
            `Terium runner returned output that is not JSON. It said: ${excerpt}`,
          ),
        );
        return;
      }

      resolve(structured);
    });

    proc.stdin.write(JSON.stringify({ domain, parameters }));
    proc.stdin.end();
  });
}
