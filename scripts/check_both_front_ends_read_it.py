#!/usr/bin/env python3
"""Does every finding reach BOTH front ends, or only the one it was built on?

WHY THIS EXISTS
---------------
This defect has now been found by hand twice, one pass apart, and the
second time only because the first fix made a leaf name collide:

1. **ADR 0106.** `literatureCandidates` -- the papers PubMed and CORE turn
   up when BRENDA holds nothing -- was emitted by the runner and read by
   nothing on the API path. A student was told the literature had nothing
   while the system held the list.

2. **ADR 0109.** The same field, on the CLI path, one pass later. Worse
   there: `commandResolve` printed *"BRENDA and PubMed were searched and
   returned nothing"*, which is FALSE precisely when the fallback worked.

Two by hand is not yet the three this project usually waits for, and the
reason to check now rather than at three is that the second instance was
found by ACCIDENT. Nothing was looking.

WHAT IT MEASURES
----------------
The runner emits one JSON document. Two independent consumers read it:

    science_agent_runner.py
        |-> Science-Agent-Pipeline/.../lib/*.ts   (API, web)
        `-> src/literature/*.ts, src/cli/*.ts     (CLI)

A key read by one and not the other is a finding that reaches half the
users. That is not always wrong -- the CLI has no HTTP response to annotate
-- but it should be a DECISION rather than an accident, which is the same
contract as `docs/undelivered-fields-baseline.txt`.

WHY WHOLE-TREE SCOPE, STATED BECAUSE IT WAS GOT WRONG FIRST
-----------------------------------------------------------
The first version read `scienceAgent.ts` and `literatureResolver.ts` alone
and reported 34 keys as one-sided. Nine of those were the matcher's fault:
these pipes span several files each, and `Effector`'s fields live in
`provenance.ts` while `scienceAgent.ts` merely imports the type. A matcher
whose scope is narrower than the thing it measures does not report "I could
not see" -- it reports "it is not there" (ADR 0102).

CONSERVATIVE BY CONSTRUCTION
----------------------------
A key counts as read if its name appears in any non-test file on that side.
That over-counts readers and so UNDER-reports one-sided findings. Deliberate:
a false accusation wastes somebody's time and teaches them to distrust the
check, while a missed one is the status quo this improves on gradually.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "docs" / "one-sided-findings.txt"

#: Every non-test file on each side of the runner's output.
API_GLOBS = ["Science-Agent-Pipeline/artifacts/api-server/src/lib/*.ts"]
CLI_GLOBS = ["src/literature/*.ts", "src/cli/*.ts"]


def _side_source(globs: list[str]) -> str:
    parts = []
    for pattern in globs:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if "__tests__" in str(path) or ".test." in path.name:
                continue
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def _reads(source: str, key: str) -> bool:
    return bool(re.search(rf"\b{re.escape(key)}\b", source))


def read_baseline() -> dict[str, str]:
    if not BASELINE.exists():
        return {}
    out: dict[str, str] = {}
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, reason = stripped.partition("#")
        if key.strip():
            out[key.strip()] = reason.strip()
    return out


def emitted_top_level_keys() -> set[str] | None:
    """The keys the runner actually emits, by running it.

    Reuses `check_findings_reach_a_surface.py`'s probe rather than
    re-deriving it. Two implementations of "what does the runner emit" is
    ADR 0027's defect, and this guard exists because of a variant of that.
    """
    spec = importlib.util.spec_from_file_location(
        "reachability", REPO_ROOT / "scripts" / "check_findings_reach_a_surface.py"
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    saved_argv = sys.argv
    sys.argv = ["reachability"]
    try:
        spec.loader.exec_module(module)
    except SystemExit:
        return None
    finally:
        sys.argv = saved_argv
    keys = module._emitted_keys()
    return None if keys is None else {k for k in keys if "." not in k}


def selftest() -> int:
    """Drive the guard through its refusals, with the failures present.

    WHY THIS HAD TO EXIST BEFORE THE GUARD COULD BE WIRED
    -----------------------------------------------------
    Mutation testing this guard on the real tree returned **0 caught, 3 not
    caught**, and the guard was not what was wrong. Every mutation deletes a
    failure path, and on the real tree the guard is GREEN -- every one-sided
    key is listed, nothing is stale, both sides are non-empty. Removing a
    check that is not firing changes no output, so no verdict can be had.

    Same shape as ADR 0100's G2 and ADR 0104's T3: a mutation that is a
    no-op against the current input cannot be caught, and recording it as
    caught would be a verdict the harness never established.

    So the fix was never a better mutation. It is an input where the
    refusals fire. With this in place the three mutations become
    expressible, and the guard can go into a harness everyone runs --
    which it deliberately did not, until now.
    """
    import tempfile

    global REPO_ROOT, BASELINE, API_GLOBS, CLI_GLOBS, emitted_top_level_keys
    saved = (REPO_ROOT, BASELINE, API_GLOBS, CLI_GLOBS, emitted_top_level_keys)
    failures = 0

    print("Self-test: the refusals, with something to refuse.\n")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "api").mkdir()
            (root / "cli").mkdir()
            (root / "docs").mkdir()
            REPO_ROOT = root
            BASELINE = root / "docs" / "one-sided-findings.txt"
            API_GLOBS = ["api/*.ts"]
            CLI_GLOBS = ["cli/*.ts"]

            # `sharedKey` is read on both sides; `apiOnlyKey` on one.
            (root / "api" / "a.ts").write_text(
                "const x = r.sharedKey; const y = r.apiOnlyKey;\n", encoding="utf-8"
            )
            (root / "cli" / "c.ts").write_text(
                "const x = r.sharedKey;\n", encoding="utf-8"
            )

            def run(label: str, want: int) -> None:
                nonlocal failures
                buf_out, buf_err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(
                    buf_err
                ):
                    got = main()
                ok = got == want
                failures += 0 if ok else 1
                print(f"  [{'ok' if ok else 'FAIL'}] {label} (exit {got}, want {want})")

            emitted_top_level_keys = lambda: {"sharedKey", "apiOnlyKey"}  # noqa: E731

            BASELINE.write_text("", encoding="utf-8")
            run("a NEW one-sided finding fails", 1)

            BASELINE.write_text("apiOnlyKey  # deliberate\n", encoding="utf-8")
            run("listing it in the baseline passes", 0)

            # The shrinking-baseline rule. `selected` was written into the
            # real baseline and rejected exactly this way, because it is
            # also an ordinary local variable name on both sides.
            BASELINE.write_text(
                "apiOnlyKey  # deliberate\nsharedKey  # wrong, it is read by both\n",
                encoding="utf-8",
            )
            run("a baselined key that is no longer one-sided fails", 1)

            # A guard that examined nothing must not print OK -- the same
            # trap as the citation guard that parsed zero entries. Without
            # this, a renamed directory would silently make every key look
            # present, or every key look absent.
            #
            # THE BASELINE MUST LIST EVERYTHING FOR THIS CASE TO MEAN
            # ANYTHING. With `sharedKey` unlisted, an empty CLI side makes it
            # look one-sided and the unreviewed check fails the build --
            # so deleting the empty-side check changed no output and the
            # mutation came back NOT CAUGHT. The guard was defended twice
            # and the weaker defence was doing the work.
            #
            # Listing every key removes that cover. Now an empty side
            # produces "everything one-sided, everything accounted for",
            # which is exactly the silent OK on a comparison that never
            # happened -- and only the empty-side check stands between the
            # guard and reporting it.
            BASELINE.write_text(
                "apiOnlyKey  # deliberate\nsharedKey  # deliberate\n", encoding="utf-8"
            )
            CLI_GLOBS = ["nonexistent/*.ts"]
            run("an empty side fails even when the baseline covers every key", 1)
            CLI_GLOBS = ["cli/*.ts"]
            BASELINE.write_text("apiOnlyKey  # deliberate\n", encoding="utf-8")

            emitted_top_level_keys = lambda: set()  # noqa: E731
            run("no emitted keys fails rather than passing vacuously", 1)

            # The probe returning None means the runner could not be run at
            # all. "Could not check" must never render as "checked, fine".
            emitted_top_level_keys = lambda: None  # noqa: E731
            run("an unrunnable probe fails rather than reporting OK", 1)
    finally:
        REPO_ROOT, BASELINE, API_GLOBS, CLI_GLOBS, emitted_top_level_keys = saved

    print()
    if failures:
        print(f"FAIL: {failures} self-test case(s) failed.", file=sys.stderr)
        return 1
    print("OK: a new one-sided finding fails, the baseline must shrink, and")
    print("    a comparison that could not be made is never reported as clean.")
    return 0


def main() -> int:
    keys = emitted_top_level_keys()
    if keys is None:
        # Not measurable is not "fine". The probe runs the real runner, and
        # if it cannot, this guard has checked nothing.
        print(
            "FAIL: could not run the runner to see what it emits, so nothing "
            "was compared.",
            file=sys.stderr,
        )
        return 1
    if not keys:
        print("FAIL: the runner emitted no top-level keys.", file=sys.stderr)
        return 1

    api_src = _side_source(API_GLOBS)
    cli_src = _side_source(CLI_GLOBS)
    if not api_src or not cli_src:
        print(
            "FAIL: one side of the comparison is empty, so every key would "
            "look one-sided.",
            file=sys.stderr,
        )
        return 1

    baseline = read_baseline()
    one_sided: dict[str, str] = {}
    for key in sorted(keys):
        in_api, in_cli = _reads(api_src, key), _reads(cli_src, key)
        if in_api and in_cli:
            continue
        if not in_api and not in_cli:
            one_sided[key] = "read by NEITHER front end"
        else:
            one_sided[key] = f"read by the {'API' if in_api else 'CLI'} only"

    unreviewed = {k: v for k, v in one_sided.items() if k not in baseline}
    stale = sorted(k for k in baseline if k not in one_sided)

    print(f"Top-level keys the runner emits:  {len(keys)}")
    print(f"  read by both front ends:        {len(keys) - len(one_sided)}")
    print(f"  one-sided:                      {len(one_sided)} "
          f"({len(one_sided) - len(unreviewed)} listed, {len(unreviewed)} new)")

    problems = False
    if unreviewed:
        problems = True
        print(f"\nFindings that reach one front end and not the other ({len(unreviewed)}):",
              file=sys.stderr)
        for key, why in sorted(unreviewed.items()):
            print(f"  {key}\n      {why}", file=sys.stderr)
        print(
            "\nA finding computed once and rendered to half the users is the\n"
            "defect of ADR 0106 and ADR 0109 -- found by hand twice, and the\n"
            "second time only by accident.\n"
            "\nWire it through, or record the decision with a reason:\n"
            f"    {BASELINE.relative_to(REPO_ROOT)}",
            file=sys.stderr,
        )

    if stale:
        problems = True
        print(
            f"\nBaseline entries that are no longer one-sided ({len(stale)}):",
            file=sys.stderr,
        )
        for key in stale:
            print(f"  - {key}", file=sys.stderr)
        print(
            "\nRemove them. A list that can be added to but never emptied\n"
            "records a problem instead of fixing it.",
            file=sys.stderr,
        )

    if problems:
        return 1
    # The wording matters. An earlier draft said "or is recorded as
    # deliberately reaching one", which is the contract of
    # docs/undelivered-fields-baseline.txt and NOT of this file. Two of the
    # entries were checked; the rest are counted. Claiming they were
    # decided is the overclaim this guard was written to find.
    listed = len(one_sided)
    print(f"\nOK: no NEW one-sided finding. {listed} are listed as outstanding")
    print("    debt, which is not a statement that anyone reviewed them.")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
