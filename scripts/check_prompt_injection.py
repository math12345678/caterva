"""Guard that no prompt injection aimed at an AI agent has entered the tree.

WHY THIS REPOSITORY SPECIFICALLY

Several AI coding agents commit to Caterva concurrently, and they read each
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
  * mule/chapters.html         (caterva-landing, merged 2026-09-28) the
                               same three accessibility patterns reviewed in
                               mule/index.html: a visually-hidden keyboard
                               hint for screen readers, aria-hidden
                               decorative brackets, and an empty aria-hidden
                               rule span. Read at lines 41, 48 and 549.
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

THE SEVERITY COMPARISON WAS AN EQUALITY TEST (fixed 2026-09-06)

This guard asks trojan-scan for `--severity high`. The tool treats that as
a floor and answers with high AND critical. The guard then compared each
finding's severity for EQUALITY against "high" and skipped anything else --
so every critical finding was discarded in silence, for as long as this
guard has existed.

Critical is where `injection/instruction-override`,
`injection/exfiltration` and `injection/tool-abuse` live. The three most
serious rules the scanner has were the three it could not report.

Proved rather than argued: a file holding one sentence of the
discard-your-instructions form was written to the repository root.
trojan-scan rated it critical and nothing else. The guard ran, printed the
same four unrelated false positives it had been printing for weeks, and
never mentioned the file. After the fix, the same file is named at its
line. It was then removed.

Part 13's proof-of-catch could not have found this. Its payload also
tripped a high rule, so the run went red for the right file and the wrong
reason, and the missed critical sat invisible behind a passing proof. That
is the sharpest form of the shape this codebase keeps meeting: not a check
that cannot fail, but a check that passes its own test while blind to the
thing it exists for.

`--selftest` now hands `triage()` findings directly and asserts what it
does with each one, including a critical. Restoring the equality test
fails three of its seven cases.

CURRENT EXEMPTIONS (15; the verdicts live in trojan-baseline.json)

Recounted 2026-09-28 after merging main, and the number is a coincidence:
three entries came in from main (accessibility markup in the merged MuleRun
chapters) and three went out, for `Business/` files the history rewrite
removed when the repository was published. An exemption for a file that is
not in the tree can never match a finding; it is a verdict with nothing left
to apply to. Two more had their `file` corrected from `Terium/` to
`caterva/` -- the code moved in the rename and the verdict moved with it,
which matters because this guard rejects an exemption recorded against a
different file than the one the finding is in.

TWO MORE ARRIVED WITH A MERGE, 2026-09-24, and both are the same cry-wolf
idiom as the two below. Verdicts, reached by reading each in full:

  * `Terium/compose/timeseries.py` -- a comment explaining why the
    cross-correlation sums elementwise instead of going through BLAS: on
    macOS Accelerate the matmul sets floating-point flags from inside its
    own kernels, numpy attributes them to the caller, and every run printed
    RuntimeWarnings about arithmetic the function never performed. The
    flagged clause gives the reason that matters: spurious warnings cost a
    reader's attention to the real ones. It argues for keeping warnings
    meaningful, in a comment whose subject is a concrete numerical detail.
  * `Terium/tests/test_compose_library_signaling.py` -- a class docstring
    for the motif unit-checker, making the same point about a library that
    ships with a standing finding against it. Same idiom, same direction:
    it justifies why every motif must balance at composition time, since a
    dimensionally wrong rate law still integrates and still draws a smooth
    curve.

    Both are described here rather than quoted. Reproducing the wording to
    explain it re-trips the rule -- this guard's notes already record that
    happening three times, and writing this section is the fourth: the two
    sentences above were quoted verbatim on the first attempt and CI came
    back with four findings instead of two, the extra pair being these very
    lines.

Neither asserts that any code is safe, which is what the rule
`injection/trust-assertion` is looking for; both argue for MORE attention to
a warning. This idiom is house style here and will keep producing this
finding -- it is the plainest way the codebase has to state ADR 0028.

Six were added on 2026-09-06, once the criticals became visible. Three of
them are RECURSIVE -- the stage record that triaged the first scan quotes
the phrases that scan flagged, so recording a false positive reproduces
it. Two are this codebase's standard phrasing for ADR 0028's cry-wolf
reasoning, which argues that a warning firing too broadly stops being
read: it asks for more attention to a warning, not less, which is the
opposite of the rule that matches it. One is START_HERE.md's routing table
row pointing agents at their brief -- a signpost, not an instruction, and
`docs/AGENT_BRIEF.md` was read in full before that verdict.

Two findings were FIXED rather than exempted, because neither needed the
text that tripped the rule:

  * `STAGE_10_PART_13.md` quoted the synthetic attack payload verbatim.
    A probe someone composed has no documentary value in its exact
    wording, unlike real tool output, and the literal string was live
    injection text in a file other agents read. Paraphrased, with the
    edit recorded in the file.
  * `adr-0068-live-data-sources.json` used a deflection-shaped phrase as
    a mutation's replacement text. A mutation's replacement is arbitrary;
    it only has to make the NOTICE line wrong. Reworded.

The three original exemptions, all one sentence


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
CATERVA_SKIP_INJECTION_SCAN=1 to opt out explicitly -- visibly, in the
environment, not by accident.

Run directly: python scripts/check_prompt_injection.py
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Severity at which a finding fails the build. "high" only: the medium
#: tier is dominated by docs that legitimately name an AI agent, and this
#: repository's docs discuss agents constantly by nature.
FAIL_SEVERITY = "high"

#: Severity is a THRESHOLD, not a label to match.
#:
#: This guard used to test `severity != FAIL_SEVERITY` and `continue`. It
#: asks trojan-scan for `--severity high`, which the tool correctly treats
#: as a floor and answers with high AND critical -- and then the guard threw
#: every critical finding away. `injection/instruction-override`,
#: `injection/exfiltration` and `injection/tool-abuse` are all rated
#: critical, so the three most serious classes the scanner detects were the
#: three it could not report.
#:
#: Demonstrated on 2026-09-06 rather than reasoned about: a file holding one
#: sentence of the discard-your-instructions form was written to the
#: repository root. trojan-scan rated it `critical`, and nothing else. The
#: guard then ran, printed the same four unrelated false positives it had
#: been printing for weeks, and never mentioned the file at all.
#:
#: The earlier proof-of-catch (Part 13) could not reveal this. Its payload
#: combined an instruction override with a stay-quiet clause, and the second
#: of those is rated high. The guard caught the high finding, the run went
#: red, and the critical finding beside it was never noticed -- so a passing
#: proof concealed a blind spot in the very thing it was proving.
#:
#: Both payloads are PARAPHRASED here on purpose. Quoting either verbatim
#: makes this file trip the rules it exists to enforce, which is what
#: happened on the first attempt at this comment, and is the same trap the
#: commandResolve.ts baseline entry records.
SEVERITY_RANK = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

#: Generous: the scan walks ~750 files and took 27s on a slow mount.
SCAN_TIMEOUT_S = 300

SKIP_ENV = "CATERVA_SKIP_INJECTION_SCAN"

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
def triage(
    findings: list, baseline: dict[str, dict[str, str]]
) -> tuple[list[str], list[str]]:
    """Split scanner findings into violations and reviewed exemptions.

    Lifted out of `check()` on 2026-09-06 so it can be exercised without a
    scan. It used to be an inline loop, and the severity comparison inside
    it -- an equality test against "high" -- discarded every `critical`
    finding for as long as this guard has existed. Nothing could have
    caught that: there was no way to hand this logic a finding and ask what
    it did with it. `--selftest` now does exactly that.

    Returns (violations, exempted); the caller decides what to print.
    """
    violations: list[str] = []
    exempted: list[str] = []

    for finding in findings:
        if not isinstance(finding, dict):
            continue
        severity = str(finding.get("severity", "")).lower()
        rank = SEVERITY_RANK.get(severity)
        if rank is None:
            # An unrecognised severity is not a quiet skip. The tool may
            # have added a level, and silently dropping it is how the
            # critical findings were lost in the first place.
            violations.append(
                f"{finding.get('file', '?')}:{finding.get('line', '?')} "
                f"reported severity {severity!r}, which this guard does not "
                f"recognise. Refusing to decide it is safe. Add it to "
                f"SEVERITY_RANK once someone has read the tool's docs."
            )
            continue
        if rank < SEVERITY_RANK[FAIL_SEVERITY]:
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

        # The fingerprint is PRINTED, because the sentence below tells the
        # reader to record a verdict in trojan-baseline.json and that file is
        # keyed on exactly this value. Without it the instruction cannot be
        # followed: the only other way to obtain a fingerprint is to re-run
        # the scanner and read its raw JSON, which is precisely what someone
        # reading a CI log cannot do. Measured 2026-09-24: two findings
        # arrived with a merge, both benign, and clearing them needed a
        # round trip through CI purely to learn two hex strings.
        violations.append(
            f"{location}:{line} [{rule}] fingerprint={fingerprint or '?'} "
            f"{message} -- text aimed at an AI "
            "reader rather than a human one. Several agents commit to this "
            "repository and read each other's files, so prose is an "
            "execution surface here."
        )


    return violations, exempted



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

    violations, exempted = triage(findings, baseline)

    # Printed every run, never silently dropped. A baseline that disappears
    # from the output is indistinguishable from no findings at all, which
    # is how an exemption list stops being read.
    if exempted:
        print(f"Reviewed exemptions applied ({len(exempted)}):")
        for line in exempted:
            print(f"  {line}")
        print()

    return violations



def selftest() -> int:
    """Hand `triage()` findings and check what it does with them.

    Written on 2026-09-06 because the defect it pins was undetectable
    before it existed. The severity comparison was an equality test against
    "high", so every `critical` finding -- instruction-override,
    exfiltration, tool-abuse, the three most serious rules the scanner has
    -- was skipped in silence. A real payload was planted in the repository
    root to confirm it: trojan-scan rated it critical, and this guard
    reported the same four unrelated findings it had been reporting for
    weeks without ever naming the file.

    The August proof-of-catch could not have found this. Its payload also
    tripped a `high` rule, so the run went red for the wrong reason and the
    missed critical was invisible behind a passing proof.
    """
    def finding(**kw):
        base = {
            "severity": "high",
            "file": "some/file.md",
            "line": 1,
            "ruleId": "injection/trust-assertion",
            "fingerprint": "f" * 16,
            "message": "m",
        }
        base.update(kw)
        return base

    baseline = {
        "abc123": {"file": "some/file.md", "reason": "reviewed and benign"},
    }

    cases: list[tuple[str, list, dict, bool, str]] = [
        # (label, findings, baseline, expect_violation, needle)
        (
            "a critical finding is reported",
            [finding(severity="critical", ruleId="injection/instruction-override")],
            {},
            True,
            "instruction-override",
        ),
        (
            "a high finding is reported",
            [finding(severity="high")],
            {},
            True,
            "trust-assertion",
        ),
        (
            "a medium finding is not",
            [finding(severity="medium")],
            {},
            False,
            "",
        ),
        (
            "an unrecognised severity is reported, not skipped",
            [finding(severity="catastrophic")],
            {},
            True,
            "does not recognise",
        ),
        (
            "a reviewed exemption suppresses its own finding",
            [finding(fingerprint="abc123")],
            baseline,
            False,
            "",
        ),
        (
            "an exemption recorded against another file does NOT suppress",
            [finding(fingerprint="abc123", file="a/different/file.md")],
            baseline,
            True,
            "recorded against",
        ),
        (
            "a critical finding is not suppressed by severity alone",
            [finding(severity="critical", ruleId="injection/exfiltration")],
            baseline,
            True,
            "exfiltration",
        ),
    ]

    ok = True
    for label, findings, base, expect_violation, needle in cases:
        violations, exempted = triage(findings, base)
        got = bool(violations)
        matched = (not needle) or any(needle in v for v in violations)
        passed = got == expect_violation and matched
        print(f"  {'ok    ' if passed else 'FAILED'} {label}")
        if not passed:
            ok = False
            print(
                f"           expected violation={expect_violation}"
                + (f" mentioning {needle!r}" if needle else "")
                + f"; got violations={violations!r} exempted={exempted!r}",
                file=sys.stderr,
            )

    if ok:
        print(f"selftest OK: {len(cases)} cases")
        return 0
    print("SELFTEST FAILED", file=sys.stderr)
    return 1


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()

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