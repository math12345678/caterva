/**
 * A suggested command must not throw away what the user already typed.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `formatResolveCommand` appended a fixed tail — `--s0 10mM --enzyme-conc
 * 0.001mM` — regardless of the command line it was suggesting a replacement
 * for. Measured:
 *
 *   $ simulate "michaelis menten of lactate dehydrogenase on pyruvate
 *               in Homo sapiens" --s0 10mM --vmax 1.2mM/s
 *   -> suggests: ... --s0 10mM --enzyme-conc 0.001mM
 *
 * The user's `--vmax 1.2mM/s` is gone, replaced by an `--enzyme-conc`
 * intended to DERIVE Vmax from kcat x [E]0 — and the suggested command then
 * exits 2, because the kcat it now depends on is not there.
 *
 * So the guidance took a user whose own flags were nearly sufficient and
 * handed them a command that fails, having discarded the value that would
 * have worked. Not merely unhelpful: a regression on their own input.
 *
 * `--vmax` and `--enzyme-conc` are ALTERNATIVES — give Vmax outright, or give
 * [E]0 so it can be bridged from kcat. Offering both is what made it wrong.
 *
 * These are unit tests against `formatResolveCommand` rather than CLI spawns.
 * The end-to-end property (the suggested command runs) is covered by
 * `refusalTellsYouWhatToDo.test.ts` for the refusal path; this file pins the
 * construction itself, which is where the defect lived, and runs in
 * milliseconds instead of minutes.
 */
import { formatResolveCommand, type ParsedSystem } from '../suggestResolveCommand';

const SYSTEM: ParsedSystem = {
  enzyme: 'lactate dehydrogenase',
  substrate: 'pyruvate',
  organism: 'Homo sapiens',
};

describe('the suggestion carries the flags you already gave', () => {
  it('keeps a supplied --vmax instead of replacing it', () => {
    const out = formatResolveCommand(SYSTEM, { s0: '10mM', vmax: '1.2mM/s' });

    expect(out).toContain('--vmax 1.2mM/s');
    // The exact swap that broke it: Vmax supplied, and the suggestion
    // offering a way to derive Vmax instead.
    expect(out).not.toContain('--enzyme-conc');
  });

  it('keeps a supplied --s0 rather than substituting the example', () => {
    const out = formatResolveCommand(SYSTEM, { s0: '250uM' });
    expect(out).toContain('--s0 250uM');
    expect(out).not.toContain('--s0 10mM');
  });

  it('offers --enzyme-conc only when Vmax was NOT supplied', () => {
    // The other half. Always dropping `--enzyme-conc` would satisfy the
    // first test while removing the kcat bridge from the one case that
    // needs it — ADR 0019's whole path.
    const out = formatResolveCommand(SYSTEM, { s0: '10mM' });
    expect(out).toContain('--enzyme-conc');
    expect(out).not.toContain('--vmax');
  });

  it('carries through flags it knows nothing about', () => {
    // km, ki, i0 and anything added later. A whitelist would silently drop
    // the next parameter someone introduces, which is this defect again in
    // slow motion.
    const out = formatResolveCommand(SYSTEM, {
      s0: '10mM', vmax: '1.2mM/s', ki: '5mM', i0: '1mM',
    });
    expect(out).toContain('--ki 5mM');
    expect(out).toContain('--i0 1mM');
  });

  it('is stable across runs', () => {
    // Object key order must not change the suggestion. A command that
    // differs between two identical runs is one a student cannot diff
    // against what they typed.
    const a = formatResolveCommand(SYSTEM, { ki: '5mM', s0: '10mM', i0: '1mM' });
    const b = formatResolveCommand(SYSTEM, { i0: '1mM', ki: '5mM', s0: '10mM' });
    expect(a).toBe(b);
  });

  it('still names the system, and still works with no flags at all', () => {
    // The original behaviour has to survive: called with nothing supplied,
    // it is the worked example it always was.
    const out = formatResolveCommand(SYSTEM);
    expect(out).toContain('--enzyme "lactate dehydrogenase"');
    expect(out).toContain('--substrate "pyruvate"');
    expect(out).toContain('--organism "Homo sapiens"');
    expect(out).toContain('--s0 10mM');
    expect(out).toContain('--enzyme-conc 0.001mM');
  });
});
