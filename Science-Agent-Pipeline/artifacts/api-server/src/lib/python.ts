import { spawnSync } from "node:child_process";
import path from "node:path";

const SUPPORTED_MINOR_VERSIONS = new Set([10, 11, 12, 13]);
const REQUIRED_IMPORTS = [
  "numpy",
  "roadrunner",
  "antimony",
  "libsbml",
  "httpx",
  "pydantic",
  "bs4",
];

/** Check version and every import required by the two Python bridges. */
export function canRunSupportedPython(
  candidate: string,
  repoRoot: string,
): boolean {
  const importChecks = REQUIRED_IMPORTS.map((name) => `import ${name}`).join(
    "; ",
  );
  const result = spawnSync(
    candidate,
    [
      "-c",
      "import sys; " +
        "sys.exit(1) if sys.version_info[:2] not in ((3, 10), (3, 11), (3, 12), (3, 13)) else None; " +
        importChecks,
    ],
    { cwd: repoRoot, stdio: "ignore" },
  );
  return result.status === 0;
}

let cached: {
  repoRoot: string;
  configured: string | undefined;
  virtualEnv: string | undefined;
  path: string | undefined;
  pythonPath: string | undefined;
  executable: string;
} | null = null;

/**
 * Resolve the interpreter used for every Python bridge.
 *
 * The project supports Python 3.10–3.13 (ADR 0014). Never silently use
 * ambient `python3`: on some machines it is 3.9 (which cannot evaluate the
 * project's PEP 604 annotations), and on others it is an unsupported build
 * entirely. A supported interpreter with a bare or incomplete environment is
 * rejected here rather than failing later inside a child-process bridge.
 */
export function resolvePythonExecutable(repoRoot: string): string {
  const configured = process.env["TERRIUM_PYTHON"];
  const virtualEnv = process.env["VIRTUAL_ENV"];
  const environmentPath = process.env["PATH"];
  const pythonPath = process.env["PYTHONPATH"];
  if (
    cached &&
    cached.repoRoot === repoRoot &&
    cached.configured === configured &&
    cached.virtualEnv === virtualEnv &&
    cached.path === environmentPath &&
    cached.pythonPath === pythonPath
  ) {
    return cached.executable;
  }

  const configuredCandidate =
    configured && (path.isAbsolute(configured) || configured.includes(path.sep))
      ? path.resolve(repoRoot, configured)
      : configured;
  const candidates = configuredCandidate
    ? [configuredCandidate]
    : virtualEnv
      ? [path.join(virtualEnv, "bin", "python")]
      : [
          path.join(repoRoot, ".venv", "bin", "python"),
          "python3.13",
          "python3.12",
          "python3.11",
          "python3.10",
          // Bare `python3` LAST, and only as a fallback.
          //
          // The version-specific names come first because on a machine with
          // several interpreters they are the ones that say which is which,
          // and picking the newest supported one deliberately is better than
          // taking whatever `python3` happens to point at.
          //
          // But refusing `python3` entirely rejects working environments over
          // a filename. Many containers ship exactly one interpreter, at
          // /usr/bin/python3, with every dependency installed and no
          // python3.NN symlink anywhere — and Terrium told them to "install
          // Python 3.12" when 3.12 was already there under a different name.
          //
          // This is safe because `canRunSupportedPython` checks
          // `sys.version_info` and every required import before accepting a
          // candidate. The name was never what made a candidate valid; it was
          // only ever a hint about where to look.
          "python3",
        ];

  for (const candidate of candidates) {
    if (canRunSupportedPython(candidate, repoRoot)) {
      cached = {
        repoRoot,
        configured,
        virtualEnv,
        path: environmentPath,
        pythonPath,
        executable: candidate,
      };
      return candidate;
    }
  }

  throw new Error(
    "No supported Python 3.10–3.13 interpreter with Terrium dependencies found. " +
      "Set TERRIUM_PYTHON or install Python 3.12 with requirements-dev.txt.",
  );
}

/** Return whether a version is inside Terrium's supported interpreter range. */
export function isSupportedPythonMinor(minor: number): boolean {
  return SUPPORTED_MINOR_VERSIONS.has(minor);
}
