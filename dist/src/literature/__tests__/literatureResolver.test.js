"use strict";
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
/**
 * The literature resolver bridge.
 *
 * `LiteratureService` was an in-memory `Map` that reached no database,
 * registry or API -- everything it "recommended" was something the caller
 * had already handed it. This module connects it to Terrium's real
 * literature layer (`Tests/fallback_logic.py` via
 * `science_agent_runner.py`), which walks BRENDA exact -> BRENDA
 * cross-species -> PubMed and never fabricates a number.
 *
 * These tests spawn a REAL subprocess against a stub runner rather than
 * mocking the module. The subprocess boundary is where this module's bugs
 * actually were: the first version discarded the runner's structured
 * `{"ok": false, "error": "403 Forbidden"}` because the process also
 * exited 1, turning a precise cause into "exited with code 1". Mocking
 * `resolveKinetic` would have tested nothing that broke.
 */
const child_process_1 = require("child_process");
const fs = __importStar(require("fs"));
const os = __importStar(require("os"));
const path = __importStar(require("path"));
const literatureResolver_1 = require("../literatureResolver");
const telluriumBridge_1 = require("../../engine/telluriumBridge");
const PYTHON = (0, telluriumBridge_1.resolvePythonExecutable)(telluriumBridge_1.REPO_ROOT);
function pythonIsAvailable() {
    try {
        (0, child_process_1.execFileSync)(PYTHON, ['-c', 'pass'], { stdio: 'pipe' });
        return true;
    }
    catch {
        return false;
    }
}
const PYTHON_AVAILABLE = pythonIsAvailable();
if (!PYTHON_AVAILABLE) {
    console.warn('\n[literatureResolver.test] python3 unavailable; subprocess tests are ' +
        'SKIPPED, not passing.\n');
}
const describeSubprocess = PYTHON_AVAILABLE ? describe : describe.skip;
let stubDirectory;
const originalRunner = process.env['TERRIUM_LITERATURE_RUNNER'];
/** Write a stub runner that prints `payload` and exits with `exitCode`. */
function useStubRunner(payload, exitCode = 0) {
    const script = path.join(stubDirectory, `stub_${Date.now()}_${Math.random()}.py`);
    fs.writeFileSync(script, 'import sys\n' +
        'sys.stdin.read()\n' +
        `sys.stdout.write(${JSON.stringify(payload)})\n` +
        `sys.exit(${exitCode})\n`, 'utf-8');
    process.env['TERRIUM_LITERATURE_RUNNER'] = script;
}
beforeAll(() => {
    stubDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'terrium-resolver-'));
});
afterAll(() => {
    fs.rmSync(stubDirectory, { recursive: true, force: true });
    if (originalRunner === undefined) {
        delete process.env['TERRIUM_LITERATURE_RUNNER'];
    }
    else {
        process.env['TERRIUM_LITERATURE_RUNNER'] = originalRunner;
    }
});
const QUERY = {
    enzymeName: 'lactate dehydrogenase',
    substrate: 'pyruvate',
    organism: 'Homo sapiens',
    ecNumber: '1.1.1.27'
};
describe('refusing to search for nothing', () => {
    it('throws when neither ecNumber nor enzymeName is given', async () => {
        await expect((0, literatureResolver_1.resolveKinetic)({ substrate: 'pyruvate', organism: 'Homo sapiens' })).rejects.toThrow(literatureResolver_1.ResolverUnavailableError);
    });
});
describeSubprocess('reading the runner', () => {
    it('returns the value AND the unit the source reported', async () => {
        useStubRunner(JSON.stringify({
            ok: true,
            found: true,
            km: 2.5,
            unit: 'mM',
            organism: 'Homo sapiens',
            source: 'brenda_exact',
            citation: { source: 'BRENDA', reference_id: '12345' },
            logs: []
        }));
        const result = await (0, literatureResolver_1.resolveKinetic)(QUERY);
        expect(result.found).toBe(true);
        if (!result.found)
            return;
        expect(result.value).toBe(2.5);
        // The unit travels WITH the value, from the same source. This is the
        // whole reason to resolve rather than assume: `getDefaultUnit` used to
        // label values from a table keyed on the parameter's name, so the
        // label always agreed with the assumption and never with the data.
        expect(result.unit).toBe('mM');
        expect(result.crossSpecies).toBe(false);
    });
    it('reads the value from the key matching the quantity', async () => {
        // A Ki is emitted under "ki", not "km". Reading the wrong key would let
        // a Ki be used as a Km -- the provenance-mixing ADR 0008 forbids.
        useStubRunner(JSON.stringify({
            ok: true,
            found: true,
            ki: 0.04,
            km: 999, // must be ignored for a ki query
            unit: 'mM',
            organism: 'Homo sapiens',
            source: 'brenda_exact',
            citation: null,
            logs: []
        }));
        const result = await (0, literatureResolver_1.resolveKinetic)({ ...QUERY, quantity: 'ki' });
        expect(result.found).toBe(true);
        if (!result.found)
            return;
        expect(result.value).toBe(0.04);
        expect(result.quantity).toBe('ki');
    });
    it('flags a cross-species match instead of presenting it as exact', async () => {
        useStubRunner(JSON.stringify({
            ok: true,
            found: true,
            km: 1.1,
            unit: 'mM',
            organism: 'Oryctolagus cuniculus',
            source: 'brenda_cross_species',
            citation: { source: 'BRENDA', reference_id: '999' },
            logs: []
        }));
        const result = await (0, literatureResolver_1.resolveKinetic)(QUERY);
        expect(result.found).toBe(true);
        if (!result.found)
            return;
        // Real and citable, but measured in a different organism than asked
        // about. The caller must be able to see that.
        expect(result.crossSpecies).toBe(true);
        expect(result.organism).toBe('Oryctolagus cuniculus');
    });
    it('reports found:false as an answer, not an error', async () => {
        useStubRunner(JSON.stringify({ ok: true, found: false, logs: ['BRENDA exact: none'] }));
        const result = await (0, literatureResolver_1.resolveKinetic)(QUERY);
        expect(result.found).toBe(false);
        expect(result.logs).toContain('BRENDA exact: none');
    });
    it('refuses a value that arrives without a unit', async () => {
        // A kinetic constant without its unit is not a measurement: Km in mM
        // and Km in uM differ by 1000x. This tree has been bitten twice by
        // assumed units, so an unlabelled number is rejected rather than
        // guessed at.
        useStubRunner(JSON.stringify({
            ok: true,
            found: true,
            km: 2.5,
            organism: 'Homo sapiens',
            source: 'brenda_exact',
            logs: []
        }));
        await expect((0, literatureResolver_1.resolveKinetic)(QUERY)).rejects.toThrow(/no unit/i);
    });
    it('surfaces the runner\'s structured error even when it exits non-zero', async () => {
        // The regression. science_agent_runner.py prints
        // {"ok": false, "error": "403 Forbidden"} AND exits 1. Treating a
        // non-zero exit as fatal before parsing stdout replaced that precise
        // cause with "exited with code 1".
        useStubRunner(JSON.stringify({ ok: false, error: '403 Forbidden' }), 1);
        await expect((0, literatureResolver_1.resolveKinetic)(QUERY)).rejects.toThrow('403 Forbidden');
    });
    it('returns the Python-computed bridged Vmax for kcat + enzymeConc', async () => {
        // Vmax = kcat * [E]0 is computed by the runner using the same
        // Tellurium.core.validation.vmax_from_kcat the engine uses. This side
        // must read it, not recompute it -- a second copy of the arithmetic
        // would also be a second copy of the [E]0/Km flag threshold, free to
        // drift.
        useStubRunner(JSON.stringify({
            ok: true,
            found: true,
            kcat: 6500,
            unit: '1/s',
            vmax: 6.5,
            vmaxValidation: { ok: true, flagged: true, reason: '[E]0 is 0.0111x Km' },
            organism: 'Homo sapiens',
            source: 'brenda_exact',
            citation: { source: 'BRENDA', reference_id: '649716' },
            logs: []
        }));
        const result = await (0, literatureResolver_1.resolveKinetic)({
            ...QUERY,
            quantity: 'kcat',
            enzymeConc: 0.001
        });
        expect(result.found).toBe(true);
        if (!result.found)
            return;
        expect(result.value).toBe(6500);
        expect(result.bridgedVmax).toBe(6.5);
        expect(result.vmaxValidation?.flagged).toBe(true);
    });
    it('carries no bridged Vmax when no enzyme concentration was supplied', async () => {
        // ADR 0012/0013/0019: [E]0 is a caller input BRENDA cannot supply. A
        // kcat without it stays a citable number that no simulation can use --
        // the honest outcome, rather than a guessed enzyme concentration.
        useStubRunner(JSON.stringify({
            ok: true,
            found: true,
            kcat: 6500,
            unit: '1/s',
            organism: 'Homo sapiens',
            source: 'brenda_exact',
            citation: null,
            logs: []
        }));
        const result = await (0, literatureResolver_1.resolveKinetic)({ ...QUERY, quantity: 'kcat' });
        expect(result.found).toBe(true);
        if (!result.found)
            return;
        expect(result.bridgedVmax).toBeUndefined();
    });
    it('throws ResolverUnavailableError when the runner emits nothing', async () => {
        useStubRunner('', 1);
        await expect((0, literatureResolver_1.resolveKinetic)(QUERY)).rejects.toThrow(literatureResolver_1.ResolverUnavailableError);
    });
    it('throws rather than guessing when the runner emits invalid JSON', async () => {
        useStubRunner('not json at all');
        await expect((0, literatureResolver_1.resolveKinetic)(QUERY)).rejects.toThrow(/invalid JSON/i);
    });
    it('does not treat a missing script as "no literature"', async () => {
        // "We never asked" and "the registry says no" are different facts.
        process.env['TERRIUM_LITERATURE_RUNNER'] = path.join(stubDirectory, 'does-not-exist.py');
        await expect((0, literatureResolver_1.resolveKinetic)(QUERY)).rejects.toThrow(literatureResolver_1.ResolverUnavailableError);
    });
});
