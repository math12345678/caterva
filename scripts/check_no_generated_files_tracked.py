"""Guard that build output is not committed to git.

WHY THIS KEEPS HAPPENING

Three times in one session, derived files were about to enter or did enter
version control:

  * `node_modules/` was untracked but NOT ignored, so a `git add -A` would
    have committed tens of thousands of vendored files.
  * `coverage/` appeared after a `--coverage` run, likewise unignored.
  * `dist/` — 41 compiled `.js` files — WAS committed, after `tsconfig.json`
    gained an `outDir` and lost `noEmit`.

None of these are malicious or even careless in isolation. They are what
happens when several agents work a repository quickly and `git add -A` is
the habit. But committed build output is a specific kind of damage in THIS
codebase, which has spent seventeen parts removing duplicate sources of
truth: `dist/src/units.js` is a second copy of `src/units.ts` that goes
stale the instant anyone edits the TypeScript, and a reader who opens it
gets a confident, wrong answer to "what does this module do".

Every serious defect this project has found lived in a copy nobody was
watching. A compiled mirror of the entire source tree is the largest
possible instance of that.

WHAT IT CHECKS

Whether git is TRACKING anything under a known-generated path. Not whether
the directory exists -- building is fine, committing the build is not. It
reads `git ls-files`, so it reflects the index rather than the filesystem.

Run directly: python scripts/check_no_generated_files_tracked.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Paths whose contents are derived from source. Committing any of them
#: puts a second, staleable copy of something into the tree.
GENERATED_PATHS: dict[str, str] = {
    "dist": "compiled TypeScript output (`npm run build`)",
    "build": "build output",
    "coverage": "test coverage report (`npm run test:coverage`)",
    "node_modules": "installed dependencies",
    ".pnpm-store": "pnpm's content-addressable store",
    "out-tsc": "TypeScript build output",
    ".next": "Next.js build output",
    "__pycache__": "Python bytecode",
    ".pytest_cache": "pytest's cache",
    ".mypy_cache": "mypy's cache",
    "htmlcov": "coverage HTML report",
}

#: Individual file suffixes that are always derived.
GENERATED_SUFFIXES: dict[str, str] = {
    ".tsbuildinfo": "TypeScript incremental build state",
    ".pyc": "Python bytecode",
}


def _tracked_files() -> list[str] | None:
    """Every path git currently tracks, or None if git could not be asked."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line.strip()]


def check() -> list[str]:
    """Returns a list of violation strings, empty when the index is clean."""
    tracked = _tracked_files()

    if tracked is None:
        return [
            "Could not run `git ls-files`, so it is unknown whether build "
            "output is committed. A check that did not run is not a check "
            "that passed."
        ]

    if not tracked:
        return [
            "`git ls-files` returned nothing. Either this is not a git "
            "repository or the index is empty -- refusing to report success "
            "on an empty result."
        ]

    offenders: dict[str, list[str]] = {}

    for path in tracked:
        parts = pathlib.PurePosixPath(path).parts

        for directory, description in GENERATED_PATHS.items():
            # Matched as a path COMPONENT, so `dist/x.js` and
            # `packages/a/dist/x.js` both count, while a source file that
            # merely contains the word does not.
            if directory in parts:
                offenders.setdefault(f"{directory}/ — {description}", []).append(path)
                break
        else:
            for suffix, description in GENERATED_SUFFIXES.items():
                if path.endswith(suffix):
                    offenders.setdefault(f"*{suffix} — {description}", []).append(path)
                    break

    violations: list[str] = []
    for label, paths in sorted(offenders.items()):
        sample = ", ".join(paths[:3])
        more = f" (and {len(paths) - 3} more)" if len(paths) > 3 else ""
        violations.append(
            f"{len(paths)} tracked file(s) under {label}: {sample}{more}. "
            "Build output is derived, not source -- a committed copy goes "
            "stale the moment anyone edits the original, and gives the next "
            "reader a confident wrong answer. Remove with "
            f"`git rm -r --cached <path>` and add it to .gitignore."
        )

    return violations


def main() -> int:
    violations = check()
    if not violations:
        print(
            "OK: no build output, caches or vendored dependencies are "
            "tracked in git."
        )
        return 0

    print(f"Generated files found in version control ({len(violations)}):\n")
    for violation in violations:
        print(f"  {violation}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
