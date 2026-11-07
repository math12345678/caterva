/**
 * Keep every test run out of the developer's real ~/.caterva.
 *
 * WHY THIS EXISTS
 * ---------------
 * The CLI tests spawn the real binary with the test process's environment,
 * and nothing in that environment told the binary where to keep its state.
 * So every `simulate` a test ran appended to the user's own
 * ~/.caterva/history.json and wrote a record into ~/.caterva/records. By
 * 2026-11 one developer's history held 57 fixture runs (stub PubMed ids
 * 12345678, 999111, 1, 2; a BRENDA "ref 12345") listed by `caterva history`
 * beside their real work, and 91 fixture records `verify` would vouch for.
 * Nothing failed, which is why nobody saw it.
 *
 * jest's globalSetup runs in the parent process before any worker is forked,
 * so a variable set here is in the REAL process.env every worker -- and
 * every child a test spawns, with or without an explicit `env:` -- inherits.
 * Setting it from a per-file setup alone would not be enough: jest gives
 * each test file a copy of process.env, and a child spawned without `env:`
 * reads the real one.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

export const STATE_DIR_VAR = 'CATERVA_TEST_STATE_DIR';
export const HISTORY_VAR = 'CATERVA_HISTORY_FILE';
export const RECORDS_VAR = 'CATERVA_RECORDS_DIR';

/**
 * Point history and records at a fresh scratch directory.
 *
 * Unconditional on purpose: a developer who exported CATERVA_HISTORY_FILE
 * pointing at their real history (to inspect it, say) would otherwise have
 * the test suite append fixtures to it.
 */
export function isolateCatervaState(env: NodeJS.ProcessEnv = process.env): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'caterva-test-state-'));
  env[STATE_DIR_VAR] = dir;
  env[HISTORY_VAR] = path.join(dir, 'history.json');
  env[RECORDS_VAR] = path.join(dir, 'records');
  return dir;
}
