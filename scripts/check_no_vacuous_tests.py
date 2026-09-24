"""Guard that no test can pass without asserting anything.

THE DEFECT CLASS

    it("rejects a bad value", () => {
      const result = doThing();
      if (result) {
        expect(result.ok).toBe(false);   // <- only runs when result is truthy
      }
    });

When the guard is false the body is skipped, the test passes, and it has
verified nothing. It reports green in exactly the circumstances where it
would have been most useful.

This repository has produced it repeatedly:

  * `cachedProvenance.test.ts` returned early on a failed poll, skipping all
    three of its assertions -- silently, in precisely the conditions where
    the regression it guarded was most likely (Stage 10 Part 5).
  * `kcatProvenance.test.ts` wraps its only assertion in `if (provenance)`,
    and provenance is `undefined` for those keys BY DESIGN, so the assertion
    never executes at all.
  * A regression test I wrote in Part 12 passed against the very bug it was
    written for, because an unreachable registry made it bail before the
    assertion.

A test that cannot fail is worse than a missing test, because the missing
one is visibly missing.

The same defect has a second shape, which accommodates rather than skips:

    it("rejects a bad value", () => {
      if (result.trajectory.length === 0) {
        expect(result.validated).toBe(false);
      } else {
        expect(result.validated).toBe(true);
      }
    });

Every branch asserts, so nothing is skipped -- and the test still cannot
fail, because it has an answer ready for both outcomes and states no
expectation about which one should occur. Both shapes are the same thing: a
test with no way to go red.

WHAT COUNTS

A test body where EVERY `expect(` sits inside a conditional -- counting an
`else` branch as part of the conditional it belongs to. A test with
assertions both inside and outside a conditional is fine: the outer ones
still run. So is a conditional used for setup around assertions that follow
it.

The check is deliberately syntactic and conservative: it looks at brace
depth relative to `if`/`&&`-guards within a single `it(...)`/`test(...)`
body. It will not catch every vacuous test (a `for` over an empty array has
the same effect), and it is tuned to avoid false positives, because a guard
that cries wolf gets suppressed and then catches nothing at all.

ALLOWLIST

A test may legitimately assert conditionally when the environment decides
what is knowable -- e.g. asserting a live registry's answer only when the
network is up. Those must be listed explicitly in ALLOWED, with a reason,
so an exemption is a decision somebody made rather than a pattern that
slipped through.

Run directly: python scripts/check_no_vacuous_tests.py
"""

from __future__ import annotations

import ast
import os
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

SEARCH_ROOTS = [
    "src",
    "Science-Agent-Pipeline/artifacts/api-server/src",
]

SKIP_PARTS = {"node_modules", "dist", "coverage", ".git", "__pycache__"}

TEST_FILE = re.compile(r".*\.(test|spec)\.tsx?$")

#: `it("...", ...)` / `test("...", ...)`, capturing the name.
TEST_START = re.compile(r"""\b(?:it|test)(?:\.\w+)?\s*\(\s*['"`](.+?)['"`]""")

#: Tests whose conditional assertions are deliberate, with the reason.
#: Empty on purpose: every instance found so far was a defect.
ALLOWED: dict[str, str] = {}


def _test_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root_name in SEARCH_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for current, directories, names in os.walk(root):
            directories[:] = [d for d in directories if d not in SKIP_PARTS]
            here = pathlib.Path(current)
            for name in names:
                if TEST_FILE.match(name):
                    files.append(here / name)
    return sorted(files)


def _scan_body(body: str) -> tuple[int, int]:
    """Return (total expects, expects guarded by a conditional).

    Tracks brace depth, remembering the depth at which each `if (` opened.
    An `expect(` deeper than an open conditional is guarded.
    """
    total = 0
    guarded = 0
    depth = 0
    conditional_depths: list[int] = []
    index = 0

    while index < len(body):
        char = body[index]

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            closed = [d for d in conditional_depths if d >= depth]
            conditional_depths = [d for d in conditional_depths if d < depth]

            # `} else {` continues the same conditional. An else-branch
            # assertion is exactly as skippable as an if-branch one, and a
            # test whose only assertions are
            #
            #     if (cond) { expect(A) } else { expect(B) }
            #
            # cannot fail at all: it accommodates both outcomes and so states
            # no expectation about which should happen. Without this, the
            # closing brace would drop the conditional and the else-branch
            # assertion would be miscounted as unconditional.
            if closed and re.match(r"\s*else\b", body[index + 1 :]):
                conditional_depths.append(depth)
        elif (
            body.startswith("if", index)
            and re.match(r"if\s*\(", body[index:])
            # Word boundary on the left, so an identifier ending in "if"
            # followed by a paren -- `notif (x)`, `verif (y)` -- is not read
            # as a conditional. Without this the guard would invent
            # conditionals and report tests that are perfectly fine, and a
            # guard that cries wolf gets suppressed and then catches nothing.
            and (index == 0 or not (body[index - 1].isalnum() or body[index - 1] in "_$."))
        ):
            # The block this `if` opens will be at depth+1.
            conditional_depths.append(depth)
        elif body.startswith("expect(", index):
            total += 1
            if any(depth > d for d in conditional_depths):
                guarded += 1

        index += 1

    return total, guarded


def _extract_tests(source: str) -> list[tuple[str, int, str]]:
    """(name, line, body) for each test in the file."""
    tests: list[tuple[str, int, str]] = []

    for match in TEST_START.finditer(source):
        name = match.group(1)
        line = 1 + source[: match.start()].count("\n")

        # Walk from the first `{` after the match to its closing brace.
        brace = source.find("{", match.end())
        if brace == -1:
            continue
        depth = 0
        end = brace
        for index in range(brace, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        tests.append((name, line, source[brace : end + 1]))

    return tests


#: Roots holding the pytest suites. Separate from SEARCH_ROOTS because the
#: Python scan is AST-based, not brace-based.
PYTHON_ROOTS = ["Tests", "Terium/tests"]

PYTHON_TEST_FILE = re.compile(r"^test_.*\.py$")

#: Python tests whose every assertion sits behind an `if`, recorded rather
#: than fixed here.
#:
#: WHY A BASELINE AND NOT A CLEAN SWEEP
#: This guard was TypeScript-only for its whole life, so the Python suites
#: were never scanned -- and "OK: every test has at least one assertion that
#: always runs" was a claim about a third of the tests it appeared to cover.
#: Turning it on found these eight. They belong to several agents' modules
#: and fixing them blind would be worse than recording them: some are
#: genuinely conditional for a reason their author knows.
#:
#: The list may SHRINK, never grow. Anything not listed here is a failure.
#:
#: EVERY ENTRY MUST CARRY A REASON, and the four that remain do. That is the
#: difference between a debt and a decision:
#:
#:   * a bare key says only "this is known", which is how an exemption
#:     outlives the thing that justified it;
#:   * a reason says whether the test is conditional BY DESIGN -- BRENDA
#:     often reports no pH, so "assert it where reported" is the claim --
#:     or merely conditional and awaiting a fix.
#:
#: It started at eight. Four were fixed rather than excused, each with the
#: mutation that proves the fix:
#:
#:   test_bibtex_specials_in_a_title_are_escaped   two of six parameters
#:       asserted nothing, and they were the two hardest cases (`{braces}`,
#:       `back\slash` -- the ones escaping to macros rather than a backslash
#:       prefix). Coverage was inverted from the risk.
#:   test_the_commentary_is_never_the_substrate    would have gone green if
#:       the parser stopped capturing commentary, which IS the regression it
#:       names.
#:   test_trypsin_classic_substrates_are_typed_classic   would have gone
#:       green if no classic substrate parsed at all.
#:   test_effective_size_harmonic_mean_never_exceeds_arithmetic   its branch
#:       was on the INPUT rather than an unknown outcome, so it could still
#:       fail -- but harmonic <= arithmetic holds for every series, and
#:       saying so unconditionally is stronger than branching around it.
PYTHON_BASELINE: dict[str, str] = {
    "Tests/test_turnover_numbers.py::test_variants_sharing_a_value_are_kept_apart": (
        "asserts only when two entries share a kcat value, which is the "
        "situation it exists to judge. TestTurnoverFixtures also runs "
        "test_the_fixture_parses_to_at_least_one_entry over the same "
        "`fixture` param, so an empty parse fails there rather than "
        "passing silently here"
    ),
    "Tests/test_turnover_numbers.py::test_assay_conditions_are_parsed_where_reported": (
        "conditional BY NAME -- BRENDA often reports no pH or temperature, "
        "and the test's claim is that any value present is physically "
        "sensible. Requiring a reported value in every fixture would "
        "contradict what it checks. Non-emptiness is covered by the "
        "sibling test_the_fixture_parses_to_at_least_one_entry"
    ),
    "Tests/test_popgen_resolver.py::test_mutation_rate_is_positive": (
        "module-level skip when stdpopsim is absent (ADR 0061 made it "
        "opt-in), so the body does not run silently -- but when it DOES "
        "run and the resolver reports not-found, it asserts nothing. "
        "HOW TO RETIRE THIS ENTRY: on a machine with stdpopsim installed, "
        "confirm resolve_mutation_rate('Homo sapiens').found is True, then "
        "change `if result.found:` to `assert result.found, "
        "result.search_log`. Homo sapiens is stdpopsim's best-supported "
        "species; if it does not resolve, that is the bug this test should "
        "have been finding. Not done here because stdpopsim is not "
        "installed in this environment and PyPI is unreachable, and a test "
        "changed without being run is how a green suite starts lying"
    ),
    "Tests/test_popgen_resolver.py::test_mutation_rate_is_plausible": (
        "same module-level skip, and the same retirement condition, as "
        "test_mutation_rate_is_positive above"
    ),
}


class _PythonAsserts(ast.NodeVisitor):
    """Counts assertions reachable with and without passing through an `if`.

    Loops count as unconditional, matching the TypeScript half. This guard's
    own docstring already declines to judge `for` over a possibly-empty
    collection, and applying a stricter rule to Python than to TypeScript
    would make the two halves mean different things.
    """

    def __init__(self) -> None:
        self.depth = 0
        self.free = 0
        self.guarded = 0

    def _count(self) -> None:
        if self.depth:
            self.guarded += 1
        else:
            self.free += 1

    def visit_If(self, node: ast.If) -> None:
        self.depth += 1
        for child in node.body + node.orelse:
            self.visit(child)
        self.depth -= 1
        self.visit(node.test)

    def visit_Assert(self, node: ast.Assert) -> None:
        self._count()

    def visit_With(self, node: ast.With) -> None:
        if any("raises" in ast.dump(item.context_expr) for item in node.items):
            self._count()
        self.generic_visit(node)


# ============================================================================
# THE THIRD SHAPE: a filter asserted empty, over a source that may be empty
# ============================================================================
#
#     offenders = [f for f in report.findings if f.severity in DISAGREEMENT]
#     assert not offenders
#
# Every assertion runs, no branch is skipped, and both checks above are
# satisfied. It still cannot fail, for a third reason: the result is empty
# whether the package is healthy OR the filter matches nothing at all. A
# misspelled severity, a renamed attribute, an upstream that returned no
# findings -- each produces the same green.
#
# This is the shape the module docstring above already declines to judge
# ("a `for` over an empty array has the same effect"), and it was found in
# this repository the way the other two were: in a sweep across eleven
# models that reported zero disagreements. Mutating the filter to match
# nothing left it green. The fix was to pin the source non-empty and to
# drive the filter with something that does match.
#
# WHY IT ONLY LOOKS AT RUNTIME-PRODUCED SOURCES
#
# The first version of this check flagged twenty-three tests and most were
# false. It objected to `[e for e in range(doc.getNumErrors())]`, to
# comprehensions over `self`, over imported module objects, and over
# module-level constants written out as literal tuples five lines above --
# all of them visibly non-empty, or non-empty by construction, to anyone
# reading the file.
#
# That is ADR 0028's failure exactly: a check that fires too broadly stops
# being read, and then it catches nothing. So the rule now only looks at
# sources whose emptiness a reader genuinely cannot see:
#
#   * a fixture -- a parameter of the test function, produced at runtime;
#   * a local bound from a call, for the same reason.
#
# A module-level constant, an import, `self`, and a builtin are all
# excluded. That drops the yield from twenty-three to the handful where
# emptiness is a real and invisible possibility, which is the only version
# of this check worth having on.
#
# WHY THE PIN MAY LIVE IN A SIBLING TEST
#
# The pin usually lives in a sibling test, because a module-scoped fixture
# is shared and asserting its shape once is the natural place for it:
#
#     def test_every_model_validates(self, reports):
#         assert len(reports) == len(BUILDABLE)      # <- the pin
#
#     def test_nothing_disagrees(self, reports):
#         assert not [f for f in ... ]               # <- the filter
#
# A per-function rule would flag the second and be wrong. So pins are
# collected across the whole class (module level for bare functions), which
# is the scope a reader checks anyway.
#
# WHAT COUNTS AS A PIN
#
# Any assertion that fails when the source is empty: `assert src`,
# `assert len(src) == 3`, `assert len(src) > 0`, `assert src, "msg"`,
# `assert set(src) == {...}`, or `assert len(src) >= 1`. A comprehension
# over a literal display (`[a, b, c]`) needs no pin -- it is visibly
# non-empty at the callsite.

#: Comparators that make `len(x) <op> n` fail on an empty x.
_PINNING_COMPARE = (ast.Eq, ast.Gt, ast.GtE, ast.NotEq)


def _fixtures_that_assert_their_premise(body) -> set[str]:
    """Fixture names whose own body asserts something.

    A fixture is the right place for its premise: `partly_measured` is
    named for having both measured and unmeasured parameters, and five
    tests depend on the second half of that being true. Asserting it once
    where the fixture is built beats repeating it in every test, and it
    fails at setup with the fixture's own message rather than as a
    confusing empty-filter pass downstream.
    """
    pinned: set[str] = set()
    for node in body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_fixture = any(
            "fixture" in ast.dump(d) for d in node.decorator_list
        )
        if is_fixture and any(
            isinstance(n, ast.Assert) for n in ast.walk(node)
        ):
            pinned.add(node.name)
    return pinned


def _names_pinned_nonempty(body) -> set[str]:
    """Names some assertion in `body` would fail on if they were empty."""
    pinned: set[str] = _fixtures_that_assert_their_premise(body)

    for node in ast.walk(ast.Module(body=list(body), type_ignores=[])):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test

        # A truthiness assertion rooted at the name. Covers `assert src`,
        # `assert src.strip()`, `assert src.rows`, and
        # `assert src.a or src.b` -- each fails when src is empty.
        #
        # `assert not src` is deliberately NOT a pin: it is the emptiness
        # assertion this check is looking for, and counting it would make
        # every finding excuse itself.
        if not (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)):
            for part in (test.values if isinstance(test, ast.BoolOp) else [test]):
                root = _root_name(part)
                if root and isinstance(part, (ast.Name, ast.Attribute, ast.Call)):
                    pinned.add(root)
            if isinstance(test, (ast.Name, ast.Attribute, ast.Call, ast.BoolOp)):
                continue

        # assert len(src) == 3  /  > 0  /  >= 1  /  != 0
        if isinstance(test, ast.Compare) and len(test.ops) == 1:
            left, op = test.left, test.ops[0]
            if isinstance(op, _PINNING_COMPARE):
                for name in _sources_of_len_call(left):
                    pinned.add(name)
                # assert set(src) == {...} / sorted(src) == [...]
                if isinstance(left, ast.Call) and isinstance(op, ast.Eq):
                    func = left.func
                    if isinstance(func, ast.Name) and func.id in {
                        "set", "sorted", "list", "tuple", "dict",
                    }:
                        for arg in left.args:
                            if isinstance(arg, ast.Name):
                                pinned.add(arg.id)
    return pinned


def _sources_of_len_call(node) -> set[str]:
    """`len(x)` -> {"x"}; anything else -> empty."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
    ):
        return {node.args[0].id}
    return set()


def _root_name(node):
    """The name a comprehension iterates: `report.findings` -> "report"."""
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    if isinstance(node, ast.Call):
        return _root_name(node.func)
    return node.id if isinstance(node, ast.Name) else None


#: Sources whose emptiness is visible in the file, or meaningless to pin.
_NOT_AT_RISK = {"self", "cls", "range", "enumerate", "zip", "vars", "dir"}


def _runtime_sources(func) -> set[str]:
    """Names in `func` whose emptiness a reader cannot see.

    Fixtures (parameters) and locals bound from a call. Everything else --
    module constants, imports, literals -- is either visible in the file or
    not the kind of thing this check is about.
    """
    at_risk = {
        arg.arg for arg in func.args.args + func.args.kwonlyargs
        if arg.arg not in _NOT_AT_RISK
    }
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                at_risk.add(target.id)
    return at_risk


def _emptiness_assertions(func) -> list[tuple[int, str, str]]:
    """(line, asserted_name, source_name) for each empty-filter assertion."""
    at_risk = _runtime_sources(func)

    # What each local name was bound to, if it was bound to a comprehension.
    bound: dict[str, ast.AST] = {}
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(
                node.value,
                (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp),
            ):
                bound[target.id] = node.value

    found: list[tuple[int, str, str]] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test

        asserted = None
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            if isinstance(test.operand, ast.Name):
                asserted = test.operand.id
        elif isinstance(test, ast.Compare) and len(test.ops) == 1:
            # assert offenders == []  /  assert len(offenders) == 0
            if isinstance(test.ops[0], ast.Eq) and isinstance(
                test.comparators[0], (ast.List, ast.Dict, ast.Set)
            ) and not getattr(test.comparators[0], "elts", getattr(
                test.comparators[0], "keys", [1])):
                if isinstance(test.left, ast.Name):
                    asserted = test.left.id

        if asserted is None or asserted not in bound:
            continue

        comp = bound[asserted]
        if not comp.generators:
            continue
        # A literal source is visibly non-empty; no pin needed.
        iterated = comp.generators[0].iter
        if isinstance(iterated, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            continue
        source = _root_name(iterated)
        if source and source in at_risk:
            found.append((node.lineno, asserted, source))
    return found


def _empty_filter_violations(tree, path) -> list[str]:
    """Flag empty-filter assertions whose source is never pinned non-empty."""
    violations: list[str] = []

    #: (scope body, the tests inside it). A class shares its pins; bare
    #: functions share the module's.
    scopes: list[tuple[list, list]] = []
    module_tests = [
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name.startswith("test")
    ]
    if module_tests:
        scopes.append((tree.body, module_tests))
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            tests = [
                n for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name.startswith("test")
            ]
            if tests:
                scopes.append((node.body, tests))

    module_fixtures = _fixtures_that_assert_their_premise(tree.body)

    for body, tests in scopes:
        pinned = _names_pinned_nonempty(body) | module_fixtures
        for func in tests:
            for line, asserted, source in _emptiness_assertions(func):
                if source in pinned:
                    continue
                violations.append(
                    f"{path}::{func.name} (line {line}) -- `{asserted}` is "
                    f"filtered out of `{source}` and then asserted empty, but "
                    f"nothing asserts `{source}` is non-empty. This passes "
                    "whether the code is healthy or the filter matches "
                    f"nothing. Pin the source (`assert {source}` or "
                    f"`assert len({source}) == N`) and drive the filter with "
                    "something that does match."
                )
    return violations


def _python_violations() -> list[str]:
    violations: list[str] = []
    scanned = 0

    for root_name in PYTHON_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if not PYTHON_TEST_FILE.match(path.name):
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, SyntaxError):
                continue

            violations.extend(
                _empty_filter_violations(tree, path.relative_to(REPO_ROOT))
            )

            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not node.name.startswith("test"):
                    continue
                scanned += 1

                counter = _PythonAsserts()
                for statement in node.body:
                    counter.visit(statement)

                if counter.free or not counter.guarded:
                    continue

                key = f"{path.relative_to(REPO_ROOT)}::{node.name}"
                if key in PYTHON_BASELINE:
                    continue

                violations.append(
                    f"{key} (line {node.lineno}) -- all "
                    f"{counter.guarded} assertion(s) are inside an `if`, so "
                    "this test cannot fail: the branch is skipped and "
                    "nothing is checked. Assert the condition itself, or "
                    "seed the state the test needs."
                )

    if scanned == 0:
        violations.append(
            "No Python test functions were found under "
            + ", ".join(PYTHON_ROOTS)
            + ". Refusing to report success on an empty scan."
        )
    return violations


def check() -> list[str]:
    """Returns a list of violation strings, empty when every test asserts."""
    files = _test_files()
    if not files:
        return [
            "No test files found under "
            + ", ".join(SEARCH_ROOTS)
            + ". Refusing to report success -- an empty scan is not a clean "
            "tree."
        ]

    violations: list[str] = []

    for path in files:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for name, line, body in _extract_tests(source):
            total, guarded = _scan_body(body)

            # No assertions at all is a different (and rarer) problem; this
            # guard is specifically about assertions that exist but may not
            # run.
            if total == 0 or guarded < total:
                continue

            if name in ALLOWED:
                continue

            relative = path.relative_to(REPO_ROOT)
            violations.append(
                f"{relative}:{line} \"{name}\" -- all {total} assertion(s) "
                "are inside a conditional, so this test cannot fail: either "
                "the branch is skipped and nothing is checked, or every "
                "branch asserts and the test accommodates whatever happened. "
                "Assert the condition itself, or seed the state the test "
                "needs. If the conditionality is deliberate, add the name to "
                "ALLOWED in this script with a reason."
            )

    violations.extend(_python_violations())
    return violations


def main() -> int:
    violations = check()
    if not violations:
        print(
            "OK: every test has at least one assertion that always runs.\n"
            f"    Scanned TypeScript under {', '.join(SEARCH_ROOTS)}\n"
            f"    and Python under {', '.join(PYTHON_ROOTS)}"
            + (
                f" ({len(PYTHON_BASELINE)} Python test(s) on the recorded "
                "baseline; see PYTHON_BASELINE)."
                if PYTHON_BASELINE
                else "."
            )
        )
        return 0

    print(f"Vacuous tests found ({len(violations)}):\n")
    for violation in violations:
        print(f"  {violation}")
    print(
        "\nA test that cannot fail is worse than a missing test: the missing "
        "one is visibly missing."
    )
    return 1


def _selftest() -> int:
    """Prove the Python half fires, on suites this function writes.

    The TypeScript half has years of real findings behind it. The Python
    half was added today and reported OK on its first run -- which is
    exactly the state a check is in when it cannot fail. This establishes
    that it can.
    """
    import tempfile

    global PYTHON_ROOTS, REPO_ROOT, PYTHON_BASELINE
    saved = (PYTHON_ROOTS, REPO_ROOT, PYTHON_BASELINE)
    failures: list[str] = []

    def run(files: dict[str, str], baseline: dict[str, str] | None = None):
        global PYTHON_ROOTS, REPO_ROOT, PYTHON_BASELINE
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "suite").mkdir()
            for name, body in files.items():
                (root / "suite" / name).write_text(body, encoding="utf-8")
            REPO_ROOT = root
            PYTHON_ROOTS = ["suite"]
            PYTHON_BASELINE = baseline or {}
            return _python_violations()

    vacuous = (
        "def test_thing():\n"
        "    result = compute()\n"
        "    if result:\n"
        "        assert result.ok\n"
    )
    healthy = (
        "def test_thing():\n"
        "    result = compute()\n"
        "    assert result is not None\n"
        "    if result:\n"
        "        assert result.ok\n"
    )
    looping = (
        "def test_thing():\n"
        "    for item in items():\n"
        "        assert item.ok\n"
    )
    raises = (
        "def test_thing():\n"
        "    with pytest.raises(ValueError):\n"
        "        boom()\n"
    )

    try:
        # Negative case FIRST. If a healthy test is reported, every positive
        # below would fire on anything.
        if run({"test_a.py": healthy}):
            failures.append("a test with an unconditional assert was reported")

        if not run({"test_a.py": vacuous}):
            failures.append("a wholly conditional assert was NOT reported")

        if run({"test_a.py": looping}):
            failures.append(
                "a `for` loop was treated as conditional; the TypeScript half "
                "declines to judge loops and the two must agree"
            )

        if run({"test_a.py": raises}):
            failures.append("`with pytest.raises` was not counted as an assertion")

        key = "suite/test_a.py::test_thing"
        if run({"test_a.py": vacuous}, {key: "recorded"}):
            failures.append("the baseline did not suppress a recorded entry")

        if not run({}):
            failures.append("an empty scan reported success")

        # A test function with no assertions at all is a different problem
        # and not this guard's business.
        if run({"test_a.py": "def test_thing():\n    compute()\n"}):
            failures.append("a test with no assertions was reported")

        # --- the third shape: a filter asserted empty over a loose source --
        #
        # Added the same day as the check, and for the same reason as the
        # rest of this function: the empty-filter scan reported OK on its
        # first run over the whole repository, which is indistinguishable
        # from a scan that cannot fire.
        empty_filter = (
            "def test_thing(reports):\n"
            "    bad = [r for r in reports if r.severity == 'error']\n"
            "    assert not bad\n"
        )
        if not any("filtered out of" in v for v in run(
            {"test_a.py": empty_filter}
        )):
            failures.append("an unpinned empty-filter assertion was not caught")

        pinned_here = (
            "def test_thing(reports):\n"
            "    assert len(reports) == 11\n"
            "    bad = [r for r in reports if r.severity == 'error']\n"
            "    assert not bad\n"
        )
        if any("filtered out of" in v for v in run({"test_a.py": pinned_here})):
            failures.append("a source pinned in the same test was flagged")

        pinned_by_sibling = (
            "class TestIt:\n"
            "    def test_premise(self, reports):\n"
            "        assert len(reports) == 11\n"
            "    def test_thing(self, reports):\n"
            "        bad = [r for r in reports if r.severity == 'error']\n"
            "        assert not bad\n"
        )
        if any("filtered out of" in v for v in run(
            {"test_a.py": pinned_by_sibling}
        )):
            failures.append("a source pinned by a sibling test was flagged")

        pinned_by_fixture = (
            "import pytest\n"
            "@pytest.fixture\n"
            "def reports():\n"
            "    out = build()\n"
            "    assert out, 'nothing to check'\n"
            "    return out\n"
            "class TestIt:\n"
            "    def test_thing(self, reports):\n"
            "        bad = [r for r in reports if r.severity == 'error']\n"
            "        assert not bad\n"
        )
        if any("filtered out of" in v for v in run(
            {"test_a.py": pinned_by_fixture}
        )):
            failures.append("a fixture asserting its own premise was flagged")

        # A module constant is visible in the file; flagging it is the
        # cry-wolf behaviour that made the first version unusable.
        module_constant = (
            "RULES = (1, 2, 3)\n"
            "def test_thing():\n"
            "    bad = [r for r in RULES if r < 0]\n"
            "    assert not bad\n"
        )
        if any("filtered out of" in v for v in run(
            {"test_a.py": module_constant}
        )):
            failures.append("a module-level constant source was flagged")

        # The emptiness assertion must not be read as its own pin.
        self_excusing = (
            "def test_thing(rows):\n"
            "    bad = [r for r in rows if r.bad]\n"
            "    assert not bad\n"
            "    assert not bad\n"
        )
        if not any("filtered out of" in v for v in run(
            {"test_a.py": self_excusing}
        )):
            failures.append("`assert not x` was accepted as its own pin")
    finally:
        PYTHON_ROOTS, REPO_ROOT, PYTHON_BASELINE = saved

    if failures:
        print(f"SELFTEST FAILED ({len(failures)}):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("SELFTEST OK: the Python scan fires, and a healthy test still passes.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    sys.exit(main())
