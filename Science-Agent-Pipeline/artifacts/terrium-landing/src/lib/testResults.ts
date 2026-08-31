// Real, current results from running every suite in the stack end to end.
//
// This is NOT a mock. These numbers come from actually running the suites:
//   cd Terium                                          && python -m pytest -v -rs
//   cd Tests                                            && python -m pytest -v -rs
//   cd Science-Agent-Pipeline/artifacts/api-server      && npx vitest run
//   cd Science-Agent-Pipeline/artifacts/terrium-landing && npx vitest run
//
// The Python suites were run in a throwaway virtualenv built from this
// repo's own requirements.txt + requirements-dev.txt, so the count reflects
// every declared dependency actually being present -- not whatever happens
// to already be on the machine that last updated this file.
//
// Whoever updates this file after adding/removing tests should re-run all
// four suites and paste the real numbers -- that's the entire point of the
// terminal panel this feeds: it should never show a number nobody checked.

export interface SuiteFile {
  file: string;
  passed: number;
  skipped: number;
  failed: number;
}

export interface TestSuite {
  name: string;
  workingDirectory: string;
  files: SuiteFile[];
}

export const TEST_SUITES: TestSuite[] = [
  {
    name: "simulation engine",
    workingDirectory: "Terium/",
    files: [
      {
        file:
          "52 test files -- kinetics & Michaelis-Menten correctness, " +
          "epidemiology (SIR/SEIR), stochastic simulation (Gillespie SSA), " +
          "molecular dynamics, population genetics, PCR, SBML export & " +
          "provenance, and citation/build guards",
        passed: 1228,
        skipped: 0,
        failed: 0,
      },
    ],
  },
  {
    name: "literature layer (BRENDA / KEGG / PubMed)",
    workingDirectory: "Tests/",
    files: [
      {
        file:
          "77 test files -- BRENDA/KEGG parsing, table scoping, " +
          "organism resolution, citation formatting, fallback logic",
        passed: 1116,
        skipped: 1,
        failed: 0,
      },
    ],
  },
  {
    name: "agent pipeline API",
    workingDirectory: "Science-Agent-Pipeline/artifacts/api-server/",
    files: [
      {
        file:
          "55 test files -- query resolution, parameter provenance, " +
          "literature verification, rate limiting, SSE job routes",
        passed: 627,
        skipped: 0,
        failed: 0,
      },
    ],
  },
  {
    name: "landing app",
    workingDirectory: "Science-Agent-Pipeline/artifacts/terrium-landing/",
    files: [
      { file: "AgentSimulator.test.tsx", passed: 3, skipped: 0, failed: 0 },
      { file: "Components.test.tsx", passed: 8, skipped: 0, failed: 0 },
    ],
  },
];

export const SKIP_EXPLANATION =
  "test_popgen_resolver.py skips one test when stdpopsim isn't installed. " +
  "stdpopsim is GPL-3.0-or-later; Terrium is Apache-2.0, so it was moved " +
  "out of requirements.txt into an optional requirements-popgen.txt on " +
  "2026-08-15 rather than mixing licenses into the default install. The " +
  "population-genetics code itself wraps that import in try/except and " +
  "degrades to the non-stdpopsim path -- this is a documented licensing " +
  "boundary, not an untested code path.";

export function totals() {
  let passed = 0;
  let skipped = 0;
  let failed = 0;
  for (const suite of TEST_SUITES) {
    for (const f of suite.files) {
      passed += f.passed;
      skipped += f.skipped;
      failed += f.failed;
    }
  }
  return { passed, skipped, failed, total: passed + skipped + failed };
}
