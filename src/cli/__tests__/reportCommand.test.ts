/**
 * `scientific report` — the command that produces something a student can
 * hand to a teacher.
 *
 * WHY IT SPAWNS THE REAL CLI
 * --------------------------
 * ADR 0107: `export_citations.py` sat dead on its import line in HEAD while
 * every test passed, because the tests imported the library directly and
 * pytest had already put the repository root on `sys.path`. The document
 * builder is covered by `Tests/test_lab_report.py`; what is asserted here
 * is that a person typing the command gets it.
 *
 * These do not reach BRENDA. The resolution path is covered against
 * fixtures elsewhere; what a network-free machine can still check is that
 * the command exists, is discoverable, and fails in a way a reader can act
 * on — the half a mocked test cannot see.
 */

import { spawnSync } from 'child_process';
import path from 'path';

const CLI = path.join(__dirname, '..', 'scientificCLI.ts');

function run(args: string[]): { status: number | null; out: string } {
  const proc = spawnSync('npx', ['ts-node', CLI, ...args], {
    cwd: path.join(__dirname, '..', '..', '..'),
    encoding: 'utf-8',
  });
  return { status: proc.status, out: `${proc.stdout ?? ''}${proc.stderr ?? ''}` };
}

describe('scientific report', () => {
  it('is listed in help, so a student can find it', () => {
    const { out } = run(['help']);
    expect(out).toContain('report --ec N --organism O --substrate S');
    // The distinguishing section is advertised, not buried.
    expect(out).toMatch(/what Terrium would not do/);
  }, 120_000);

  it('points at `catalog` when the request is incomplete', () => {
    // The two commands compose: catalog tells you the labels BRENDA uses,
    // report consumes them. A refusal that did not say so would leave a
    // student guessing the substrate string — the exact friction ADR 0124
    // was written about.
    const { status, out } = run(['report']);
    expect(status).toBe(1);
    expect(out).toContain('scientific catalog 1.1.1.27');
    expect(out).toContain('(S)-lactate');
  }, 120_000);

  it('does not write a file named after the next flag', () => {
    // `--out --json` used to be a real hazard for hand-rolled flag
    // parsing: the value after `--out` is a flag, not a path.
    const { out } = run(['report', '--ec', '1.1.1.27', '--out', '--json']);
    expect(out).not.toContain('Wrote --json');
  }, 120_000);
});
