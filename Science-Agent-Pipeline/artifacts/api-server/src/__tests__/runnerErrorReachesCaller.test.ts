/**
 * The runner reports a caught failure as {"ok": false, "error": ...} on
 * stdout and exits 1, with nothing on stderr. The wrapper read only stderr,
 * so "BRENDA returned 500 for EC 2.7.1.1" reached callers as "Science agent
 * runner exited with code 1" (CI, 2026-09-28). The reason has to survive.
 */
import { describe, expect, it } from "vitest";

import { runnerError } from "../lib/scienceAgent";

describe("runnerError", () => {
  it("returns the runner's own reason from its failure record", () => {
    const out =
      'log line\n{"ok": false, "error": "Server error \'500 Internal Server Error\' for url ..."}';
    expect(runnerError(out)).toContain("500 Internal Server Error");
  });

  it("is null for a success, a non-JSON line or empty output", () => {
    expect(runnerError('{"ok": true, "found": true}')).toBeNull();
    expect(runnerError("Traceback (most recent call last):")).toBeNull();
    expect(runnerError("")).toBeNull();
  });
});
