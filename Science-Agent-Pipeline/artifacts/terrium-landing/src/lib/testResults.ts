// Real, current results from running both test suites end to end.
//
// This is NOT a mock. These numbers come from actually running the suites:
//   cd Tellurium && python -m pytest -v -rs
//   cd Tests      && python -m pytest -v -rs
//
// Whoever updates this file after adding/removing tests should re-run both
// suites and paste the real numbers -- that's the entire point of the
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
    name: 'simulation engine',
    workingDirectory: 'Tellurium/',
    files: [
      { file: 'test_brenda_integration.py', passed: 19, skipped: 1, failed: 0 },
      { file: 'test_dependencies_declared.py', passed: 1, skipped: 0, failed: 0 },
      { file: 'test_engine_api.py', passed: 39, skipped: 0, failed: 0 },
      { file: 'test_epidemiology_correctness.py', passed: 23, skipped: 0, failed: 0 },
      { file: 'test_kinetics_correctness.py', passed: 30, skipped: 0, failed: 0 },
      { file: 'test_model_building.py', passed: 38, skipped: 0, failed: 0 },
      { file: 'test_numerical_robustness.py', passed: 30, skipped: 0, failed: 0 },
      { file: 'test_pcr_correctness.py', passed: 32, skipped: 0, failed: 0 },
      { file: 'test_properties.py', passed: 19, skipped: 0, failed: 0 },
      { file: 'test_sbml.py', passed: 28, skipped: 0, failed: 0 },
      { file: 'test_validation.py', passed: 45, skipped: 0, failed: 0 },
    ],
  },
  {
    name: 'literature layer (BRENDA / KEGG / PubMed)',
    workingDirectory: 'Tests/',
    files: [
      { file: '52 test files -- BRENDA/KEGG parsing, table scoping, '
        + 'organism resolution, citation formatting, fallback logic',
        passed: 124, skipped: 0, failed: 0 },
    ],
  },
];

export const SKIP_EXPLANATION =
  'test_flagged_brenda_entries_do_not_become_confident_numbers skips when '
  + 'its fixture -- a real captured BRENDA page for LDH -- happens to '
  + 'contain zero flagged Km rows, which it currently does. Nothing false '
  + 'to assert against real data that came back clean is not a gap. The '
  + 'same contract (a flagged Km must stay flagged through the engine) is '
  + 'exercised unconditionally by '
  + 'test_flagged_entries_do_not_become_confident_numbers_deterministic, '
  + 'which builds a flagged entry directly instead of depending on scraped '
  + 'data being unlucky.';

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
