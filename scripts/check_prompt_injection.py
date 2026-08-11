"""Guard that no prompt injection aimed at an AI agent has entered the tree.

WHY THIS REPOSITORY SPECIFICALLY

Several AI coding agents commit to Terrium concurrently, and they read each
other's files -- source, comments, docs, test fixtures. That makes text an
execution surface: a sentence written to manipulate a reader rather than inform
one can change what the next agent does. It is the same threat model as a
malicious dependency, except the payload is prose.

This wraps `trojan-scan`, which runs entirely offline and looks for
instruction overrides, forged role markers, planted trust assertions, and
payloads hidden in invisible unicode or base64.

ON THE BASELINE

On 2026-08-11 a scan reported 16 findings (8 high, 8 medium). Every one was
examined individually and every one was a false positive -- the scanner
matching English phrases in legitimate documentation:

  * SECURITY_HARDENING.md      documents that there is NO secrets manager
                               and secrets come from process.env. An honest
                               security assessment, not an exfiltration
                               instruction.
  * check_typescript_compiles  an implementation note explaining why a
                               guard had become ineffective. Flagged on the
                               phrase "never report".
  * test_model_building.py     explains that validate=False skips
                               validation, which is the behaviour under
                               test.
  * CliApp.tsx                 a decorative pulse-dot carrying aria-hidden,
                               which is correct accessibility practice.
  * DashboardPreview.tsx       a Tailwind `overflow-hidden` layout class.
  * BUILD_PIPELINE.md and co.  docs that mention "Claude" or "LLM", and an
                               API guide with a "System:" line in an example
                               transcript.

The findings then disappeared on their own: concurrent agents reworded
several of those files for unrelated reasons between the scan and this
guard being written. That is worth knowing, because it means a clean scan
today is not evidence that the earlier findings were ever real -- the
verdicts above are, and they were reached by reading each site.

A baseline file is supported (`trojan-baseline.json`) and deliberately NOT
pre-populated: an unreviewed baseline is a suppression list nobody read,
and this codebase has spent eleven stages removing checks that could not
fail. If a future finding is genuinely benign, add it to the baseline WITH
a justification in this docstring, so the next reader can tell a reviewed
exemption from a silenced one.

CANNOT-RUN IS NOT CLEAN

If `npx`/`trojan-scan` is unavailable the guard reports that it could not
run and FAILS, rather than printing a pass. A scanner that silently skips
is indistinguishable from a scanner that found nothing, which is precisely
the defect class this repository keeps correcting. Set
TERRIUM_SKIP_INJECTION_SCAN=1 to opt out explicitly -- visibly, in the
environment, not by accident.

Run directly: python scripts/check_prompt_injection.py
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Severity at which a finding fails the build. "high" only: the medium
#: tier is dominated by docs that legitimately name an AI agent, and this
#: repository's docs discuss agents constantly by nature.
FAIL_SEVERITY = "high"

#: Generous: the scan walks ~750 files and took 27s on a slow mount.
SCAN_TIMEOUT_S = 300

SKIP_ENV = "TERRIUM_SKIP_INJECTION_SCAN"


def check() -> list[str]:
    """Returns a list of violation strings, empty when the tree is clean."""
    if os.environ.get(SKIP_ENV) == "1":
        print(
            f"NOTE: prompt-injection scan skipped ({SKIP_ENV}=1). This is an "
            "explicit opt-out, not a pass."
        )
        return []

    if shutil.which("npx") is None:
        return [
            "npx is not on PATH, so the prompt-injection scan could NOT run. "
            "A scan that did not happen is not a clean scan. Install Node.js, "
            f"or set {SKIP_ENV}=1 to opt out deliberately."
        ]

    command = [
        "npx",
        "--yes",
        "trojan-scan@0.2.0",
        ".",
        "--format",
        "json",
        "--severity",
        FAIL_SEVERITY,
        # Always exit 0; this guard decides what fails, from the parsed
        # findings, so an exit code cannot be mistaken for a verdict.
        "--fail-on",
        "never",
    ]

    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=SCAN_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return [
            f"prompt-injection scan timed out after {SCAN_TIMEOUT_S}s and "
            "therefore reported nothing. Treating that as a failure rather "
            "than a pass."
        ]
    except OSError as exc:
        return [f"prompt-injection scan could not be started: {exc}"]

    stdout = result.stdout.strip()
    if not stdout:
        return [
            "prompt-injection scan produced no output at all "
            f"(exit {result.returncode}). {result.stderr.strip()[:300]} "
            "-- an empty result is not a clean result."
        ]

    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return [
            f"prompt-injection scan returned unparseable JSON ({exc}). "
            "Refusing to report success on output that could not be read."
        ]

    findings = report.get("findings", report if isinstance(report, list) else [])
    if not isinstance(findings, list):
        return [
            "prompt-injection scan JSON had no 'findings' list; the tool's "
            "output shape may have changed. Refusing to report success."
        ]

    violations: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if str(finding.get("severity", "")).lower() != FAIL_SEVERITY:
            continue
        location = finding.get("file") or finding.get("path") or "?"
        line = finding.get("line", "?")
        rule = finding.get("rule") or finding.get("id") or "?"
        message = finding.get("message") or finding.get("title") or ""
        violations.append(
            f"{location}:{line} [{rule}] {message} -- text aimed at an AI "
            "reader rather than a human one. Several agents commit to this "
            "repository and read each other's files, so prose is an "
            "execution surface here."
        )

    return violations


def main() -> int:
    violations = check()
    if not violations:
        print(
            "OK: no high-severity prompt-injection indicators. "
            "(Baseline is deliberately empty -- see this file's docstring "
            "for why, and for the 2026-08-11 triage.)"
        )
        return 0

    print(f"Prompt-injection indicators found ({len(violations)}):\n")
    for violation in violations:
        print(f"  {violation}")
    print(
        "\nEach finding needs a human verdict. If it is benign, record WHY "
        "in scripts/check_prompt_injection.py's docstring before adding it "
        "to trojan-baseline.json -- an unreviewed baseline is a suppression "
        "list nobody read."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
