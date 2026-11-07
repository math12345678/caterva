/**
 * The test suite must never write into the developer's real ~/.caterva.
 *
 * It did, for months: the CLI tests spawn the real binary, the binary keeps
 * run history and execution records under the home directory, and nothing
 * told it otherwise. One developer's `caterva history` ended up listing 57
 * fixture runs citing stub PMIDs (12345678, 999111) beside real work, and
 * `verify` would vouch for 91 fixture records. Every test passed throughout,
 * so the only symptom was in a file no test read.
 *
 * These checks look at RESOLVED paths, not at the real home directory: a
 * test that compared ~/.caterva before and after would itself depend on, and
 * race with, whatever the developer is doing there.
 */
import { execFileSync } from 'child_process';
import * as os from 'os';
import * as path from 'path';

import { historyPath } from '../execution/job-manager';
import { recordsDir } from '../reproducibility/reproducibilityEngine';

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const TS_NODE = path.join(REPO_ROOT, 'node_modules', '.bin', 'ts-node');

/** Every directory a user's real state could be under. */
function homes(): string[] {
  const out = [os.homedir()];
  // os.homedir() and $HOME can disagree inside jest (see recordsDir()), and
  // either one is somewhere a fixture must not land.
  if (process.env['HOME']) out.push(process.env['HOME']);
  return out.map((h) => path.resolve(h));
}

function underAHome(p: string): string | undefined {
  const resolved = path.resolve(p);
  return homes().find((h) => resolved === h || resolved.startsWith(h + path.sep));
}

describe('state written during tests stays out of the home directory', () => {
  it('both overrides are set for this test file', () => {
    expect(process.env['CATERVA_HISTORY_FILE']).toBeTruthy();
    expect(process.env['CATERVA_RECORDS_DIR']).toBeTruthy();
  });

  it('history and records resolve outside every home directory', () => {
    expect({ history: historyPath(), home: underAHome(historyPath()) }).toEqual({
      history: historyPath(),
      home: undefined,
    });
    expect({ records: recordsDir(), home: underAHome(recordsDir()) }).toEqual({
      records: recordsDir(),
      home: undefined,
    });
  });

  it('a child spawned WITHOUT an explicit env inherits the same scratch paths', () => {
    // Several CLI tests call execFileSync with no `env:`. Such a child reads
    // the worker's real process.env, not jest's per-file copy, so only a
    // variable set in globalSetup reaches it. Printing the env from a bare
    // child is what proves that path, not reading process.env here.
    const out = execFileSync(
      process.execPath,
      ['-e', 'process.stdout.write(JSON.stringify([process.env.CATERVA_HISTORY_FILE, process.env.CATERVA_RECORDS_DIR]))'],
      { encoding: 'utf-8' },
    );
    const [history, records] = JSON.parse(out) as [string | null, string | null];
    expect(history).toBe(process.env['CATERVA_HISTORY_FILE']);
    expect(records).toBe(process.env['CATERVA_RECORDS_DIR']);
  });

  it('the CLI, as the tests spawn it, resolves both paths outside the home directory', () => {
    // The functions the binary itself calls, in a ts-node child exactly like
    // the one cliEndToEnd.test.ts spawns -- so a later change that resolves
    // the path some other way in the CLI process is caught too.
    const script =
      "const j=require('./src/execution/job-manager');" +
      "const r=require('./src/reproducibility/reproducibilityEngine');" +
      'process.stdout.write(JSON.stringify([j.historyPath(), r.recordsDir()]));';
    const out = execFileSync(TS_NODE, ['-T', '-e', script], {
      cwd: REPO_ROOT,
      encoding: 'utf-8',
      timeout: 120_000,
    });
    const [history, records] = JSON.parse(out.trim().split('\n').pop() as string) as [string, string];
    expect({ history, home: underAHome(history) }).toEqual({ history, home: undefined });
    expect({ records, home: underAHome(records) }).toEqual({ records, home: undefined });
  });
});
