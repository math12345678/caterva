"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Regressions for a reproducibility verifier that could not fail.
 *
 * None of these cases were covered by `reproducibilityEngine.test.ts`, and
 * none of that file's tests had ever been executed: this tree shipped with
 * a `package.json` advertising `"type-check": "tsc --noEmit"` and
 * `"verify-all": "npm run type-check && npm run lint && npm test"` but no
 * `tsconfig.json`, so `tsc` found no inputs, printed its own help text,
 * exited 1, and `verify-all` died before ever reaching `npm test`.
 *
 * Four compounding defects meant `ReproducibilityVerifier.verify` reported
 * "✓ FULLY REPRODUCIBLE (max error: 0.00e+0)" for every input it was ever
 * given:
 *
 *   1. `compareOutputs(originalRecord.output, reproducer)` passed the
 *      reproducer FUNCTION where the reproduced OUTPUT belonged.
 *   2. `const repro = reproduced?.trajectory?.[i]?.value || orig` then
 *      substituted the ORIGINAL value for every missing point -- so the
 *      comparison was `orig` against `orig` and the error was exactly 0.
 *   3. `passed` reduced to `inputHashMatch`, which was itself always false
 *      for any record with real parameters, because `createRecord` hashed
 *      the raw `parameters` while storing `serializeParameters(parameters)`.
 *   4. `outputHashMatch` hashed `JSON.stringify(reproducer)` -- `undefined`
 *      for a function -- and was then left out of `passed` entirely.
 *
 * Every test below fails against the original implementation. That is the
 * point of them: a verifier whose verdict does not depend on its input is
 * not a weak check, it is an inverted one, and it certifies exactly the
 * irreproducible results it exists to catch.
 */
const reproducibilityEngine_1 = require("../reproducibilityEngine");
/** A three-point decay, with parameters -- the case that used to make
 *  `inputHashMatch` permanently false. */
function makeRecord(trajectory = [
    { time: 0, value: 100 },
    { time: 1, value: 95 },
    { time: 2, value: 90 }
]) {
    return reproducibilityEngine_1.ExecutionRecorder.createRecord('job_regression', 'decay query', { km: { value: 5.2, unit: 'mM', source: 'BRENDA', confidence: 0.9 } }, { temperature: 37, pH: 7.4 }, {
        trajectory,
        metrics: trajectory.length > 0
            ? { finalValue: trajectory[trajectory.length - 1].value }
            : {}
    });
}
describe('the input hash covers what is actually stored', () => {
    it('holds when serialization is NOT an identity on the parameters', () => {
        // This is the case that actually exercises defect 3, and the reason
        // this test exists separately from the one below.
        //
        // `serializeParameters` projects each parameter onto exactly
        // `{ value, unit, source, confidence }`. A fixture whose parameters
        // already have precisely that shape serializes to itself, so hashing
        // the raw argument and hashing the stored form produce the SAME digest
        // and the defect is invisible. The first version of this suite used
        // such a fixture and passed cleanly against the bug -- mutation
        // testing is what surfaced that.
        //
        // Real resolved parameters carry provenance the projection drops, so
        // the fixture here carries an extra field and omits `confidence` (which
        // the projection defaults to 1.0). Both make serialization lossy, which
        // is the condition under which the two hashes diverge.
        const record = reproducibilityEngine_1.ExecutionRecorder.createRecord('job_lossy', 'decay query', {
            km: {
                value: 5.2,
                unit: 'mM',
                source: 'BRENDA',
                literatureDoi: '10.1093/nar/gkaa1025', // dropped by the projection
                organism: 'Homo sapiens' // dropped by the projection
            },
            vmax: { value: 12.4, unit: 'umol/min/mg', source: 'BRENDA' } // no confidence
        }, { temperature: 37, pH: 7.4 }, { trajectory: [{ time: 0, value: 100 }], metrics: {} });
        const { intact, issues } = reproducibilityEngine_1.DataIntegrityChecker.verify(record);
        expect(issues).toEqual([]);
        expect(intact).toBe(true);
    });
    it('holds when the output carries fields the stored projection drops', () => {
        // The output-side twin of the test above, and it needs its own lossy
        // fixture for the same reason: `record.output` stores only
        // `{ trajectory, metrics }`, so an output that already has exactly
        // those two keys hashes identically either way and hides the defect.
        //
        // This is not a contrived shape. `ScientificPipeline.runSimulation`
        // returns `{ trajectory, finalValue, computedMetrics }` -- three keys,
        // two of which the projection discards -- so every record the real
        // pipeline produced had an output hash that could never be recomputed,
        // and DataIntegrityChecker reported "Output data corrupted" for all of
        // them.
        const record = reproducibilityEngine_1.ExecutionRecorder.createRecord('job_lossy_output', 'decay query', {}, {}, {
            trajectory: [{ time: 0, value: 100 }],
            metrics: { finalValue: 100 },
            finalValue: 100, // dropped by the projection
            computedMetrics: { r2: 0.99 }, // dropped by the projection
            solverSteps: 412 // dropped by the projection
        });
        const { intact, issues } = reproducibilityEngine_1.DataIntegrityChecker.verify(record);
        expect(issues).toEqual([]);
        expect(intact).toBe(true);
    });
    it('re-hashing a record\'s own inputs reproduces its stored inputHash', () => {
        // Defect 3. With parameters present, the stored hash was computed over
        // the raw argument and verification recomputed it over the serialized
        // form, so this equality never held and `passed` was pinned to false.
        const record = makeRecord();
        const { intact, issues } = reproducibilityEngine_1.DataIntegrityChecker.verify(record);
        expect(issues).toEqual([]);
        expect(intact).toBe(true);
    });
    it('a freshly created record is intact, not "corrupted"', () => {
        // The empty `executionTrace` every new record carries was reported as
        // an integrity issue, so `checkIntegrity` returned intact=false for
        // healthy data and the CLI (`process.exit(result.intact ? 0 : 1)`)
        // exited nonzero on it.
        const { intact, warnings } = reproducibilityEngine_1.DataIntegrityChecker.verify(makeRecord());
        expect(intact).toBe(true);
        expect(warnings.length).toBeGreaterThan(0);
        expect(warnings.join(' ')).toContain('not data corruption');
    });
});
describe('an irreproducible run is reported as irreproducible', () => {
    it('fails when the reproduction differs far beyond solver tolerance', async () => {
        // The headline regression. Pre-fix this returned passed=true with
        // maxRelativeError=0 no matter how wrong the reproduction was.
        const record = makeRecord();
        const wildlyDifferent = async () => ({
            trajectory: [
                { time: 0, value: 100 },
                { time: 1, value: 5 }, // 95 -> 5
                { time: 2, value: 1 }
            ],
            metrics: {}
        });
        const result = await reproducibilityEngine_1.ReproducibilityVerifier.verify(record, wildlyDifferent);
        expect(result.verification.passed).toBe(false);
        expect(result.verification.maxRelativeError).toBeGreaterThan(0.9);
        expect(result.summary).toContain('NOT REPRODUCIBLE');
        expect(result.differences?.conclusion).toContain('DIFFER');
        // The causes must not blame floating point for a 95% disagreement.
        expect(result.differences?.possibleCauses ?? []).not.toContain('Different floating-point implementations');
    });
    it('fails when the reproduction omits points instead of scoring them as matches', async () => {
        // Defect 2: `|| orig` substituted the expected value for a missing one.
        const record = makeRecord();
        const truncated = async () => ({
            trajectory: [{ time: 0, value: 100 }], // 1 point, not 3
            metrics: {}
        });
        const result = await reproducibilityEngine_1.ReproducibilityVerifier.verify(record, truncated);
        expect(result.verification.passed).toBe(false);
    });
    it('fails when the reproduction returns nothing at all', async () => {
        const result = await reproducibilityEngine_1.ReproducibilityVerifier.verify(makeRecord(), async () => ({}));
        expect(result.verification.passed).toBe(false);
    });
    it('fails when a reproduced point is NaN rather than treating it as a match', async () => {
        const record = makeRecord();
        const withNaN = async () => ({
            trajectory: [
                { time: 0, value: 100 },
                { time: 1, value: NaN },
                { time: 2, value: 90 }
            ],
            metrics: {}
        });
        const result = await reproducibilityEngine_1.ReproducibilityVerifier.verify(record, withNaN);
        expect(result.verification.passed).toBe(false);
    });
    it('does not certify a reproduction of an empty original', async () => {
        // An empty trajectory returned maxRelativeError 0, which sailed past
        // the tolerance test -- a perfect score on no evidence.
        const record = makeRecord([]);
        const result = await reproducibilityEngine_1.ReproducibilityVerifier.verify(record, async () => ({ trajectory: [], metrics: {} }));
        expect(result.verification.passed).toBe(false);
    });
    it('catches a large disagreement where the original value is exactly zero', async () => {
        // The old loop `continue`d on orig === 0, so a reproduction returning
        // 500 where the original was 0 contributed nothing to the error.
        const record = makeRecord([
            { time: 0, value: 100 },
            { time: 1, value: 0 }
        ]);
        const nonzeroAtZero = async () => ({
            trajectory: [
                { time: 0, value: 100 },
                { time: 1, value: 500 }
            ],
            metrics: {}
        });
        const result = await reproducibilityEngine_1.ReproducibilityVerifier.verify(record, nonzeroAtZero);
        expect(result.verification.passed).toBe(false);
    });
});
describe('a genuine reproduction still passes', () => {
    it('accepts a bit-identical reproduction', async () => {
        const trajectory = [
            { time: 0, value: 100 },
            { time: 1, value: 95 },
            { time: 2, value: 90 }
        ];
        const record = makeRecord(trajectory);
        const identical = async () => ({
            trajectory: trajectory.map(p => ({ ...p })),
            metrics: { finalValue: 90 }
        });
        const result = await reproducibilityEngine_1.ReproducibilityVerifier.verify(record, identical);
        expect(result.verification.passed).toBe(true);
        expect(result.verification.inputHashMatch).toBe(true);
        expect(result.verification.maxRelativeError).toBe(0);
        expect(result.verification.outputsIdentical).toBe(true);
        expect(result.summary).toContain('REPRODUCIBLE');
        expect(result.summary).not.toContain('NOT REPRODUCIBLE');
    });
    it('accepts a difference inside the solver\'s declared tolerance', async () => {
        // Tolerance is `atol + rtol*|original|` read from the record's own
        // solver block (atol 1e-8, rtol 1e-6), not a constant in the verifier.
        // At value 100 that allows 1e-8 + 1e-4 = 1.0001e-4.
        const record = makeRecord([{ time: 0, value: 100 }]);
        const withinTolerance = async () => ({
            trajectory: [{ time: 0, value: 100.0001 }], // 1e-4 absolute
            metrics: {}
        });
        const result = await reproducibilityEngine_1.ReproducibilityVerifier.verify(record, withinTolerance);
        expect(result.verification.passed).toBe(true);
        // Unconditional, unlike the original test for this behaviour, which
        // wrapped its only assertion in `if (result.differences)` and so
        // passed silently whenever `differences` was undefined.
        expect(result.differences).toBeDefined();
        expect(result.differences.possibleCauses).toContain('Different floating-point implementations');
    });
    it('rejects a difference just outside the declared tolerance', async () => {
        // Proof the boundary is real and not merely permissive: 2e-4 absolute
        // at value 100 exceeds the 1.0001e-4 allowance.
        const record = makeRecord([{ time: 0, value: 100 }]);
        const outside = async () => ({
            trajectory: [{ time: 0, value: 100.0002 }],
            metrics: {}
        });
        const result = await reproducibilityEngine_1.ReproducibilityVerifier.verify(record, outside);
        expect(result.verification.passed).toBe(false);
    });
    it('holds a tighter-tolerance run to a tighter standard', async () => {
        // The threshold is read from the record, so tightening the solver
        // config must tighten the verdict. A constant in the verifier could
        // not do this.
        const loose = makeRecord([{ time: 0, value: 100 }]);
        const tight = makeRecord([{ time: 0, value: 100 }]);
        tight.solver.relativeTolerance = 1e-12;
        tight.solver.absoluteTolerance = 1e-14;
        const reproducer = async () => ({
            trajectory: [{ time: 0, value: 100.00005 }], // 5e-5 absolute
            metrics: {}
        });
        expect((await reproducibilityEngine_1.ReproducibilityVerifier.verify(loose, reproducer)).verification.passed).toBe(true);
        expect((await reproducibilityEngine_1.ReproducibilityVerifier.verify(tight, reproducer)).verification.passed).toBe(false);
    });
});
