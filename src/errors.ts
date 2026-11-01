/**
 * Errors that survive being caught.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `ScientificPipeline.execute` signalled failure by throwing a plain
 * object:
 *
 *     throw {
 *       jobId,
 *       error: 'SIMULATION_ERROR',
 *       message: error instanceof Error ? error.message : 'Unknown error',
 *       executionTimeMs: Date.now() - startTime
 *     };
 *
 * Note the care taken over `message`: the real cause is extracted and
 * preserved. Every consumer then read it with the standard idiom —
 *
 *     error instanceof Error ? error.message : String(error)
 *
 * — and a plain object is not an `Error`, so `String(obj)` ran instead and
 * produced **`"[object Object]"`**.
 *
 * That string was what a user saw. Measured on the real throw shape:
 *
 *     error recorded : "[object Object]"
 *     real message   : "Cannot simulate: km could not be resolved from literature"
 *
 * It reached the `error` field of `GET /api/jobs/:jobId`, the `errorMessage`
 * recorded in metrics, the `error` column of the batch and comparison CSVs,
 * and the CLI. A student whose run failed because a Km could not be
 * resolved — the single most common and most actionable failure this
 * project has — was told `[object Object]`.
 *
 * TWO FIXES, BECAUSE ONE IS NOT ENOUGH
 * ------------------------------------
 * `SimulationError` fixes the source: it is a real `Error`, so every
 * existing `instanceof Error` check works, including in code nobody has
 * written yet.
 *
 * `describeError` fixes the readers: it recovers a message from a
 * non-`Error` that carries one. That is deliberate defence in depth rather
 * than redundancy, because the next `throw { message }` will be written by
 * somebody who has not read this file — several already exist in
 * dependencies — and the failure mode is silent. `"[object Object]"` does
 * not throw, does not warn, and looks like a rendering bug rather than a
 * lost diagnosis.
 */

/** A simulation that could not be performed, with the reason intact. */
export class SimulationError extends Error {
  /** Kept for compatibility with the object shape this replaced. */
  readonly code = 'SIMULATION_ERROR';
  readonly jobId?: string;
  readonly executionTimeMs?: number;

  constructor(message: string, details: { jobId?: string; executionTimeMs?: number } = {}) {
    super(message);
    this.name = 'SimulationError';
    this.jobId = details.jobId;
    this.executionTimeMs = details.executionTimeMs;

    // Required for `instanceof` to work when the class is compiled to ES5,
    // which the build target permits. Without it `e instanceof
    // SimulationError` is false and this file would reintroduce, in a new
    // form, exactly the bug it exists to fix.
    Object.setPrototypeOf(this, SimulationError.prototype);
  }
}

/**
 * The most informative message available for a caught value.
 *
 * Order matters and each step is here for a reason:
 *
 *   1. `Error` — the ordinary case.
 *   2. an object with a string `message` — the case that produced
 *      `"[object Object]"`. Preferring it over `String(value)` is the
 *      entire point of this function.
 *   3. a string thrown directly.
 *   4. `String(value)` — last resort, and it will produce
 *      `"[object Object]"` for an object with no message. That is correct:
 *      there is genuinely nothing better to say, and inventing a friendlier
 *      sentence would claim knowledge of a cause nobody recorded.
 *
 * Never returns an empty string. An empty `error` field reads as "no
 * error", which is the inversion this codebase treats as the core defect —
 * a failure that renders as success.
 */
export function describeError(value: unknown): string {
  if (value instanceof Error && value.message) return value.message;

  if (typeof value === 'string' && value.trim() !== '') return value;

  if (value !== null && typeof value === 'object') {
    const message = (value as { message?: unknown }).message;
    if (typeof message === 'string' && message.trim() !== '') return message;

    // An object carrying a code but no message still says more than
    // "[object Object]".
    const code = (value as { error?: unknown; code?: unknown }).error
      ?? (value as { code?: unknown }).code;
    if (typeof code === 'string' && code.trim() !== '') {
      return `${code} (no message was recorded)`;
    }
  }

  const stringified = String(value);
  return stringified.trim() === '' ? 'An unknown error occurred (no details were recorded)' : stringified;
}
