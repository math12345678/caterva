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
 * Terrium's actual literature layer is `Tests/fallback_logic.py`
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
import { REPO_ROOT, resolvePythonExecutable } from '../engine/teriumBridge';

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
   * Vmax = kcat * [E]0, present only for a kcat query with `enzymeConc`.
   *
   * Computed in PYTHON by the same
   * `Terium.core.validation.vmax_from_kcat()` the engine itself uses --
   * one implementation of the arithmetic and its Rule 2 bounds, not a
   * second copy in TypeScript. The [E]0/Km flag in particular carries a
   * threshold that must not be duplicated here and allowed to drift.
   */
  bridgedVmax?: number;
  vmaxValidation?: { ok: boolean; flagged: boolean; reason?: string };
  logs: string[];
}

export interface UnresolvedKinetic {
  found: false;
  quantity: KineticQuantity;
  /** Why nothing was found -- the resolver's own search log. */
  logs: string[];
}

export type ResolverResult = ResolvedKinetic | UnresolvedKinetic;

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
 * `TERRIUM_LITERATURE_RUNNER` overrides it so the subprocess path -- spawn,
 * stdin, exit code, stdout parsing -- can be exercised against a stub that
 * emits canned JSON, with no network. That path is where the bugs actually
 * are: the first version of this module threw away the runner's structured
 * `{"ok": false, "error": "403 Forbidden"}` because the process also
 * exited 1, replacing a precise cause with "exited with code 1". A mock of
 * the whole module would not have caught that; a real subprocess does.
 */
function scriptPath(): string {
  return process.env['TERRIUM_LITERATURE_RUNNER'] || DEFAULT_SCRIPT_PATH;
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
        enzymeConc: query.enzymeConc
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
    logger.info(
      { query, quantity },
      'Literature resolver found no value; reporting absence rather than a default'
    );
    return { found: false, quantity, logs };
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

  return {
    found: true,
    quantity,
    value,
    unit,
    organism: (parsed['organism'] as string) ?? null,
    source: String(parsed['source'] ?? 'unknown'),
    citation: (parsed['citation'] as ResolvedCitation) ?? null,
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
