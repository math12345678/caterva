/**
 * A suggested command must never name an enzyme the user did not.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `simulate "acetylcholinesterase"` printed:
 *
 *     scientific simulate "michaelis menten" --resolve \
 *       --enzyme "lactate dehydrogenase" --substrate pyruvate \
 *       --organism "Homo sapiens" --s0 10mM --enzyme-conc 0.001mM
 *
 * A complete, copy-pasteable command for a **different enzyme**. A student
 * who runs it gets LDH results while believing they asked about
 * acetylcholinesterase — a real BRENDA citation attached to a system they
 * never named, which this repository calls worse than no provenance.
 *
 * It is worse than a generic example precisely because it looks tailored.
 * A template with `<enzyme>` in it is obviously a template; a specific
 * enzyme name reads as an answer.
 *
 * This is the hardcoded-LDH defect for the fourth time. ADR 0059 found it in
 * `literature`, `validate` and `simulate`, each fetching lactate
 * dehydrogenase regardless of the query. `suggestResolveCommand.ts` was
 * written to do this properly — and one branch beside it still held the
 * literal.
 *
 * WHAT IS ASSERTED
 * ----------------
 * The class, not the instance: for a query naming enzyme X, no *other*
 * enzyme name may appear anywhere in the output. That catches the next
 * hardcoded example too, whichever enzyme someone reaches for.
 */
import { execFileSync } from 'child_process';
import * as path from 'path';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const CLI = path.join(REPO_ROOT, 'src', 'cli', 'scientificCLI.ts');
const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');

function runCli(args: string[]): string {
  try {
    return execFileSync(TS_NODE, [CLI, ...args], {
      cwd: REPO_ROOT,
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 120_000,
    });
  } catch (err) {
    const e = err as { stdout?: string; status?: number; signal?: string };
    if (e.status === undefined || e.status === null) {
      // A killed process has no exit status; coercing it would let an
      // environment failure impersonate a result.
      throw new Error(`CLI killed, not a real exit: signal=${e.signal}`);
    }
    return e.stdout ?? '';
  }
}

const ANSI = /\x1b\[[0-9;]*m/g;

/** Enzymes that appear in this repository's examples and fixtures. */
const OTHER_ENZYMES = [
  'lactate dehydrogenase',
  'hexokinase',
  'acetylcholinesterase',
  'alcohol dehydrogenase',
];

jest.setTimeout(600_000);

describe('a suggestion names YOUR system or none', () => {
  it.each([
    ['acetylcholinesterase'],
    ['hexokinase'],
  ])('does not advertise a different enzyme when asked about %s', (asked) => {
    const out = runCli(['simulate', asked]).replace(ANSI, '').toLowerCase();

    for (const other of OTHER_ENZYMES) {
      if (other === asked) continue;
      expect(out).not.toContain(other);
    }
  });

  it('uses a placeholder when the system cannot be read from the query', () => {
    // The honest fallback. A slot the reader must fill is never the wrong
    // enzyme; a filled-in name sometimes is.
    const out = runCli(['simulate', 'acetylcholinesterase']).replace(ANSI, '');
    expect(out).toContain('--enzyme "<enzyme>"');
    expect(out).toMatch(/replace the three names/i);
  });

  it('uses the real system when the query does name one', () => {
    // The other half — the guard against overcorrecting. Replacing
    // everything with placeholders would satisfy the tests above while
    // deleting `suggestResolveCommand`'s whole purpose.
    const out = runCli([
      'simulate',
      'michaelis menten of acetylcholinesterase on acetylcholine in Homo sapiens',
    ]).replace(ANSI, '');

    expect(out).toContain('--enzyme "acetylcholinesterase"');
    expect(out).toContain('--substrate "acetylcholine"');
    expect(out).not.toContain('<enzyme>');
  });
});
