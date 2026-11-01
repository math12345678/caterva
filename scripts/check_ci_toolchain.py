#!/usr/bin/env python3
"""Every `pnpm` step in CI can actually find pnpm, and runs the pinned version.

WHY THIS EXISTS
---------------
CI failed on every push for two days. The `api-server` job read:

    - name: Install pnpm
      run: corepack prepare pnpm@11.4.0 --activate

    - name: Install workspace dependencies
      working-directory: Science-Agent-Pipeline
      run: pnpm install --frozen-lockfile

`corepack prepare --activate` **exits 0 and creates no `pnpm` on PATH**.
Reproduced locally on Node v22.23.2 / corepack 0.34.6 -- the same Node major
the workflow requests:

    $ corepack prepare pnpm@11.4.0 --activate
    Preparing pnpm@11.4.0 for immediate activation...
    $ echo $?
    0
    $ which pnpm
    (nothing)

`corepack enable` is the command that writes the shims. So the install step
died on `pnpm: command not found` while the step named "Install pnpm"
reported success -- a check that cannot fail, sitting one line above the
thing it was supposed to make work.

THE VERSION WAS ALSO A FICTION
------------------------------
`Science-Agent-Pipeline/package.json` declares `"packageManager":
"pnpm@11.20.0"`. Corepack's shim reads that field and runs THAT version,
regardless of what `prepare` named. Verified in the same reproduction: with
the shim on PATH and `packageManager: pnpm@11.20.0` in the directory,

    $ pnpm --version
    11.20.0

So `11.4.0` in the workflow was never going to be the version that ran even
in the world where the step worked. Two people reading the workflow would
disagree about which pnpm CI uses, and both would be wrong.

WHY THIS IS ARCHITECTURE-INDEPENDENT, WHICH MATTERS HERE
--------------------------------------------------------
The previous attempt at this same failing build concluded from
`pip install` output that `libroadrunner==2.8.0` did not exist. It does; the
sandbox is aarch64 and the wheels are x86_64, and GitHub's runners are
x86_64. A local observation was generalised to a machine it did not describe,
and the pin, the numpy version, and a whole Python from the CI matrix were
changed on the strength of it. `check_pins_resolve.py` exists because of it.

Nothing in *this* guard is a claim about wheels, interpreters, or CPUs.
Whether `corepack prepare` writes a shim is the same on every architecture,
and the reproduction above ran the runner's own Node major. That is the only
reason a local result was allowed to settle it.

WHAT IT CHECKS
--------------
1. A job that runs `pnpm` must run `corepack enable` in an EARLIER step.
2. `corepack prepare pnpm@X --activate` is reported wherever it stands in
   for enabling, and named for what it is: a no-op that exits 0.
3. A pnpm version written into a workflow must equal the `packageManager`
   field that will actually decide the version.

WHAT IT DOES NOT CHECK
----------------------
Whether the install then succeeds. That needs a network and a lockfile
resolution, which is CI's job. This guard answers exactly one question --
"can the command be found, and is the version named the version that runs" --
and says so rather than implying it vouched for the build.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, NamedTuple

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is in requirements-dev
    sys.stderr.write(
        "check_ci_toolchain: PyYAML is not installed.\n"
        "  This is 'could not check', NOT 'checked and fine'. Exiting 3.\n"
    )
    raise SystemExit(3)

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

#: `pnpm` as a command, not as a substring of `pnpm-lock.yaml` or a prose
#: mention. Anchored to a line start or a shell separator.
PNPM_INVOCATION = re.compile(r"(?:^|[;&|]\s*|\s&&\s*)pnpm\s", re.MULTILINE)
COREPACK_ENABLE = re.compile(r"\bcorepack\s+enable\b")
COREPACK_PREPARE = re.compile(r"\bcorepack\s+prepare\s+pnpm@(\S+)")
PNPM_VERSION_MENTION = re.compile(r"\bpnpm@(\d[^\s'\"]*)")


class Finding(NamedTuple):
    workflow: str
    job: str
    step: str
    problem: str
    remedy: str


def _package_manager(working_directory: str | None) -> tuple[str | None, str]:
    """The version corepack will ACTUALLY use, and where it was read from.

    Returns `(None, reason)` when it cannot be determined. A missing
    package.json is not "the versions agree" -- the caller must not treat an
    absent answer as a passing one.
    """
    base = REPO_ROOT / working_directory if working_directory else REPO_ROOT
    manifest = base / "package.json"
    if not manifest.is_file():
        return None, f"no package.json at {manifest.relative_to(REPO_ROOT)}"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"{manifest.relative_to(REPO_ROOT)} is not readable JSON: {exc}"
    declared = data.get("packageManager")
    if not isinstance(declared, str) or not declared.startswith("pnpm@"):
        return None, f"{manifest.relative_to(REPO_ROOT)} declares no pnpm packageManager"
    return declared[len("pnpm@") :], str(manifest.relative_to(REPO_ROOT))


def audit_job(workflow: str, job_name: str, job: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    steps = job.get("steps") or []
    if not isinstance(steps, list):
        return findings

    enabled_by: str | None = None
    prepared_at: tuple[str, str] | None = None  # (step name, version)

    for step in steps:
        if not isinstance(step, dict):
            continue
        run = step.get("run")
        if not isinstance(run, str):
            continue
        name = str(step.get("name") or run.strip().splitlines()[0][:40])

        if COREPACK_ENABLE.search(run):
            enabled_by = enabled_by or name

        prepare = COREPACK_PREPARE.search(run)
        if prepare and not COREPACK_ENABLE.search(run):
            prepared_at = (name, prepare.group(1))

        if PNPM_INVOCATION.search(run):
            if enabled_by is None:
                if prepared_at is not None:
                    problem = (
                        f"runs pnpm, but the only preparation was "
                        f"`corepack prepare pnpm@{prepared_at[1]} --activate` in "
                        f"step {prepared_at[0]!r}, which exits 0 and writes no "
                        f"shim. This step dies on `pnpm: command not found`."
                    )
                else:
                    problem = (
                        "runs pnpm, and no earlier step in this job ran "
                        "`corepack enable`. Unless the runner image ships pnpm, "
                        "this step dies on `pnpm: command not found`."
                    )
                findings.append(
                    Finding(
                        workflow,
                        job_name,
                        name,
                        problem,
                        "add a step running `corepack enable` before this one.",
                    )
                )

        # Version drift: any pnpm@X written in the workflow must match the
        # packageManager field, because that field is what decides.
        for match in PNPM_VERSION_MENTION.finditer(run):
            written = match.group(1)
            actual, source = _package_manager(step.get("working-directory"))
            if actual is None:
                # Cannot determine -> report as undetermined, never as agreeing.
                findings.append(
                    Finding(
                        workflow,
                        job_name,
                        name,
                        f"names pnpm@{written}, and the version that would "
                        f"actually run could not be determined ({source}).",
                        "declare `packageManager` so the two can be compared.",
                    )
                )
            elif actual != written:
                findings.append(
                    Finding(
                        workflow,
                        job_name,
                        name,
                        f"names pnpm@{written}, but corepack reads "
                        f"packageManager from {source} and will run "
                        f"pnpm@{actual}. The workflow describes a version that "
                        f"never runs.",
                        f"write pnpm@{actual}, or stop naming a version here.",
                    )
                )
    return findings


def audit(workflows: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(workflows):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            findings.append(
                Finding(path.name, "-", "-", f"is not parseable YAML: {exc}", "fix the syntax.")
            )
            continue
        if not isinstance(doc, dict):
            continue
        jobs = doc.get("jobs")
        if not isinstance(jobs, dict):
            continue
        for job_name, job in jobs.items():
            if isinstance(job, dict):
                findings.extend(audit_job(path.name, str(job_name), job))
    return findings


def _selftest() -> int:
    """Prove each finding can fire, against a workflow built to trip it.

    A guard whose scope is 'the repository as it stands' reports zero
    findings forever once the repository is clean, and a matcher that matched
    nothing would report zero too. These cases are the difference.
    """
    cases: list[tuple[str, dict[str, Any], bool]] = [
        (
            "prepare --activate, then pnpm",
            {
                "steps": [
                    {"name": "Install pnpm", "run": "corepack prepare pnpm@11.4.0 --activate"},
                    {"name": "Install deps", "run": "pnpm install --frozen-lockfile"},
                ]
            },
            True,
        ),
        (
            "pnpm with no corepack at all",
            {"steps": [{"name": "Test", "run": "pnpm run test"}]},
            True,
        ),
        (
            "corepack enable, then pnpm",
            {
                "steps": [
                    {"name": "Enable", "run": "corepack enable"},
                    {"name": "Install", "run": "pnpm install --frozen-lockfile"},
                ]
            },
            False,
        ),
        (
            "enable AFTER the pnpm step is not earlier",
            {
                "steps": [
                    {"name": "Install", "run": "pnpm install"},
                    {"name": "Enable", "run": "corepack enable"},
                ]
            },
            True,
        ),
        (
            "pnpm-lock.yaml in prose is not an invocation",
            {
                "steps": [
                    {"name": "Note", "run": "echo 'see pnpm-lock.yaml for details'"},
                ]
            },
            False,
        ),
        (
            "pnpm after && still needs the shim",
            {"steps": [{"name": "Chain", "run": "cd app && pnpm install"}]},
            True,
        ),
    ]

    failures = 0
    for label, job, should_find in cases:
        got = bool(audit_job("selftest.yml", "job", job))
        ok = got == should_find
        failures += not ok
        verdict = "ok" if ok else "SELFTEST FAILED"
        expected = "a finding" if should_find else "no finding"
        print(f"  [{verdict}] {label}: expected {expected}, got {'a finding' if got else 'none'}")

    # The version comparison, exercised against the real manifest so that a
    # renamed field or a moved file breaks the selftest rather than silently
    # making every comparison undeterminable.
    actual, source = _package_manager("Science-Agent-Pipeline")
    if actual is None:
        print(f"  [SELFTEST FAILED] packageManager unreadable: {source}")
        failures += 1
    else:
        print(f"  [ok] packageManager reads as pnpm@{actual} from {source}")
        wrong = {"steps": [{"name": "s", "working-directory": "Science-Agent-Pipeline",
                            "run": f"corepack prepare pnpm@0.0.0-nope --activate"}]}
        if not audit_job("selftest.yml", "job", wrong):
            print("  [SELFTEST FAILED] a mismatched pnpm version was not reported")
            failures += 1
        else:
            print("  [ok] a mismatched pnpm version is reported")

    if failures:
        print(f"\nSELFTEST FAILED: {failures} case(s).")
        return 1
    print("\nSelftest passed: every finding above can fire.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true", help="prove the checks can fail")
    args = parser.parse_args()

    if args.selftest:
        return _selftest()

    if not WORKFLOW_DIR.is_dir():
        # Not "no problems found". No workflows to check is a different fact.
        print(f"No workflow directory at {WORKFLOW_DIR.relative_to(REPO_ROOT)} — nothing checked.")
        return 3

    workflows = list(WORKFLOW_DIR.glob("*.yml")) + list(WORKFLOW_DIR.glob("*.yaml"))
    if not workflows:
        print("No workflow files found — nothing checked.")
        return 3

    findings = audit(workflows)
    print(f"Workflow files checked: {len(workflows)}")

    if not findings:
        print("  every pnpm step has a `corepack enable` before it, and every")
        print("  version named matches the packageManager that decides.")
        print()
        print("  NOT checked: whether the install then succeeds. That needs a")
        print("  network and a lockfile resolution. See the module docstring.")
        return 0

    print(f"\nCI toolchain findings ({len(findings)}):\n")
    for f in findings:
        print(f"  {f.workflow} :: job {f.job} :: step {f.step!r}")
        print(f"      {f.problem}")
        print(f"      -> {f.remedy}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
