"use strict";
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
exports.ResolverUnavailableError = void 0;
exports.resolveKinetic = resolveKinetic;
const child_process_1 = require("child_process");
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const logger_1 = require("../logger");
const telluriumBridge_1 = require("../engine/telluriumBridge");
const DEFAULT_SCRIPT_PATH = path.join(telluriumBridge_1.REPO_ROOT, 'Science-Agent-Pipeline', 'artifacts', 'api-server', 'src', 'lib', 'science_agent_runner.py');
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
function scriptPath() {
    return process.env['TERRIUM_LITERATURE_RUNNER'] || DEFAULT_SCRIPT_PATH;
}
/** BRENDA and PubMed are network calls; this is generous but finite. */
const RESOLVER_TIMEOUT_MS = 120_000;
/** Raised when the resolver could not be run at all. Deliberately distinct
 *  from `found: false`: "the registry says no" and "we never asked" are
 *  different facts, and collapsing them is how an unchecked value comes to
 *  look checked. */
class ResolverUnavailableError extends Error {
    constructor(message) {
        super(message);
        this.name = 'ResolverUnavailableError';
    }
}
exports.ResolverUnavailableError = ResolverUnavailableError;
/**
 * Resolve one kinetic constant from the real literature layer.
 *
 * Returns `found: false` when BRENDA and PubMed genuinely have nothing --
 * that is an answer. Throws ResolverUnavailableError when the resolver
 * could not run, because a failure to look is not evidence of absence.
 */
async function resolveKinetic(query, options = {}) {
    if (!query.ecNumber && !query.enzymeName) {
        throw new ResolverUnavailableError('Neither ecNumber nor enzymeName was supplied, so there is nothing to ' +
            'search for. The resolver will not guess an enzyme identity.');
    }
    const runnerScript = scriptPath();
    if (!fs.existsSync(runnerScript)) {
        throw new ResolverUnavailableError(`Literature resolver not found at ${runnerScript}. This module resolves ` +
            'against BRENDA/PubMed and will not fall back to a local table.');
    }
    const quantity = query.quantity ?? 'km';
    const pythonExecutable = (0, telluriumBridge_1.resolvePythonExecutable)(telluriumBridge_1.REPO_ROOT);
    const raw = await new Promise((resolve, reject) => {
        if (options.signal?.aborted) {
            reject(new Error('Cancelled'));
            return;
        }
        const proc = (0, child_process_1.spawn)(pythonExecutable, [runnerScript], {
            cwd: telluriumBridge_1.REPO_ROOT,
            env: {
                ...process.env,
                // Tests/ is on the path as well as the repo root: the runner
                // imports `fallback_logic` and `enzyme_lookup` as top-level
                // modules, matching how scienceAgent.ts invokes it.
                PYTHONPATH: [
                    process.env['PYTHONPATH'],
                    telluriumBridge_1.REPO_ROOT,
                    path.join(telluriumBridge_1.REPO_ROOT, 'Tests')
                ]
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
            finish(() => reject(new ResolverUnavailableError(`Literature resolver exceeded ${RESOLVER_TIMEOUT_MS}ms`)));
        }, RESOLVER_TIMEOUT_MS);
        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', (c) => {
            stdout += c.toString('utf-8');
        });
        proc.stderr.on('data', (c) => {
            stderr += c.toString('utf-8');
        });
        proc.on('error', (err) => {
            finish(() => reject(new ResolverUnavailableError(`Failed to spawn literature resolver: ${err.message}`)));
        });
        proc.on('close', (code) => {
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
            finish(() => reject(new ResolverUnavailableError(stderr.trim() || `Literature resolver exited with code ${code}`)));
        });
        proc.stdin.write(JSON.stringify({
            enzymeName: query.enzymeName,
            substrate: query.substrate,
            organism: query.organism,
            ecNumber: query.ecNumber,
            quantity,
            enzymeConc: query.enzymeConc
        }));
        proc.stdin.end();
    });
    let parsed;
    try {
        parsed = JSON.parse(raw);
    }
    catch (err) {
        throw new ResolverUnavailableError('Literature resolver returned invalid JSON: ' +
            (err instanceof Error ? err.message : String(err)));
    }
    if (parsed['ok'] !== true) {
        throw new ResolverUnavailableError(String(parsed['error'] ?? 'Literature resolver reported an error'));
    }
    const logs = Array.isArray(parsed['logs'])
        ? parsed['logs']
        : [];
    if (parsed['found'] !== true) {
        logger_1.logger.info({ query, quantity }, 'Literature resolver found no value; reporting absence rather than a default');
        return { found: false, quantity, logs };
    }
    // The value is emitted under the key matching the quantity ("km", "ki",
    // "kcat") so a cross-species Ki cannot be read as a Km.
    const value = parsed[quantity];
    const unit = parsed['unit'];
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw new ResolverUnavailableError(`Resolver reported found=true but no usable '${quantity}' value.`);
    }
    if (typeof unit !== 'string' || unit.length === 0) {
        // A number without its unit is not a measurement. Km in mM and Km in
        // uM differ by 1000x, and this tree has already been bitten twice by
        // assumed units.
        throw new ResolverUnavailableError(`Resolver returned a '${quantity}' value with no unit. A kinetic ` +
            'constant without its unit cannot be used.');
    }
    return {
        found: true,
        quantity,
        value,
        unit,
        organism: parsed['organism'] ?? null,
        source: String(parsed['source'] ?? 'unknown'),
        citation: parsed['citation'] ?? null,
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
            ? { bridgedVmax: parsed['vmax'] }
            : {}),
        ...(parsed['vmaxValidation']
            ? {
                vmaxValidation: parsed['vmaxValidation']
            }
            : {}),
        logs
    };
}
