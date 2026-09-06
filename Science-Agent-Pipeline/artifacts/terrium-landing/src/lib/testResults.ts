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
//
// Nobody did, for a while. Audited 2026-09-03 against live runs, this file
// claimed 1228 engine passes when the engine suite contains only 1205
// TESTS -- more passing tests than exist. It also claimed 55 api-server
// test files / 627 passed (actual 63 / 733), 2 landing files / 11 passed
// (actual 4 / 22), 0 engine skips (actual 4), and 1116 literature-layer
// passes (actual 1130). Those numbers feed the hero, the metrics bar and
// the trust section -- the most-read figures in a product whose entire
// claim is that every number is verifiable.
//
// scripts/check_landing_test_counts.py now guards them. By default it
// compares the "NN test files" figure in each description against the
// filesystem, which is instant and runs in `make guards`; `--full` runs
// all four suites and compares pass counts exactly (~40 minutes).
//
// MEASUREMENT NOTES, because these counts are contention-sensitive:
// running several suites at once produces spurious failures and DIFFERENT
// totals -- the api-server suite reported 726/726 alone, and 695 passed /
// 23 failed while two pytest suites and two dev servers were running, with
// failures at 150-172s that are timeouts, not defects. Every number below
// was taken from a run with nothing else in flight, via --junitxml
// rather than by reading the console summary, which pytest was not
// emitting through the capture used here.
//
// THE ENGINE NUMBER IS NOW MEASURED, NOT DERIVED (2026-09-05):
// 1246 passed / 0 skipped / 0 failed, from a direct run of Terium/ alone
// under the repo's .venv, read out of a junit-xml report rather than off
// the terminal.
//
// It previously read 1201 passed / 4 skipped, and that figure was
// REASONED rather than run: a plain machine reported 1200 passed /
// 4 skipped / 1 failed, the failure being
// test_citation_metadata.py::test_the_guard_passes refusing to treat
// "cffconvert is not installed" as a pass -- correctly, since 'could not
// check' and 'checked and fine' are different facts -- and 1201/4/0 was
// what that implied for a provisioned environment. Sound reasoning, but a
// derived number on a page whose claim is that every number was checked.
// The four skips are gone too: they were optional dependencies that
// `make setup` now installs.
//
// The api-server suite has the same shape of environment dependency, and
// the same treatment. python.test.ts refuses to run its two
// interpreter-selection cases unless a Python 3.10-3.13 with Terrium's
// dependencies is discoverable (VIRTUAL_ENV, a repo-root .venv, or a
// versioned python3.1x on PATH). On a machine where none is -- the
// versioned homebrew pythons here lack roadrunner -- it fails rather than
// skipping, deliberately: "could not check" is not "checked and fine".
// Measured 2026-09-05: 744 passed / 2 failed on this machine, 746 passed
// with a discoverable interpreter, which is the number below.

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
          "55 test files -- kinetics & Michaelis-Menten correctness, " +
          "epidemiology (SIR/SEIR), stochastic simulation (Gillespie SSA), " +
          "molecular dynamics, population genetics, PCR, SBML export & " +
          "provenance, and citation/build guards",
        // Measured 2026-09-06, Terium/ run alone under .venv.
        passed: 1317,
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
          "78 test files -- BRENDA/KEGG parsing, table scoping, " +
          "organism resolution, citation formatting, fallback logic",
        // Measured 2026-09-05, running Tests/ alone under .venv (the
        // interpreter these counts are documented against):
        // `1130 passed, 1 skipped in 257.23s`. Run ALONE deliberately --
        // these suites are contention-sensitive and a parallel run has
        // already produced a spuriously low figure twice in this file's
        // history.
        passed: 1130,
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
          "74 test files -- query resolution, parameter provenance, " +
          "literature verification, model grounding for caller-supplied " +
          "models, rate limiting, SSE job routes",
        // Measured 2026-09-06: `74 passed (74) / 798 passed (798)`, run
        // alone with the repo's .venv/bin first on PATH.
        //
        // That PATH is not a thumb on the scale, it is the documented
        // environment. Two tests in python.test.ts assert that a
        // TERRIUM_PYTHON given as a BARE NAME resolves through PATH, and
        // they refuse -- rather than skip -- when no PATH-resolvable
        // interpreter has Terrium's dependencies installed. Homebrew's
        // python3.11 and python3.12 are on PATH here but have none of
        // them, so off a `make setup` shell those two fail for a reason
        // that is about this machine and not about the code. With
        // .venv/bin on PATH all 7 pass, which is what CI does.
        //
        // The previous entry read `passed: 755, failed: 0` -- but 755 was
        // the suite TOTAL, of which 753 passed and 2 failed. Reporting a
        // total in the passed column turns any failure into an invisible
        // one, which is the specific dishonesty this panel exists to
        // avoid.
        passed: 798,
        skipped: 0,
        failed: 0,
      },
    ],
  },
  {
    name: "landing app",
    workingDirectory: "Science-Agent-Pipeline/artifacts/terrium-landing/",
    files: [
      {
        file:
          "5 test files -- component rendering, nav/section integrity, " +
          "page-claim accuracy, and disabled-source claims",
        passed: 36,
        skipped: 0,
        failed: 0,
      },
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
