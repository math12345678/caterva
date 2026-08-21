/**
 * `report` must read a number the same way the rest of the CLI does.
 *
 * WHAT WAS MEASURED, BEFORE THIS EXISTED
 * --------------------------------------
 * The CLI's help teaches `--s0 10mM` for `simulate`, so that is what a
 * student types everywhere. `report` built its payload with `Number()`:
 *
 *     Number('10mM')                     -> NaN
 *     JSON.stringify({ s0: NaN })        -> {"s0":null}
 *
 * and `report_lab.py` skips supplied values that are None. So the number
 * disappeared and the document came back with:
 *
 *     the simulation was not run: s0 is missing — yours to choose
 *
 * Verified end to end through the real script before the fix. **The student
 * did choose it.** A refusal that blames the user for the tool's own data
 * loss is worse than a crash: it looks actionable and it is wrong.
 *
 * The second defect is quieter. A bare `--vmax 0.25` was used as mM/s
 * because the engine's other inputs are mM, while `parseQuantity` — every
 * other command's reader — assumes uM/min for a bare vmax. The same three
 * characters, 60,000x apart, decided by which command read them. A wrong
 * Vmax does not fail; it produces a plausible trajectory in a document whose
 * purpose is being handed to a teacher.
 */
import { parseReportQuantities } from '../reportQuantities';

const by = (name: string, out: ReturnType<typeof parseReportQuantities>) =>
  out.supplied.find((s) => s.name === name);

describe('report reads quantities the way the rest of the CLI does', () => {
  it('accepts the united syntax the help text teaches', () => {
    // The regression. This is the exact string a student carries over from
    // the `simulate` examples.
    const out = parseReportQuantities({ s0: '10mM' });

    expect(out.problems).toEqual([]);
    expect(by('s0', out)?.value).toBe(10);
  });

  it('converts to the engine unit rather than assuming the typed one', () => {
    // 10000 uM is 10 mM. Passing 10000 through as "mM" would be a 1000x
    // error that no test asserting `value === 10000` would notice.
    const out = parseReportQuantities({ s0: '10000uM' });

    expect(by('s0', out)?.value).toBeCloseTo(10, 10);
    expect(by('s0', out)?.unit).toBe('mM');
  });

  it('reads a bare vmax in the same unit every other command reads it', () => {
    // uM/min -> mM/s is /1000 then /60. This is the 60,000x defect, pinned
    // as a number rather than as a policy.
    const out = parseReportQuantities({ vmax: '0.25' });

    expect(by('vmax', out)?.value).toBeCloseTo(0.25 / 1000 / 60, 12);
    expect(by('vmax', out)?.unit).toBe('mM/s');
  });

  it('uses a declared vmax unit instead of the assumed one', () => {
    const out = parseReportQuantities({ vmax: '0.25mM/s' });
    expect(by('vmax', out)?.value).toBeCloseTo(0.25, 12);
  });

  // -------------------------------------------------------------------
  // An assumed unit is not a declared one, and the document must say so
  // -------------------------------------------------------------------

  it('records that a unit was assumed when the user gave none', () => {
    const out = parseReportQuantities({ s0: '10', vmax: '0.25' });

    expect(by('s0', out)?.assumedUnit).toBe('mM');
    expect(by('vmax', out)?.assumedUnit).toBe('uM/min');
  });

  it('records nothing assumed when the user declared the unit', () => {
    // The guard against overcorrecting: marking everything "assumed" would
    // satisfy the test above while making the annotation meaningless.
    const out = parseReportQuantities({ s0: '10mM', vmax: '0.25mM/s' });

    expect(by('s0', out)?.assumedUnit).toBeUndefined();
    expect(by('vmax', out)?.assumedUnit).toBeUndefined();
  });

  // -------------------------------------------------------------------
  // Unreadable input is a stated problem, never a silent null
  // -------------------------------------------------------------------

  it('reports an unreadable number instead of dropping it', () => {
    const out = parseReportQuantities({ s0: 'ten' });

    expect(out.supplied).toEqual([]);
    expect(out.problems).toHaveLength(1);
    expect(out.problems[0]).toContain('--s0');
  });

  it('reports every bad value, not just the first', () => {
    // Fixing one, re-running, and finding the next is how the third gets
    // left. Both are collected.
    const out = parseReportQuantities({ s0: 'ten', vmax: 'fast' });
    expect(out.problems).toHaveLength(2);
  });

  it('a comma decimal is explained rather than silently truncated', () => {
    // `Number('5,2')` is NaN; `parseFloat('5,2')` would be 5. Either way a
    // European student loses a number without being told.
    const out = parseReportQuantities({ s0: '5,2' });
    expect(out.problems).toHaveLength(1);
    expect(out.supplied).toEqual([]);
  });

  // -------------------------------------------------------------------
  // Absence is not zero
  // -------------------------------------------------------------------

  it('omits a flag the user did not pass', () => {
    const out = parseReportQuantities({ s0: '10mM' });

    expect(by('vmax', out)).toBeUndefined();
    expect(out.problems).toEqual([]);
  });

  it('treats an empty string as a value they typed, not as absence', () => {
    // `--s0` with nothing after it must not silently mean "no s0". It is a
    // mistake, and a mistake the tool can see is one it should name.
    const out = parseReportQuantities({ s0: '' });
    expect(out.problems).toHaveLength(1);
  });

  it('carries the basis through so the document can state it', () => {
    const out = parseReportQuantities({ s0: '10mM', 's0-basis': 'lab handout' });
    expect(by('s0', out)?.basis).toBe('lab handout');
  });
});
