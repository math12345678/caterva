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

/**
 * A domain the runner handles WITHOUT a matching engine `simulate_*`.
 *
 * `SimulationDomain` above mirrors terium_runner.py's DISPATCH exactly, and
 * scripts/check_domain_parity.py enforces that across three files. That
 * contract is correct and stays intact.
 *
 * `compose` composes furthest of all and touches no engine function
 * directly: it recognises a MECHANISM in a description, builds a reaction
 * network from motifs, and dimensionally checks every rate law before
 * anything runs. See ADR 0173.
 *
 * `parameterize` composes more still: it resolves every unknown constant
 * from the literature concurrently, judges whether the resolved set is
 * mutually usable, re-searches under whatever that judgement requires, and
 * explores each candidate organism. See ADR 0171.
 *
 * `network` does not belong to it: it composes three engine calls --
 * compile_with_provenance, antimony_to_sbml, simulate_sbml -- so there is
 * no single function for DISPATCH to name. Python declares the same
 * category as COMPOSED_DOMAINS, and the boundary contract test requires a
 * composed domain to have a handler and to be reachable. Adding it to
 * SimulationDomain instead would have forced either a fictional engine
 * function or a weakened parity check.
 */
export type ComposedDomain = "network" | "parameterize" | "compose";

/** Anything the runner will dispatch. */
export type RunnableDomain = SimulationDomain | ComposedDomain;

/** The composed domains, as values, so the narrowing below cannot drift. */
export const COMPOSED_DOMAINS: readonly ComposedDomain[] = [
  "network",
  "parameterize",
  "compose",
] as const;

/**
 * Narrow a RunnableDomain to a catalogue domain, or throw.
 *
 * Used where a value must be a catalogue domain for a reason beyond
 * typing -- the `simulations` table's `domain` column is a Postgres enum
 * of the sixteen, and `network` is not one of them.
 *
 * A checked narrowing rather than a cast, deliberately. `as
 * SimulationDomain` would compile and then fail in the database, at
 * insert time, with an error about an enum value rather than about the
 * mistake. This fails where the mistake is.
 */
export function asSimulationDomain(domain: RunnableDomain): SimulationDomain {
  if ((COMPOSED_DOMAINS as readonly string[]).includes(domain)) {
    throw new Error(
      `${domain} is a composed domain and has no place in the catalogue ` +
        `domain set; it is not persistable to the simulations table, whose ` +
        `domain column is an enum of the catalogue domains.`,
    );
  }
  return domain as SimulationDomain;
}

/**
 * A model the caller constructed, as sent to the engine.
 *
 * Typed as `unknown` deliberately rather than mirrored here: the authority
 * on a network's shape is `reactionNetwork.ts`'s Zod schema on the way in
 * and `Terium/core/network.py` at the engine boundary. A third structural
 * definition in the transport layer would be a third thing to keep in step.
 */
export type NetworkPayload = Record<string, unknown>;

export interface TeriumPoint {
  [species: string]: number;
}

export interface TeriumResult {
  ok: true;
  domain: RunnableDomain;
  parameters: Record<string, number | string | boolean | null | number[]>;
  trajectory: TeriumPoint[];
  flagged: boolean;
  flagReason: string | null;
  /**
   * Present only for `network` runs.
   *
   * `conservationLaws` are DERIVED from the model's own stoichiometry --
   * `["S + I + R"]` for an SIR-shaped network -- and `quantitySources`
   * records what backs each number. Both are things a reader of a
   * simulation is entitled to and cannot get from a catalogue domain.
   */
  conservationLaws?: string[];
  quantitySources?: Record<
    string,
    { origin: string | null; citation: string | null; note: string | null }
  >;
  antimony?: string;
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
 * Wall-clock ceiling for a single engine subprocess, in milliseconds.
 *
 * There was no time limit here at all: `spawn` was called with no `timeout`,
 * and the only path that ever killed the child was the AbortSignal, which
 * fires on explicit job cancellation and never on a clock. A run that never
 * terminated held its queue slot forever, and nothing in the pipeline would
 * notice.
 *
 * For the fifteen preset domains this was masked -- terium_runner.py's
 * MAX_API_* ceilings bound the WORK (samples, generations, steps), so a
 * legitimate request cannot run long. The measurements recorded beside those
 * constants put the slowest permitted run (MD, 108 particles x 10k steps) at
 * ~7.3s. This default leaves an order of magnitude of headroom over that
 * while still bounding a runaway.
 *
 * Those ceilings are per-domain and keyed to specific parameters, so they do
 * NOT cover a model whose cost is not expressible as one of those counters.
 * A time limit is the only backstop that holds regardless of which domain
 * runs or what the model does, which is why it belongs here at the boundary
 * rather than beside any one ceiling.
 *
 * Override with TERIUM_RUNNER_TIMEOUT_MS (a positive integer); an unset,
 * unparseable, or non-positive value falls back to the default rather than
 * silently disabling the limit.
 */
const DEFAULT_RUNNER_TIMEOUT_MS = 120_000;

export function resolveRunnerTimeoutMs(
  env: NodeJS.ProcessEnv = process.env,
): number {
  const raw = env.TERIUM_RUNNER_TIMEOUT_MS;
  if (raw === undefined) return DEFAULT_RUNNER_TIMEOUT_MS;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return DEFAULT_RUNNER_TIMEOUT_MS;
  }
  return parsed;
}

/**
 * Run the Python Terium engine for a given domain and parameters.
 *
 * Physical validation remains authoritative in the Python engine. This bridge
 * only transports the request and preserves the engine's stable result shape.
 */
export async function runTerium(
  domain: RunnableDomain,
  parameters: Record<
    string,
    number | string | boolean | null | number[] | NetworkPayload
  >,
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

    // Distinguishes a timeout kill from every other way the child can die by
    // a signal. Without it the `close` handler's `killedBySignal` branch
    // attributes the death to the OS reclaiming memory, which is the right
    // guess for an unexplained SIGKILL but exactly wrong here -- it would
    // send someone looking for a memory problem they do not have, when the
    // actual fact ("it ran longer than the limit, here is the limit") is
    // known and actionable.
    const timeoutMs = resolveRunnerTimeoutMs();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      // SIGKILL, not SIGTERM: the point of this path is that the child is
      // not responding to the clock, and a wedged or CPU-bound process can
      // ignore SIGTERM. The `close` handler still runs and reports.
      proc.kill("SIGKILL");
    }, timeoutMs);
    const clearTimer = () => clearTimeout(timer);

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
      clearTimer();
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
      clearTimer();
      if (signal) signal.removeEventListener("abort", onAbort);
      const trimmed = stdout.trim();
      const detail = stderr.trim();

      // Before the structured-payload check below: a killed child may have
      // written a partial line to stdout, and a truncated payload is not a
      // rejection the engine chose to report. The timeout is the reason
      // this process died, and it is the fact worth reporting.
      if (timedOut) {
        reject(
          new Error(
            `Terium runner exceeded the ${timeoutMs}ms time limit and was ` +
              "killed. Reduce the size of the run (fewer points, steps, " +
              "generations or replicates), or raise " +
              "TERIUM_RUNNER_TIMEOUT_MS if this model legitimately needs " +
              "longer." +
              (detail ? ` Runner stderr: ${detail}` : ""),
          ),
        );
        return;
      }

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
