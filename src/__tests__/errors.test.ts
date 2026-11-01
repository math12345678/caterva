/**
 * The message a user sees when a run fails.
 *
 * `ScientificPipeline.execute` signalled failure by throwing a plain object
 * carrying the real cause in `message`. Every consumer read it with the
 * standard idiom `error instanceof Error ? error.message : String(error)`,
 * which for a non-Error runs `String(obj)` and produces `"[object Object]"`.
 *
 * Measured on the real throw shape before the fix:
 *
 *     error recorded : "[object Object]"
 *     real message   : "Cannot simulate: km could not be resolved from literature"
 *
 * WHY THE EXISTING TESTS COULD NOT SEE IT
 * ---------------------------------------
 * The mocks in `batch-success-accounting.test.ts` and
 * `model-selection-excludes-failures.test.ts` — written one pass earlier —
 * throw `new Error('solver diverged')`. A real Error. The pipeline throws a
 * plain object.
 *
 * That is ADR 0056's lesson (a test can only be as honest as the
 * resemblance between its fixture and its producer) applied to the FAILURE
 * shape rather than the success shape. The success shapes had been
 * transcribed from the pipeline's `return` statement; the error shapes were
 * invented, and invented an easier problem.
 */
import { SimulationError, describeError } from '../errors';

/** Exactly what `ScientificPipeline.execute` used to throw. */
const LEGACY_THROWN_OBJECT = {
  jobId: 'job_1',
  error: 'SIMULATION_ERROR',
  message: 'Cannot simulate: km could not be resolved from literature',
  executionTimeMs: 42,
};

describe('describeError recovers the cause the old idiom discarded', () => {
  it('reads the message off a thrown plain object', () => {
    // THE DEFECT. `String(LEGACY_THROWN_OBJECT)` is "[object Object]".
    expect(describeError(LEGACY_THROWN_OBJECT)).toBe(
      'Cannot simulate: km could not be resolved from literature',
    );
    expect(describeError(LEGACY_THROWN_OBJECT)).not.toBe('[object Object]');
  });

  it('reads the message off a real Error', () => {
    expect(describeError(new Error('solver diverged'))).toBe('solver diverged');
  });

  it('passes a thrown string through', () => {
    expect(describeError('something went wrong')).toBe('something went wrong');
  });

  it('falls back to a code when an object has one but no message', () => {
    expect(describeError({ error: 'SIMULATION_ERROR' })).toBe(
      'SIMULATION_ERROR (no message was recorded)',
    );
  });

  it('never returns an empty string', () => {
    // An empty `error` field reads as "no error" — a failure rendering as
    // success, which is the inversion this codebase treats as its core
    // defect. Every one of these has genuinely nothing to say, and each
    // must still say something.
    for (const value of [undefined, null, '', '   ', {}, new Error('')]) {
      expect(describeError(value).trim()).not.toBe('');
    }
  });

  it('does not invent a cause it does not have', () => {
    // The other direction. An object with no message and no code gets
    // "[object Object]", and that is correct: there is nothing better to
    // say, and a friendlier sentence would claim knowledge of a cause
    // nobody recorded.
    expect(describeError({ a: 1 })).toBe('[object Object]');
  });
});

describe('SimulationError survives being caught', () => {
  it('is an Error, so every instanceof check in the codebase works', () => {
    const e = new SimulationError('km could not be resolved', { jobId: 'j1' });
    expect(e).toBeInstanceOf(Error);
    expect(e).toBeInstanceOf(SimulationError);
  });

  it('gives the real message to the idiom that used to fail', () => {
    // The exact expression that produced "[object Object]" across the
    // codebase. It now works without any change at the call site — which is
    // the point of fixing the throw rather than only the readers.
    const e: unknown = new SimulationError('km could not be resolved');
    const viaOldIdiom = e instanceof Error ? e.message : String(e);
    expect(viaOldIdiom).toBe('km could not be resolved');
  });

  it('keeps the fields the object shape carried', () => {
    const e = new SimulationError('boom', { jobId: 'j1', executionTimeMs: 42 });
    expect(e.code).toBe('SIMULATION_ERROR');
    expect(e.jobId).toBe('j1');
    expect(e.executionTimeMs).toBe(42);
  });
});
