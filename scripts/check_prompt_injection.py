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

A baseline file is supported (`scripts/trojan-baseline.json`). An
unreviewed baseline is a suppression list nobody read, and this codebase
has spent eleven stages removing checks that could not fail -- so the
mechanism is built to resist becoming one:

  * Every entry must carry a `reason` of real length. An exemption without
    a written verdict fails the build rather than silently exempting.
  * Entries are keyed on trojan-scan's `fingerprint`, and the recorded
    `file` is re-checked at match time. A verdict reached about one file
    cannot drift onto another.
  * Every applied exemption is PRINTED on every run. A suppression list
    that vanishes from the output stops being read.

THE MECHANISM DID NOT EXIST UNTIL 2026-08-11 (Part 22)

The paragraph above, and the failure message below, both told readers to
record benign findings in `trojan-baseline.json`. Nothing read that file.

THE FOUR VERDICTS RECORDED ON 2026-08-24
----------------------------------------
Said plainly, because of who did it: the analysis below was prepared by an
AI agent and applied on the owner's instruction to proceed. That is worth
writing down, since an agent clearing findings about *text aimed at agents*
is the shape this guard exists to catch. The reasoning is here to be
disagreed with, and reverting is one commit.

  * `START_HERE.md` -- a signpost row whose label names the machine half of
    the audience, beside a link. Quoting that label here made THIS file trip
    the same rule, so it is described rather than reproduced -- the trap the
    commandResolve.ts entry already records. Exempts the POINTER only;
    `docs/AGENT_BRIEF.md` is an instruction surface that nothing here has
    reviewed.
  * `Tests/enzyme_preparation.py` -- a docstring naming the cost of erring
    in each direction on the recombinant/native threshold. Text that
    volunteers its own failure modes is not talking a reviewer out of
    anything.
  * `docs/mutations/adr-0037-organism-column.json` -- a `_note` describing
    a MUTATION's diagnostic power, not any code's safety.
  * `docs/mutations/adr-0068-live-data-sources.json` -- a mutation PAYLOAD:
    the `replace` side of a patch that rewrites a NOTICE line into a bland
    reassurance, so a guard can be proven to catch exactly that. The string
    exists to imitate concealment, and the scanner flagging it is the
    scanner working. The entry is keyed to that one fingerprint, so the
    same phrasing anywhere else is still a finding.
Following the instruction did nothing: the entry landed, the build stayed
red, and the reader believed they had recorded an exemption.

Found alongside it: the finding printer looked for `rule` and `id`, but
trojan-scan 0.2.0 emits `ruleId`. Every finding this guard has ever printed
said `[?]` where the rule name belongs.

A documented mechanism that does not exist is worse than an undocumented
gap, for the same reason a guard that reports OK on a failed parse is worse
than no guard: it is trusted.

CURRENT EXEMPTIONS (3, all one sentence)

The CLI prints a cross-species warning when a resolved parameter was
measured in a different organism than the one asked about, cautioning the
reader against attributing it to the queried species. `trust-assertion`
fires on it because the rule looks for instructions to stay quiet -- and
this is the opposite: it surfaces a caveat that would otherwise be buried.
The sentence appears three times: once in `src/cli/commandResolve.ts` and
twice quoted (README example output, and the Part 14 stage record). The
quotes are verbatim on purpose; rewording them to satisfy the scanner would
make the documentation describe output the tool does not produce.

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

#: Reviewed exemptions. Both this file's docstring and the failure message
#: told readers to record benign findings here -- and until now NOTHING READ
#: IT. Following the instruction did nothing: the entry landed, the build
#: stayed red, and the reader believed they had recorded an exemption.
#:
#: A documented mechanism that does not exist is worse than an undocumented
#: gap, for the same reason a guard that reports OK on a failed parse is
#: worse than no guard: it is trusted.
BASELINE_PATH = REPO_ROOT / "scripts" / "trojan-baseline.json"


def _load_baseline() -> tuple[dict[str, dict[str, str]], list[str]]:
    """Returns ({fingerprint: entry}, problems).

    Keyed on trojan-scan's own `fingerprint`, which is stable across
    reformatting in a way that a line number is not. But a bare hash is
    unreadable, and an exemption list nobody can read is the thing this
    guard exists to prevent -- so `file` and `reason` are required too, and
    the file is re-checked at match time.

    Every entry must carry a real `reason`. An exemption without a written
    verdict is exactly the "suppression list nobody read" the docstring
    warns about, so an unreasoned entry FAILS the build rather than quietly
    exempting anything.
    """
    if not BASELINE_PATH.is_file():
        return {}, []

    try:
        raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [
            f"{BASELINE_PATH.name} could not be read ({exc}). Refusing to "
            "scan with an unreadable exemption list -- it would silently "
            "exempt nothing, or everything, depending on the bug."
        ]

    entries = raw.get("exemptions", raw) if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        return {}, [
            f"{BASELINE_PATH.name} must contain a list of exemptions (or an "
            "object with an 'exemptions' list)."
        ]

    baseline: dict[str, dict[str, str]] = {}
    problems: list[str] = []

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            problems.append(f"{BASELINE_PATH.name}[{index}] is not an object.")
            continue

        fingerprint = str(entry.get("fingerprint", "")).strip()
        file_ = str(entry.get("file", "")).strip()
        reason = str(entry.get("reason", "")).strip()

        if not fingerprint or not file_:
            problems.append(
                f"{BASELINE_PATH.name}[{index}] needs both 'fingerprint' "
                "(from the scan's JSON output) and 'file' (so a human can "
                "tell what is being exempted)."
            )
            continue
        if len(reason) < 20:
            problems.append(
                f"{BASELINE_PATH.name}[{index}] ({file_}) has no usable "
                "'reason'. An exemption without a written verdict is a "
                "suppression list nobody read -- say why the finding is "
                "benign, in a sentence the next reader can check."
            )
            continue

        baseline[fingerprint] = {"file": file_, "reason": reason}

    return baseline, problems


#: Fewest files that must exist under the scan root for "clean" to mean
#: anything.
#:
#: This guard refuses in six ways already -- npx missing, timeout, OSError,
#: empty stdout, unparseable JSON, wrong JSON shape -- each saying that a
#: scan which did not happen is not a clean scan. It had no answer for the
#: seventh: a scan that ran perfectly over nothing. Measured, with the guard
#: placed outside the tree it scans, it printed its success line having seen
#: no files.
#:
#: The floor is on the INPUT rather than the output, because trojan-scan
#: reports no denominator -- its `summary` counts findings, and zero findings
#: is exactly what a clean repository is supposed to produce. Counting the
#: files that exist is a sanity check on what was handed to the tool, not a
#: second implementation of what the tool does with them.
#:
#: Established remedy, not an invention (ADR 0185):
#: `check_public_images_reviewed` refuses with "found only 0 public image(s),
#: below the floor of 5. The scan is broken, not the pages."
_MIN_FILES = 100


def _files_under_root() -> int:
    """How many files the scanner was pointed at. Cheap and approximate."""
    count = 0
    for path in REPO_ROOT.rglob("*"):
        parts = set(path.parts)
        if parts & {"node_modules", ".git", "__pycache__", ".venv", "venv"}:
            continue
        if path.is_file():
            count += 1
            if count >= _MIN_FILES:
                break          # the floor is a threshold, not a census
    return count


def check() -> list[str]:
    """Returns a list of violation strings, empty when the tree is clean."""
    if os.environ.get(SKIP_ENV) == "1":
        print(
            f"NOTE: prompt-injection scan skipped ({SKIP_ENV}=1). This is an "
            "explicit opt-out, not a pass."
        )
        return []

    seen = _files_under_root()
    if seen < _MIN_FILES:
        return [
            f"only {seen} file(s) exist under the scan root, below the floor "
            f"of {_MIN_FILES}. The scan is broken, not the tree -- over an "
            "empty directory 'no injection indicators' is true and means "
            "nothing."
        ]

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

    baseline, baseline_problems = _load_baseline()
    if baseline_problems:
        return baseline_problems

    violations: list[str] = []
    exempted: list[str] = []

    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if str(finding.get("severity", "")).lower() != FAIL_SEVERITY:
            continue
        location = str(finding.get("file") or finding.get("path") or "?")
        line = finding.get("line", "?")
        # trojan-scan 0.2.0 emits `ruleId`. The original code looked for
        # `rule` and `id`, so EVERY finding this guard has ever printed said
        # `[?]` where the rule name belongs -- and a baseline keyed on that
        # name could never have matched anything.
        rule = str(
            finding.get("ruleId")
            or finding.get("rule")
            or finding.get("id")
            or "?"
        )
        fingerprint = str(finding.get("fingerprint", ""))
        message = finding.get("message") or finding.get("title") or ""

        entry = baseline.get(fingerprint)
        if entry is not None:
            if entry["file"] != location.lstrip("./"):
                # The verdict was reached about a different file. Exempting
                # on a stale record would silence a finding nobody reviewed.
                violations.append(
                    f"{location}:{line} [{rule}] is exempted by a baseline "
                    f"entry recorded against {entry['file']}. Re-review it "
                    "and update the entry, or remove it."
                )
                continue
            exempted.append(f"{location}:{line} [{rule}] -- {entry['reason']}")
            continue

        violations.append(
            f"{location}:{line} [{rule}] {message} -- text aimed at an AI "
            "reader rather than a human one. Several agents commit to this "
            "repository and read each other's files, so prose is an "
            "execution surface here."
        )

    # Printed every run, never silently dropped. A baseline that disappears
    # from the output is indistinguishable from no findings at all, which
    # is how an exemption list stops being read.
    if exempted:
        print(f"Reviewed exemptions applied ({len(exempted)}):")
        for entry in exempted:
            print(f"  {entry}")
        print()

    return violations


def main() -> int:
    violations = check()
    if not violations:
        print(
            "OK: no unexempted high-severity prompt-injection indicators. "
            "Any reviewed exemptions are listed above with their verdicts; "
            "see this file's docstring for the triage history."
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