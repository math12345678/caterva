import { describe, expect, it } from "vitest";

import * as reliabilityScore from "../lib/reliabilityScore";

/**
 * This file used to test a TypeScript implementation of Bakker's three
 * reliability axes, asserting it agreed with `Tests/reliability.py` on the
 * shared 16-case fixture. It did agree. It did not help.
 *
 * The bug was never in either implementation. `queryResolver.ts` called the
 * TypeScript grader with no `PhysiologicalReference` — none was reachable
 * from an HTTP request — so `conditionProximity` returned `not_assessed` on
 * every response the API server ever produced, while the CLI consumed the
 * Python score and reported real grades. Both graders return `not_assessed`
 * for a call with no reference, so the parity test found perfect agreement
 * on a question neither implementation was being asked.
 *
 * **A parity test pins two implementations against a shared fixture. It says
 * nothing about a call site that hands one of them different arguments.**
 *
 * So the TypeScript grader is gone rather than merely bypassed, and this
 * file now guards the deletion instead of the code. It exists because
 * "remove the duplicate" is not a durable fix on its own — the duplicate
 * comes back the first time someone needs a grade in TypeScript and writes
 * a helper rather than an ADR.
 *
 * What replaced it:
 *   - Grading: `Tests/reliability.py`, pinned by
 *     `Tests/reliability_cases.json` (16 cases) and
 *     `test_case_file_is_not_empty_and_covers_every_grade`, which asserts
 *     the fixture exercises every grade of every axis. No coverage was lost.
 *   - Pass-through: `reliabilityFromRunner.test.ts`, which mocks a grade the
 *     wrong implementation could not produce.
 *   - Threading: `reliabilitySingleSource.test.ts`, which asserts the
 *     reference reaches the runner and is never invented.
 */

describe("reliabilityScore.ts is types only", () => {
  const GRADING_FUNCTIONS = [
    "scoreReliability",
    "gradeAssayCompleteness",
    "gradeConditionProximity",
    "gradeOrganismMatch",
  ];

  it.each(GRADING_FUNCTIONS)(
    "does not export %s — grading lives in Python",
    (name) => {
      expect(reliabilityScore).not.toHaveProperty(name);
    },
  );

  it("exports no callable at all", () => {
    // Deliberately broader than the named list. A second implementation
    // reintroduced under a different name ("computeReliability",
    // "gradeAxes") would slip past a name-by-name check, and the name is
    // not what makes it a duplicate.
    const callables = Object.entries(reliabilityScore)
      .filter(([, value]) => typeof value === "function")
      .map(([name]) => name);

    expect(callables).toEqual([]);
  });

  it("still carries the types the wire contract needs", async () => {
    // The counterpart. If this module were emptied entirely the test above
    // would pass while `ScienceAgentResult.reliability` lost its shape, so
    // the absence of functions has to be paired with the presence of types.
    //
    // Types are erased at runtime, so this checks the source rather than the
    // module object — the only way to assert an interface still exists.
    const { readFileSync } = await import("node:fs");
    const path = await import("node:path");
    const source = readFileSync(
      path.join(__dirname, "..", "lib", "reliabilityScore.ts"),
      "utf8",
    );

    const required = [
      "PhysiologicalReference",
      "ReliabilityScore",
      "ScoreAxis",
      "AssayCompleteness",
      "ConditionProximity",
      "OrganismMatch",
    ];
    const missing = required.filter(
      (name) => !new RegExp(`export (interface|type) ${name}\\b`).test(source),
    );

    // Reported as a list rather than one `expect` per name so a failure
    // names every type that went missing, not just the first.
    expect(missing).toEqual([]);
  });
});
