/**
 * `scientific catalog <ec>` — the command that means the first query need
 * not be a guess.
 *
 * WHY IT SPAWNS THE REAL CLI
 * --------------------------
 * ADR 0107: `export_citations.py` sat dead on its import line in HEAD
 * while every test passed, because the tests imported the library directly
 * and pytest had already put the repository root on `sys.path`. A command
 * is only real if invoking it the way a person does produces the output.
 *
 * These do not reach BRENDA. The network path is exercised by the resolver
 * suites against fixtures; what is asserted here is that the command
 * exists, is discoverable, and fails in a way a reader can act on — which
 * is the half that a mocked test cannot see.
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

describe('scientific catalog', () => {
  it('is listed in help, so a student can find it', () => {
    // A capability nobody can find is not a capability — and this one
    // exists specifically to be the first thing someone runs.
    const { out } = run(['help']);
    expect(out).toContain('catalog <ec-number>');
    expect(out).toContain('1.1.1.27');
  }, 120_000);

  it('explains what to type when given no EC number', () => {
    const { status, out } = run(['catalog']);
    expect(status).toBe(1);
    expect(out).toContain('scientific catalog 1.1.1.27');
    // The reason, not just the syntax: a reader who knows WHY it helps
    // will use it again.
    expect(out).toMatch(/labels instead of guessing/);
  }, 120_000);

  it('reports a page it could not read as data, not as a crash', () => {
    // An EC number that is syntactically fine and has no BRENDA page.
    // Whatever comes back — a 403, a 404, an empty page — the command
    // must say so in a sentence. A discovery command that exits with a
    // stack trace has told the reader less than one that says the page
    // could not be read.
    const { out } = run(['catalog', '9.9.9.9']);
    expect(out).not.toContain('Traceback');
    expect(out).not.toMatch(/Error: connect|ECONNREFUSED/);
  }, 120_000);
});
