"use strict";
/**
 * Bridge from this tree to the real Tellurium engine.
 *
 * WHY THIS EXISTS
 *
 * `ScientificPipeline.runSimulation` did not run a simulation. It contained
 * a hand-rolled Michaelis-Menten forward-Euler loop:
 *
 *     let s = parameters.s0?.value || 1.0;
 *     const km = parameters.km?.value || 5.0;
 *     const vmax = parameters.vmax?.value || 10.0;
 *     for (let t = 0; t <= t_end; t += dt) {
 *       const v = (vmax * s) / (km + s);
 *       s = Math.max(0, s - v * dt);
 *     }
 *
 * Three separate problems, in increasing order of seriousness:
 *
 *   1. It is a duplicate implementation of a model the Python engine
 *      already implements, integrated with a first-order explicit method at
 *      fixed dt rather than the engine's adaptive solver. Two
 *      implementations of one model is a guaranteed source of results that
 *      disagree with the product's own answer.
 *   2. `Math.max(0, ...)` clamps negative substrate rather than reporting
 *      that the step size was too large, so it silently produced a
 *      plausible-looking trajectory in exactly the regime where it was
 *      wrong.
 *   3. `|| 5.0`, `|| 10.0`, `|| 1.0`. Those defaults are the entire thing
 *      Terrium exists to refuse. A missing Km silently became 5.0 and the
 *      run continued, producing a trajectory with a provenance record
 *      claiming literature backing for a number nothing supplied. This is
 *      the same hard rule the engine enforces via ParameterOrigin: a
 *      simulation must not run on `default` values.
 *
 * This module replaces all of it by spawning the SAME
 * `tellurium_runner.py` the production api-server uses
 * (`Science-Agent-Pipeline/artifacts/api-server/src/lib/telluriumRunner.ts`),
 * over the same JSON stdin/stdout protocol. Physical validation stays
 * authoritative in the Python engine; nothing here reimplements a model.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.REPO_ROOT = exports.MissingParameterError = void 0;
exports.findRepositoryRoot = findRepositoryRoot;
exports.resolvePythonExecutable = resolvePythonExecutable;
exports.runTellurium = runTellurium;
exports.extractSeries = extractSeries;
const child_process_1 = require("child_process");
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const logger_1 = require("../logger");
/** A simulation must not be started with a parameter nobody supplied. */
class MissingParameterError extends Error {
    missing;
    constructor(domain, missing) {
        super(`Cannot run '${domain}': required parameter(s) ${missing.join(', ')} ` +
            'were not supplied. Terrium does not substitute defaults for missing ' +
            'scientific parameters -- a run on an invented value produces a ' +
            'result that looks measured and is not.');
        this.name = 'MissingParameterError';
        this.missing = missing;
    }
}
exports.MissingParameterError = MissingParameterError;
/**
 * Locate the repository root by walking up for a marker that identifies
 * THIS repository, rather than assuming a fixed depth from __dirname.
 * `Tellurium/tellurium_engine.py` is used because the bridge is useless
 * without it, so its absence should fail here rather than later.
 */
function findRepositoryRoot(startDirectory) {
    let current = path.resolve(startDirectory);
    for (;;) {
        if (fs.existsSync(path.join(current, 'Tellurium', 'tellurium_engine.py'))) {
            return current;
        }
        const parent = path.dirname(current);
        if (parent === current) {
            throw new Error(`Could not locate the Terrium repository root above ${startDirectory} ` +
                '(looked for Tellurium/tellurium_engine.py).');
        }
        current = parent;
    }
}
exports.REPO_ROOT = findRepositoryRoot(__dirname);
const SCRIPT_PATH = path.join(exports.REPO_ROOT, 'Science-Agent-Pipeline', 'artifacts', 'api-server', 'src', 'lib', 'tellurium_runner.py');
/**
 * Which interpreter to use.
 *
 * A repository-local virtualenv is preferred over whatever `python3`
 * happens to be on PATH, because the engine's dependencies (roadrunner,
 * numpy) are installed there and a bare `python3` will usually fail to
 * import them. `TERRIUM_PYTHON` overrides for unusual setups.
 */
function resolvePythonExecutable(repoRoot) {
    const override = process.env['TERRIUM_PYTHON'];
    if (override) {
        return override;
    }
    for (const candidate of [
        path.join(repoRoot, '.venv', 'bin', 'python3'),
        path.join(repoRoot, 'venv', 'bin', 'python3')
    ]) {
        if (fs.existsSync(candidate)) {
            return candidate;
        }
    }
    return 'python3';
}
/** How long the engine may run before we stop waiting. */
const ENGINE_TIMEOUT_MS = 120_000;
/**
 * Run a domain in the Python engine.
 *
 * `required` names the parameters that must be present. Any that are
 * missing raise MissingParameterError BEFORE the engine is started -- the
 * check exists so a missing value cannot be quietly replaced by a default
 * on this side of the boundary.
 */
async function runTellurium(domain, parameters, options = {}) {
    const required = options.required ?? [];
    const missing = required.filter((name) => parameters[name] === undefined || parameters[name] === null);
    if (missing.length > 0) {
        throw new MissingParameterError(domain, missing);
    }
    if (!fs.existsSync(SCRIPT_PATH)) {
        throw new Error(`Tellurium runner script not found at ${SCRIPT_PATH}. This bridge runs ` +
            'the real engine and will not fall back to a local approximation.');
    }
    const pythonExecutable = resolvePythonExecutable(exports.REPO_ROOT);
    return new Promise((resolve, reject) => {
        if (options.signal?.aborted) {
            reject(new Error('Cancelled'));
            return;
        }
        const proc = (0, child_process_1.spawn)(pythonExecutable, [SCRIPT_PATH], {
            cwd: exports.REPO_ROOT,
            env: {
                ...process.env,
                PYTHONPATH: [process.env['PYTHONPATH'], exports.REPO_ROOT]
                    .filter(Boolean)
                    .join(path.delimiter)
            }
        });
        let settled = false;
        const finish = (fn) => {
            if (settled)
                return;
            settled = true;
            clearTimeout(timer);
            if (options.signal)
                options.signal.removeEventListener('abort', onAbort);
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
            finish(() => reject(new Error(`Tellurium engine exceeded ${ENGINE_TIMEOUT_MS}ms for domain '${domain}'`)));
        }, ENGINE_TIMEOUT_MS);
        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', (chunk) => {
            stdout += chunk.toString('utf-8');
        });
        proc.stderr.on('data', (chunk) => {
            stderr += chunk.toString('utf-8');
        });
        proc.on('error', (err) => {
            finish(() => reject(new Error(`Failed to spawn Tellurium engine: ${err.message}`)));
        });
        proc.on('close', (code) => {
            const trimmed = stdout.trim();
            if (code !== 0 || !trimmed) {
                finish(() => reject(new Error(stderr.trim() || `Tellurium engine exited with code ${code}`)));
                return;
            }
            try {
                const parsed = JSON.parse(trimmed);
                if (!parsed.ok) {
                    // The engine's own rejection (Rule 1: physically impossible
                    // input). Surfaced verbatim rather than reinterpreted here --
                    // the engine is authoritative on physical validity.
                    finish(() => reject(new Error(parsed.error)));
                    return;
                }
                // The engine echoes the parameters it actually used. Any key we
                // sent that is absent from the echo was IGNORED -- which is how
                // `t_end`/`n_points` were silently dropped in favour of the
                // runner's `end`/`points`, leaving the caller believing it had set
                // a resolution it had not. A misspelled parameter must be loud.
                const echoed = parsed.parameters ?? {};
                const exempt = new Set(options.notEchoed ?? []);
                const ignored = Object.keys(parameters).filter((key) => parameters[key] !== null && !(key in echoed) && !exempt.has(key));
                if (ignored.length > 0) {
                    finish(() => reject(new Error(`Tellurium engine ignored parameter(s) ${ignored.join(', ')} for ` +
                        `domain '${domain}'. It accepted: ${Object.keys(echoed).join(', ')}. ` +
                        'A parameter the engine silently drops leaves the caller ' +
                        'believing it set a value it did not.')));
                    return;
                }
                if (parsed.flagged) {
                    logger_1.logger.warn({ domain, flagReason: parsed.flagReason }, 'Engine flagged this run as implausible (Rule 2)');
                }
                finish(() => resolve(parsed));
            }
            catch (err) {
                finish(() => reject(new Error('Tellurium engine returned invalid JSON: ' +
                    (err instanceof Error ? err.message : String(err)))));
            }
        });
        proc.stdin.write(JSON.stringify({ domain, parameters }));
        proc.stdin.end();
    });
}
/**
 * Species keys the engine emits, in the order this tree prefers when
 * choosing which one is "the" tracked value.
 *
 * The engine returns every species (`[S]`, `[P]`, `S`, `I`, `R`, ...) and
 * the caller here wants a single scalar per timepoint. Rather than guess,
 * the substrate/first-listed convention is applied explicitly and the full
 * record is preserved alongside it.
 */
function extractSeries(trajectory, preferred) {
    if (trajectory.length === 0) {
        return { key: '', points: [] };
    }
    const first = trajectory[0];
    const speciesKeys = Object.keys(first).filter((k) => k !== 'time');
    if (speciesKeys.length === 0) {
        return { key: '', points: [] };
    }
    const key = preferred && speciesKeys.includes(preferred) ? preferred : speciesKeys[0];
    return {
        key,
        points: trajectory.map((point) => ({
            time: point['time'] ?? 0,
            value: point[key] ?? 0
        }))
    };
}
