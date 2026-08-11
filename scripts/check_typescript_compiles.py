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

import concurrent.futures
import json
import os
import pathlib
import re
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



def _load_tsconfig(tsconfig: pathlib.Path) -> dict | None:
    """Parse a tsconfig, tolerating the comments and trailing commas the
    format permits but `json` does not.

    Every tsconfig in this repository is commented -- that is deliberate,
    the comments explain why each config exists -- so a plain
    `json.loads` fails on all of them and any logic built on it silently
    falls back to its default branch. Returns None when the file really
    cannot be parsed.
    """
    try:
        raw = tsconfig.read_text(encoding="utf-8")
    except OSError:
        return None

    # Strip // line comments and /* */ blocks, then trailing commas.
    without_block = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
    without_line = re.sub(r"^\s*//.*$", "", without_block, flags=re.M)
    without_trailing = re.sub(r",(\s*[}\]])", r"\1", without_line)

    try:
        parsed = json.loads(without_trailing)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _compiles_something(tsconfig: pathlib.Path) -> bool:
    """Whether running tsc on this config can compile any files at all.

    A pure base (`tsconfig.base.json`) exists to be `extends`-ed and names
    no inputs of its own; a solution-style config only holds `references`.
    Running tsc on either costs a full compiler startup and yields nothing
    -- and on this repository each such run is measured in tens of seconds,
    so skipping them is the difference between a guard that fits inside the
    everyday command's budget and one that does not.

    Unparseable configs return True: an unreadable file is not a reason to
    skip checking, and the cost of one extra run is smaller than the cost
    of silently ignoring a real project.
    """
    config = _load_tsconfig(tsconfig)
    if config is None:
        return True
    if config.get("files") or config.get("include"):
        return True

    # No inputs named at all. Two cases, both skipped:
    #
    #   * `references` only -- a solution-style config that delegates to
    #     other projects and compiles nothing itself (tsc reports TS6307).
    #   * neither -- a pure base such as `tsconfig.base.json`, which exists
    #     to be `extends`-ed. tsc given one of these defaults to including
    #     EVERY .ts beneath its directory, so it is simultaneously the
    #     slowest run in the sweep and the least meaningful: it would
    #     report coverage for files no real project compiles, masking a
    #     genuinely unguarded tree.
    #
    # This assumes every real project in this repository declares its
    # inputs explicitly, which is true and is worth keeping true.
    return False


def all_typescript_projects() -> list[pathlib.Path]:
    """Every tsconfig in the repository, as a path to the config FILE.

    Unlike `_candidate_workspaces()` this is not scoped to
    Science-Agent-Pipeline/ and does not require a `src/` subdirectory, so
    a project anywhere in the tree is discovered.

    Any `tsconfig*.json` counts, not just `tsconfig.json`. The convention
    for build-tool configs (vite.config.ts, vitest.config.ts,
    drizzle.config.ts) is a sibling `tsconfig.node.json`, and looking only
    for the exact name `tsconfig.json` would leave those files reported as
    uncovered no matter how correctly they were wired up.
    """
    projects: list[pathlib.Path] = []
    for current, directories, files in os.walk(REPO_ROOT):
        directories[:] = [d for d in directories if d not in SKIP_PARTS]
        here = pathlib.Path(current)
        for name in files:
            if name.startswith("tsconfig") and name.endswith(".json"):
                candidate = here / name
                if _compiles_something(candidate):
                    projects.append(candidate)
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


#: Memoises the one tsc run per tsconfig. Coverage and the type-check both
#: need `tsc -p <cfg>`, and running it twice per project doubled the guard's
#: wall-clock -- which on a repo that now has 12 tsconfigs pushed the
#: everyday `verify_build.py --quick` past its timeout. `--listFiles`
#: returns the file list AND the diagnostics, so one run answers both.
_TSC_CACHE: dict[pathlib.Path, tuple[int, str, str]] = {}


def _run_tsc(tsconfig: pathlib.Path) -> tuple[int, str, str]:
    """Run `tsc --noEmit --listFiles -p <tsconfig>` once, memoised.

    Returns (returncode, stdout, stderr). A timeout or spawn failure is
    reported as a non-zero code with an explanatory stderr rather than
    raising, so one unbuildable project cannot abort the whole sweep.
    """
    cached = _TSC_CACHE.get(tsconfig)
    if cached is not None:
        return cached

    try:
        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--listFiles", "-p", tsconfig.name],
            cwd=tsconfig.parent,
            capture_output=True,
            text=True,
            timeout=TSC_TIMEOUT_S,
        )
        outcome = (result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        outcome = (1, "", f"tsc timed out after {TSC_TIMEOUT_S}s")
    except OSError as exc:
        outcome = (1, "", f"could not run tsc: {exc}")

    _TSC_CACHE[tsconfig] = outcome
    return outcome


def files_covered_by(tsconfig: pathlib.Path) -> set[pathlib.Path]:
    """The set of files `tsc` actually pulls into this project.

    Asks the compiler via `--listFiles` rather than reimplementing
    tsconfig's include/exclude/extends resolution, which has enough corner
    cases (globs, `references`, `files` vs `include`, implicit exclusions)
    that a hand-rolled version would be wrong in ways nobody would notice.

    `--listFiles` prints the file list even when the compile has errors, so
    coverage is still known for a project that does not currently build.
    """
    project = tsconfig.parent
    _, stdout, _ = _run_tsc(tsconfig)

    covered: set[pathlib.Path] = set()
    for line in stdout.splitlines():
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
    tsconfig.json exist at or above this directory". When a tsconfig.json
    was added at the repository root to cover src/, this test stopped being
    effective -- every directory in the repo would find that root config
    by walking up, making the function unable to identify unguarded files.
    This is an example of a check that appears to pass due to structural
    limitations rather than actual coverage. The current approach uses the
    compiler's own `--listFiles` output, so files that no project actually
    pulls in are identified correctly regardless of tsconfig hierarchy.
    """
    sources = first_party_typescript()
    if not sources:
        return []

    # Warm the tsc cache in PARALLEL. Each project is an independent
    # subprocess, so they can run concurrently; serially, 12 tsconfigs at
    # roughly 10s of npx-plus-tsc each pushed this guard past the timeout
    # on `verify_build.py --quick`. Bounded rather than unbounded so a
    # machine with few cores is not swamped by a dozen compilers.
    projects = all_typescript_projects()
    if projects:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(8, len(projects))
        ) as pool:
            # _run_tsc memoises, so the sequential loop below is all cache
            # hits. Exceptions are swallowed by _run_tsc itself.
            list(pool.map(_run_tsc, projects))

    covered: set[pathlib.Path] = set()
    for project in projects:
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

        # Reuses the memoised run from the coverage sweep above rather
        # than invoking tsc a second time on the same project. Compiling
        # every workspace twice doubled this guard's wall-clock, and once
        # the repo reached 12 tsconfigs that pushed `verify_build.py
        # --quick` -- the everyday command -- past its timeout.
        returncode, stdout, stderr = _run_tsc(workspace / "tsconfig.json")

        if returncode != 0:
            # `--listFiles` puts the file list on stdout alongside the
            # diagnostics, so the paths are filtered out here; otherwise
            # every error report would be buried under hundreds of lines
            # naming every file in the program.
            output = "\n".join(
                line
                for line in (stdout + stderr).splitlines()
                if line.strip() and not line.strip().endswith((".ts", ".tsx"))
            ).strip()
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
