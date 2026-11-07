import { HISTORY_VAR, RECORDS_VAR, isolateCatervaState } from './isolatedState';

// Belt and braces for a run that bypasses the package.json config (a single
// file run with `--config` pointing elsewhere, or an IDE runner that drops
// globalSetup): without the global variables, give this file its own
// scratch directory rather than fall through to ~/.caterva. The guard test
// (src/__tests__/testsDoNotWriteToYourHome.test.ts) still fails such a run
// for children spawned without an explicit env, which only globalSetup
// reaches.
if (!process.env[HISTORY_VAR] || !process.env[RECORDS_VAR]) {
  isolateCatervaState(process.env);
}
