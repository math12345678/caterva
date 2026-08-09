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
import pathlib
import shutil
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PIPELINE_DIR = REPO_ROOT / "Science-Agent-Pipeline"

#: Directories that never contain a workspace we should type-check.
SKIP_PARTS = {"node_modules", "dist", ".next", "out-tsc", ".git", "__pycache__"}

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
