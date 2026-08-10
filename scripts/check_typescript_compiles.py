"""Guard that the TypeScript workspaces actually type-check.

This guard exists because `verify_build.py --quick` was printing

    ✅ ALL CHECKS PASSED
    🎉 The codebase is in a deployable state!

on a tree whose TypeScript did not compile. That happened repeatedly on
2026-08-09: `tsc --noEmit` had 16 errors (a `pH`/`ph` field-name mismatch
and calls to four `VerifiableMetricsCollector` methods that did not exist)
while every guard in the suite reported green.

The hole was structural, not accidental:

  * There was no type-check step anywhere in `verify_build.py`.
  * `run_typescript_tests()` (`npm test`) ran only in FULL mode, so
    `--quick` -- the mode the README documents as the everyday command and
    the one used most often -- exercised no TypeScript at all.

So the aggregate verifier's headline claim was, for the TypeScript half of
the codebase, unfounded. That is exactly the failure mode ADR 0015 names:
a rule nothing executes is not enforced. "Deployable" has to mean it
compiles.

A type check is the right thing to run always rather than only in full
mode: it is fast (a few seconds), fully deterministic, needs no network,
and catches the single most common way a broken change reaches the tree --
which matters more now that several agents commit to this repository
concurrently and a break can land between one command and the next.

Checks every workspace that has its own tsconfig.json and a `src/`
directory, so a new workspace is covered the moment it exists rather than
when someone remembers to add it here.

Run directly: python scripts/check_typescript_compiles.py
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PIPELINE_DIR = REPO_ROOT / "Science-Agent-Pipeline"

#: Directories that never contain a workspace we should type-check.
SKIP_PARTS = {
    "node_modules",
    "dist",
    ".next",
    "out-tsc",
    ".git",
    "__pycache__",
    # Virtualenvs and caches hold no first-party TypeScript but are large
    # enough to dominate the directory walk below -- .venv alone is tens of
    # thousands of files.
    ".venv",
    "venv",
    ".pytest_cache",
    ".hypothesis",
    ".mypy_cache",
    "htmlcov",
    ".freebuff",
}

#: How long a single workspace's type check may take before we call it
#: hung. tsc on this repo's largest workspace runs in well under 30s; the
#: ceiling is generous so a cold run on a slow machine does not flake.
TSC_TIMEOUT_S = 180


def _candidate_workspaces() -> list[pathlib.Path]:
    """Every directory under Science-Agent-Pipeline/ holding a tsconfig.json
    and a src/ tree.

    Discovered rather than hardcoded: a hardcoded list is exactly how the
    original gap persisted -- something existed that nothing checked.
    """
    found: list[pathlib.Path] = []
    if not PIPELINE_DIR.is_dir():
        return found
    for tsconfig in PIPELINE_DIR.rglob("tsconfig.json"):
        if any(part in SKIP_PARTS for part in tsconfig.parts):
            continue
        workspace = tsconfig.parent
        if not (workspace / "src").is_dir():
            continue
        found.append(workspace)
    return sorted(found)



def all_typescript_projects() -> list[pathlib.Path]:
    """Every directory in the repository holding a tsconfig.json.

    Unlike `_candidate_workspaces()` this is not scoped to
    Science-Agent-Pipeline/ and does not require a `src/` subdirectory, so
    a project anywhere in the tree is discovered.
    """
    projects: list[pathlib.Path] = []
    for current, directories, files in os.walk(REPO_ROOT):
        directories[:] = [d for d in directories if d not in SKIP_PARTS]
        if "tsconfig.json" in files:
            projects.append(pathlib.Path(current))
    return sorted(projects)


def first_party_typescript() -> set[pathlib.Path]:
    """Every .ts/.tsx file in the repository that we wrote.

    Declaration files are excluded: a stray .d.ts is a type declaration,
    not code that needs compiling.
    """
    sources: set[pathlib.Path] = set()
    for current, directories, files in os.walk(REPO_ROOT):
        directories[:] = [d for d in directories if d not in SKIP_PARTS]
        here = pathlib.Path(current)
        for name in files:
            if name.endswith(".d.ts"):
                continue
            if name.endswith(".ts") or name.endswith(".tsx"):
                sources.add((here / name).resolve())
    return sources


def files_covered_by(project: pathlib.Path) -> set[pathlib.Path]:
    """The set of files `tsc` actually pulls into this project.

    Asks the compiler via `--listFiles` rather than reimplementing
    tsconfig's include/exclude/extends resolution, which has enough corner
    cases (globs, `references`, `files` vs `include`, implicit exclusions)
    that a hand-rolled version would be wrong in ways nobody would notice.

    `--listFiles` prints the file list even when the compile has errors, so
    coverage is still known for a project that does not currently build.
    """
    try:
        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--listFiles", "-p", "."],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=TSC_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        return set()

    covered: set[pathlib.Path] = set()
    for line in result.stdout.splitlines():
        candidate = line.strip()
        if not candidate.endswith((".ts", ".tsx")):
            continue
        path = pathlib.Path(candidate)
        if not path.is_absolute():
            path = (project / path).resolve()
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.is_relative_to(REPO_ROOT):
            covered.add(resolved)
    return covered


def unguarded_typescript_trees() -> list[pathlib.Path]:
    """Top-level trees holding TypeScript that no tsconfig actually compiles.

    A workspace without a tsconfig.json is invisible to the type check
    above -- it discovers workspaces BY their tsconfig, so a TypeScript
    tree that lacks one is silently not type-checked rather than reported.

    That is not hypothetical. On 2026-08-09 a `src/` tree appeared at the
    repository root: 3,300+ lines across literatureService.ts,
    scientificValidator.ts, reproducibilityEngine.ts and a CLI, with a
    package.json advertising `"type-check": "tsc --noEmit"` and
    `"build": "tsc"` -- and no tsconfig.json for either script to use. It
    could not be compiled by its own commands, was imported by nothing, and
    no guard in this repository looked at it. It contained a `verifyDOI`
    that returned true for any DOI-shaped string, and a reproducibility
    verifier whose `maxRelativeError` was always exactly 0.

    IMPLEMENTATION NOTE, and the reason this asks tsc instead of looking
    for files: the first version of this function tested "does a
    tsconfig.json exist at or above this directory". That test became
    VACUOUS the moment a tsconfig.json was added at the repository root to
    cover src/ -- every directory in the repo then found that root config
    by walking up, so the function could never report anything again. It
    returned "no unguarded trees" because it was structurally incapable of
    returning anything else, which is precisely the class of defect this
    guard exists to catch. Membership is now decided by the compiler's own
    `--listFiles` output, so a file that no project actually pulls in is
    reported however many tsconfigs happen to sit above it.
    """
    sources = first_party_typescript()
    if not sources:
        return []

    covered: set[pathlib.Path] = set()
    for project in all_typescript_projects():
        covered |= files_covered_by(project)

    return sorted(sources - covered)


#: Build-tool configuration files -- `vite.config.ts`, `vitest.config.ts`,
#: `drizzle.config.ts`, `orval.config.ts` and friends. Each is loaded and
#: type-stripped by its own tool at runtime rather than compiled by the
#: application's tsconfig, so they routinely sit outside every project's
#: `include`. They are genuinely not type-checked, and the conventional
#: remedy is a `tsconfig.node.json` per workspace that includes them.
#:
#: They are reported on every run but do not fail the build, because the
#: blast radius differs in kind: a broken vite.config.ts stops the build
#: immediately and loudly, whereas an unchecked application module ships.
#: This distinction is written down rather than silently applied -- an
#: exemption nobody can see is how a guard rots.
def _is_tool_config(path: pathlib.Path) -> bool:
    return path.name.endswith(".config.ts")


def unguarded_source_files() -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """Split uncovered TypeScript into (application source, tool configs)."""
    uncovered = unguarded_typescript_trees()
    configs = [f for f in uncovered if _is_tool_config(f)]
    source = [f for f in uncovered if not _is_tool_config(f)]
    return source, configs


def _has_local_typescript(workspace: pathlib.Path) -> bool:
    """Whether `npx tsc` in this workspace will resolve a real compiler
    without reaching out to the network to fetch one.

    `npx` silently downloads a missing package, which would turn an
    offline run into either a hang or a spurious failure. Walking up for a
    node_modules/typescript keeps this guard honest about what it can
    check locally.
    """
    for directory in [workspace, *workspace.parents]:
        if (directory / "node_modules" / "typescript").is_dir():
            return True
        if directory == REPO_ROOT:
            break
    return False


def _tsconfig_is_checkable(workspace: pathlib.Path) -> bool:
    """Skip solution-style tsconfigs that only reference other projects and
    have nothing of their own to compile -- `tsc --noEmit` on those errors
    out with TS6307 rather than reporting anything useful."""
    try:
        raw = (workspace / "tsconfig.json").read_text(encoding="utf-8")
    except OSError:
        return False
    # tsconfig.json permits comments and trailing commas, which json.loads
    # rejects; a parse failure is not a reason to skip the workspace, so
    # fall through to checking it.
    try:
        config = json.loads(raw)
    except json.JSONDecodeError:
        return True
    if not isinstance(config, dict):
        return True
    has_references = bool(config.get("references"))
    has_own_files = bool(config.get("files") or config.get("include"))
    return has_own_files or not has_references


def check() -> list[str]:
    """Type-check every discovered workspace. Returns a list of violation
    strings, empty when everything compiles."""
    violations: list[str] = []

    if shutil.which("npx") is None:
        return [
            "npx is not on PATH, so no TypeScript workspace could be "
            "type-checked. Install Node.js, or run with --no-typescript if "
            "this is deliberate."
        ]

    # TypeScript that no project compiles is not "zero workspaces", it is
    # unchecked code. Reported before the per-workspace loop so it cannot
    # be lost among passing results.
    unguarded_source, unguarded_configs = unguarded_source_files()

    for source in unguarded_source:
        violations.append(
            f"{source.relative_to(REPO_ROOT)} is TypeScript that NO "
            "tsconfig.json actually compiles, so nothing type-checks it. "
            "Add it to a project's `include`, give its tree a "
            "tsconfig.json, or delete it -- unguarded code is where "
            "defects live unobserved."
        )

    if unguarded_configs:
        print(
            "NOTE: %d build-tool config file(s) are not type-checked by any "
            "project. Not a build failure (see _is_tool_config), but real:"
            % len(unguarded_configs)
        )
        for config in unguarded_configs:
            print(f"  - {config.relative_to(REPO_ROOT)}")
        print(
            "  Remedy: add a tsconfig.node.json per workspace including "
            "these files.\n"
        )

    workspaces = _candidate_workspaces()
    if not workspaces:
        return [
            f"no TypeScript workspaces found under {PIPELINE_DIR.name}/ -- "
            "expected at least one (api-server). Has the layout moved?"
        ]

    for workspace in workspaces:
        rel = workspace.relative_to(REPO_ROOT)

        if not _has_local_typescript(workspace):
            violations.append(
                f"{rel}: no local node_modules/typescript, so this workspace "
                "was NOT type-checked. Run `pnpm install` first -- a "
                "workspace that cannot be checked must not be reported as "
                "passing."
            )
            continue

        if not _tsconfig_is_checkable(workspace):
            continue

        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", "-p", "."],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=TSC_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            violations.append(
                f"{rel}: tsc --noEmit timed out after {TSC_TIMEOUT_S}s"
            )
            continue

        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            lines = [line for line in output.splitlines() if line.strip()]
            # Name the count and show the first few: the full list can run
            # to dozens of lines and the point here is to fail loudly with
            # enough detail to start on, not to reproduce tsc's whole log.
            shown = "\n      ".join(lines[:8])
            more = f"\n      ... and {len(lines) - 8} more line(s)" if len(lines) > 8 else ""
            violations.append(
                f"{rel}: tsc --noEmit reported {len(lines)} error line(s):"
                f"\n      {shown}{more}"
            )

    return violations


def main() -> int:
    violations = check()
    if not violations:
        checked = [str(w.relative_to(REPO_ROOT)) for w in _candidate_workspaces()]
        print(
            "OK: TypeScript type-checks clean in "
            f"{len(checked)} workspace(s): {', '.join(checked)}."
        )
        return 0

    print("TypeScript compilation failures found:\n")
    for violation in violations:
        print(f"  {violation}")
    print(
        "\nA tree whose TypeScript does not compile is not deployable, "
        "whatever the other guards say."
        "\nFix with: cd <workspace> && npx tsc --noEmit -p ."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
