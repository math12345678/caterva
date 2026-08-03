import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { buildTelluriumEnvironment } from "../lib/telluriumRunner";
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

    const merged = buildTelluriumEnvironment(baseEnv, "/repo");

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

  it("accepts a configured supported interpreter path", () => {
    delete process.env["TERRIUM_PYTHON"];
    const repoRoot = process.cwd();
    const candidates = [
      process.env["VIRTUAL_ENV"]
        ? `${process.env["VIRTUAL_ENV"]}/bin/python`
        : undefined,
      `${repoRoot}/.venv/bin/python`,
    ].filter((candidate): candidate is string => Boolean(candidate));
    const discovered = candidates.find((candidate) =>
      canRunSupportedPython(candidate, repoRoot),
    );
    if (discovered) {
      process.env["TERRIUM_PYTHON"] = discovered;
      expect(resolvePythonExecutable(repoRoot)).toBe(discovered);
    } else {
      expect(() => resolvePythonExecutable(repoRoot)).toThrow(
        /No supported Python 3\.10–3\.13 interpreter with Terrium dependencies found/,
      );
    }
  });

  it("accepts a configured executable name when one is available", () => {
    const executableName = [
      "python3.13",
      "python3.12",
      "python3.11",
      "python3.10",
    ].find(
      (candidate) => canRunSupportedPython(candidate, process.cwd()),
    );
    if (executableName) {
      process.env["TERRIUM_PYTHON"] = executableName;
      expect(resolvePythonExecutable(process.cwd())).toBe(executableName);
    } else {
      expect(() => resolvePythonExecutable(process.cwd())).toThrow(
        /No supported Python 3\.10–3\.13 interpreter with Terrium dependencies found/,
      );
    }
  });

  it("does not silently fall back when TERRIUM_PYTHON is invalid", () => {
    process.env["TERRIUM_PYTHON"] = "/definitely/not/a/python";
    expect(() => resolvePythonExecutable(process.cwd())).toThrow(
      /No supported Python 3\.10–3\.13 interpreter with Terrium dependencies found/,
    );
  });
});
