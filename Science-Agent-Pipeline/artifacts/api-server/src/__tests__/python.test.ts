import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { buildTeriumEnvironment } from "../lib/teriumRunner";
import {
  canRunSupportedPython,
  isSupportedPythonMinor,
  resolvePythonExecutable,
} from "../lib/python";

const originalTerriumPython = process.env["TERRIUM_PYTHON"];

afterEach(() => {
  if (originalTerriumPython === undefined) delete process.env["TERRIUM_PYTHON"];
  else process.env["TERRIUM_PYTHON"] = originalTerriumPython;
});

describe("Python bridge environment", () => {
  it("preserves an existing PYTHONPATH and appends the repository root", () => {
    const baseEnv = {
      PATH: "/usr/bin",
      PYTHONPATH: ["/opt/science", "/opt/shared"].join(path.delimiter),
    };

    const merged = buildTeriumEnvironment(baseEnv, "/repo");

    expect(merged.PATH).toBe("/usr/bin");
    expect(merged.PYTHONPATH).toBe(
      ["/opt/science", "/opt/shared", "/repo"].join(path.delimiter),
    );
  });
});

describe("Python bridge interpreter selection", () => {
  it("recognizes only the supported 3.10–3.13 minor versions", () => {
    expect(isSupportedPythonMinor(9)).toBe(false);
    expect(isSupportedPythonMinor(10)).toBe(true);
    expect(isSupportedPythonMinor(11)).toBe(true);
    expect(isSupportedPythonMinor(12)).toBe(true);
    expect(isSupportedPythonMinor(13)).toBe(true);
    expect(isSupportedPythonMinor(14)).toBe(false);
  });

  /**
   * Finds an interpreter this environment can actually run Terrium on, or
   * throws saying so.
   *
   * Both tests below used to branch on the result -- asserting the happy
   * path when one was found and the error path when one was not. That
   * accommodates both outcomes and therefore cannot fail: on a machine with
   * no usable Python the "accepts a configured interpreter" tests passed
   * without ever configuring an interpreter.
   *
   * The engine is not optional (`scripts/check_env.py` treats roadrunner,
   * antimony and libsbml as required, and the route suites run real
   * simulations), so "no usable interpreter" is a broken environment. It is
   * reported here, once, with the candidates that were tried -- rather than
   * silently converting every test in this describe block into a no-op.
   *
   * The absent-interpreter error message is not left untested: "does not
   * silently fall back when TERRIUM_PYTHON is invalid" below asserts it
   * directly, by pointing TERRIUM_PYTHON at a path that cannot exist.
   */
  function requireSupportedPython(repoRoot: string): string {
    // Deliberately NOT a mirror of resolvePythonExecutable's fallback order.
    // The old copy of that list was itself a defect: it predicted "nothing
    // will be found" by checking fewer paths than the function falls back to,
    // so adding python3.13 to the source made the test's prediction wrong
    // while nothing test-visible changed. This list only has to find SOME
    // usable interpreter to configure; which one the source would have
    // preferred is not this test's claim.
    const candidates = [
      process.env["VIRTUAL_ENV"]
        ? `${process.env["VIRTUAL_ENV"]}/bin/python`
        : undefined,
      `${repoRoot}/.venv/bin/python`,
      "python3.13",
      "python3.12",
      "python3.11",
      "python3.10",
    ].filter((candidate): candidate is string => Boolean(candidate));

    const discovered = candidates.find((candidate) =>
      canRunSupportedPython(candidate, repoRoot),
    );

    if (!discovered) {
      throw new Error(
        "no Python 3.10-3.13 interpreter with Terrium dependencies is " +
          `available, so the interpreter-selection tests cannot run. Tried: ${candidates.join(
            ", ",
          )}. Install the dependencies in requirements.txt, or set ` +
          "TERRIUM_PYTHON to an interpreter that has them.",
      );
    }

    return discovered;
  }

  it("honours TERRIUM_PYTHON when set to a supported interpreter path", () => {
    delete process.env["TERRIUM_PYTHON"];
    const repoRoot = process.cwd();

    const discovered = requireSupportedPython(repoRoot);
    process.env["TERRIUM_PYTHON"] = discovered;

    // Unconditional: an explicitly configured, working interpreter must be
    // the one used. Silently preferring a different one is the failure this
    // test exists to catch.
    expect(resolvePythonExecutable(repoRoot)).toBe(discovered);
  });

  it("honours TERRIUM_PYTHON when set to a bare executable name", () => {
    delete process.env["TERRIUM_PYTHON"];
    const repoRoot = process.cwd();

    // A bare name (resolved via PATH) rather than an absolute path -- the
    // distinction this test adds over the one above.
    const executableName = ["python3.13", "python3.12", "python3.11", "python3.10"].find(
      (candidate) => canRunSupportedPython(candidate, repoRoot),
    );

    expect(
      executableName,
      "no supported python3.1x is on PATH, so the bare-name case cannot be " +
        "exercised; install one or set TERRIUM_PYTHON",
    ).toBeDefined();

    process.env["TERRIUM_PYTHON"] = executableName!;
    expect(resolvePythonExecutable(repoRoot)).toBe(executableName);
  });

  it("does not silently fall back when TERRIUM_PYTHON is invalid", () => {
    process.env["TERRIUM_PYTHON"] = "/definitely/not/a/python";
    expect(() => resolvePythonExecutable(process.cwd())).toThrow(
      /No supported Python 3\.10–3\.13 interpreter with Terrium dependencies found/,
    );
  });
});
