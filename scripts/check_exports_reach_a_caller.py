#!/usr/bin/env python3
"""
check_exports_reach_a_caller.py

Every exported engine capability is either called by the product, or listed
as deliberately not.

WHY
---
This defect class has now been found by hand three times, and never
systematically:

1. `sbml-builder.ts` "shipped with 424 lines and a full test file, and
   nothing in the product called it -- an orphan that looked covered because
   it had tests." Wired by hand; the sentence is still in
   `inhibitionModels.test.ts`.

2. `rankModelsByFit` -- the function answering *which mechanism does my
   bench data support* -- had no production caller for the life of the
   engine. ADR 0087. It is also where ADR 0060's defect sat unnoticed: a
   model that never ran ranking FIRST. **A defect in code nobody calls has
   no symptoms.**

3. `compareModelPair`, still unwired, recorded rather than fixed because
   inventing a caller to satisfy a guard is worse than the gap.

Three by hand is the argument for a check.

WHAT IT IS, AND WHAT IT IS NOT
------------------------------
This is [ADR 0045]'s boundary guard one level up. That one walks
`KineticResult` FIELDS from the resolver to a rendering surface, and has
nothing to say about an exported FUNCTION nobody calls. Same question --
*was this computed for anyone?* -- at the granularity of a capability rather
than a value.

It is deliberately NOT a dead-code detector. An orphan is often the right
answer: `kinetic-models.ts` exports rate equations that are unwired on
purpose, because wiring them "would have been a FIFTH implementation of
enzyme kinetics". The point is that such a decision should be **recorded**,
not inferred from silence.

CONSERVATIVE BY CONSTRUCTION
----------------------------
A symbol counts as called if its name appears anywhere in any non-test
source file other than the one defining it. That over-counts callers, which
under-reports orphans. The bias is deliberate: a false orphan wastes a
person's time and teaches them to distrust the check, while a missed orphan
is the status quo this improves on gradually.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Where a "capability" lives. The engine computes things; storage shapes
#: them for delivery. Both are places where an orphan means a user cannot
#: reach something the project believes it offers.
SCAN_DIRS = [REPO_ROOT / "src" / "engine", REPO_ROOT / "src" / "storage"]

#: Anything under src/ that is not a test may be a caller.
CALLER_ROOT = REPO_ROOT / "src"

BASELINE = REPO_ROOT / "docs" / "unwired-exports.txt"

EXPORT_RE = re.compile(r"^export (?:async )?function (\w+)", re.MULTILINE)


def is_test(path: Path) -> bool:
    return "__tests__" in path.parts or ".test." in path.name or ".spec." in path.name


def read_baseline() -> dict[str, str]:
    """symbol -> the reason it is deliberately unwired."""
    if not BASELINE.exists():
        return {}
    out: dict[str, str] = {}
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        symbol, _, reason = stripped.partition("#")
        symbol = symbol.strip()
        if symbol:
            out[symbol] = reason.strip()
    return out


def selftest() -> int:
    """Reproduce, in a temporary tree, the three scenarios this guard claims.

    They were verified by hand when the guard was written and then not
    encoded, which is the failure this project has recorded three times
    under a different name: a property defended only in prose is a property
    that stops being checked (ADR 0058's M3, ADR 0072's set file, ADR 0079's
    comment-stripper).

    Hand-verification is evidence about one moment. A self-test is evidence
    every time the build runs.
    """
    import tempfile

    global SCAN_DIRS, CALLER_ROOT, BASELINE, REPO_ROOT
    saved = (SCAN_DIRS, CALLER_ROOT, BASELINE, REPO_ROOT)
    failures = 0

    print("Self-test: the three scenarios this guard claims to catch.\n")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = root / "src" / "engine"
            engine.mkdir(parents=True)
            (root / "docs").mkdir()

            REPO_ROOT = root
            SCAN_DIRS = [engine]
            CALLER_ROOT = root / "src"
            BASELINE = root / "docs" / "unwired-exports.txt"

            (engine / "thing.ts").write_text(
                "export function calledByProduct(): number { return 1; }\n"
                "export function neverCalled(): number { return 2; }\n",
                encoding="utf-8",
            )
            (root / "src" / "app.ts").write_text(
                "import { calledByProduct } from './engine/thing';\n"
                "calledByProduct();\n",
                encoding="utf-8",
            )

            cases = [
                ("an unrecorded orphan fails", "", 1),
                ("recording it passes", "neverCalled  # deliberate\n", 0),
                (
                    "a baselined symbol that IS called fails",
                    "neverCalled  # deliberate\ncalledByProduct  # wrong\n",
                    1,
                ),
            ]
            for label, baseline_text, expected in cases:
                BASELINE.write_text(baseline_text, encoding="utf-8")
                got = main()
                ok = got == expected
                failures += 0 if ok else 1
                print(f"  [{'ok' if ok else 'FAIL'}] {label} (exit {got}, want {expected})")

            # A guard that examined nothing must not pass. Same rule as the
            # citation guard that parsed zero entries and printed OK.
            SCAN_DIRS = [root / "src" / "nonexistent"]
            got = main()
            ok = got == 1
            failures += 0 if ok else 1
            print(f"  [{'ok' if ok else 'FAIL'}] an empty scan fails rather than passing "
                  f"(exit {got}, want 1)")
    finally:
        SCAN_DIRS, CALLER_ROOT, BASELINE, REPO_ROOT = saved

    print()
    if failures:
        print(f"FAIL: {failures} self-test case(s) failed.", file=sys.stderr)
        return 1
    print("OK: the guard catches an orphan, accepts a recorded one, and refuses "
          "a stale entry.")
    return 0


def main() -> int:
    sources = [
        p for d in SCAN_DIRS if d.exists() for p in sorted(d.rglob("*.ts"))
        if not is_test(p) and not p.name.endswith(".d.ts")
    ]
    if not sources:
        # A guard that examined nothing must not print OK.
        print("FAIL: found no engine/storage sources to check.", file=sys.stderr)
        print(f"  Looked in: {[str(d) for d in SCAN_DIRS]}", file=sys.stderr)
        return 1

    exports: dict[str, Path] = {}
    for path in sources:
        for match in EXPORT_RE.finditer(path.read_text(encoding="utf-8", errors="replace")):
            exports[match.group(1)] = path

    if not exports:
        print("FAIL: found no exported functions; the matcher is probably wrong.",
              file=sys.stderr)
        return 1

    callers = {
        p: p.read_text(encoding="utf-8", errors="replace")
        for p in CALLER_ROOT.rglob("*.ts")
        if not is_test(p)
    }

    # Three states, not two.
    #
    # "Called somewhere else" / "called only inside its own file" / "never
    # called at all" are different findings with different fixes, and a
    # check that merges the last two tells someone to WIRE a function whose
    # real problem is that it should not be EXPORTED. Same discipline as
    # resolved / unresolvable / not_reported.
    orphans: list[tuple[str, Path]] = []
    internal_only: list[tuple[str, Path]] = []
    for symbol, defined_in in sorted(exports.items()):
        word = re.compile(rf"\b{re.escape(symbol)}\b")
        if any(p != defined_in and word.search(text) for p, text in callers.items()):
            continue
        own = callers.get(defined_in, defined_in.read_text(encoding="utf-8", errors="replace"))
        # More than one mention in its own file means the definition plus at
        # least one call: live code with a surplus `export`.
        if len(word.findall(own)) > 1:
            internal_only.append((symbol, defined_in))
        else:
            orphans.append((symbol, defined_in))

    baseline = read_baseline()
    unrecorded = [(s, p) for s, p in orphans if s not in baseline]
    orphan_names = {s for s, _ in orphans}
    stale = sorted(s for s in baseline if s not in orphan_names)

    print(f"Exported functions in engine/storage: {len(exports)}")
    print(f"  called by the product:              "
          f"{len(exports) - len(orphans) - len(internal_only)}")
    print(f"  called only inside their own file:  {len(internal_only)}")
    print(f"  never called, recorded as such:     {len(orphans) - len(unrecorded)}")

    if internal_only:
        # Not a failure. An `export` nobody imports is a smaller problem than
        # a capability nobody reaches, and saying so is more useful than
        # demanding a caller for something already in use.
        print("\nExported but used only inside their own file "
              f"({len(internal_only)}) -- the export is surplus, not the function:")
        for symbol, path in internal_only:
            print(f"  - {symbol}  ({path.relative_to(REPO_ROOT)})")

    problems = False

    if unrecorded:
        problems = True
        print(f"\nExported and never called ({len(unrecorded)}):", file=sys.stderr)
        for symbol, path in unrecorded:
            print(f"  - {symbol}  ({path.relative_to(REPO_ROOT)})", file=sys.stderr)
        print(
            "\nAn exported function nothing calls was computed for nobody. That is\n"
            "ADR 0039's defect at the scale of a capability, and ADR 0087 is what it\n"
            "cost: the function answering 'which mechanism does my bench data\n"
            "support' went unwired for the life of the engine, and ADR 0060's defect\n"
            "sat inside it symptomless, because code nobody calls has no symptoms.\n"
            "\n"
            "Either wire it, or record the decision with its reason in\n"
            f"    {BASELINE.relative_to(REPO_ROOT)}\n"
            "\n"
            "Recording is a legitimate answer and often the right one -- inventing a\n"
            "caller to satisfy a check is worse than the gap. What is not legitimate\n"
            "is leaving it to be inferred from silence.",
            file=sys.stderr,
        )

    if stale:
        problems = True
        print(f"\nRecorded as unwired but now called ({len(stale)}):", file=sys.stderr)
        for symbol in stale:
            print(f"  - {symbol}", file=sys.stderr)
        print(
            "\nRemove these. A list that can be added to but never emptied records a\n"
            "problem instead of fixing it, and the count above stops meaning anything.",
            file=sys.stderr,
        )

    if problems:
        return 1

    print("\nOK: every exported capability is called, or recorded as deliberately not.")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
