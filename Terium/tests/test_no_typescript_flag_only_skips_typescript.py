"""`--no-typescript` must skip TypeScript, and nothing else.

WHY THIS FILE EXISTS
--------------------
Four guard groups sat inside `verify_build.py`'s `if not
args.no_typescript:` branch:

    Prompt Injection Guard
    Orphan Module Guard
    Test Honesty Guards      (22 guards: ADR index, mutation-table
                              reproducibility, CLI surface, licence
                              consistency, bug-lints, ...)
    Generated Files Guard

Exactly one of the five groups in that branch is about TypeScript
compiling. The flag is documented as "Skip TypeScript tests".

Measured on one tree, one commit:

    --quick                    6 failures
    --quick --no-typescript    3 failures

The three that vanished were ADR Index, Mutation Table Reproducibility
and Prompt Injection -- none of which reads a line of TypeScript. A flag
that makes a tree look cleaner by not looking is the shape this
repository exists to refuse.

Two of the four carried comments insisting they run in every mode:
"so it runs in every mode rather than behind the slow-test flag", and "A
guard against tests that cannot fail is worth little if it only runs in
the slow path". Both were true about the intent and false about the code.
That is worse than no comment, because it is why nobody re-read the
indentation.

WHAT THIS ASSERTS, AND WHY IT IS STRUCTURAL RATHER THAN A RUN
-------------------------------------------------------------
Running verify_build twice and diffing the failures would take several
minutes per invocation and would only catch the regression on a tree that
currently has failures to hide -- a green tree makes the two runs
identical and the test vacuous.

So this reads the source: the `if not args.no_typescript:` block must
contain the TypeScript group and nothing else. That is decidable in
milliseconds and does not depend on the tree being red.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
VERIFY_BUILD = REPO / "scripts" / "verify_build.py"

#: The only guard group that legitimately belongs behind --no-typescript.
#: check_typescript_compiles.py needs a local node_modules/typescript and
#: correctly refuses to pass without one, so a Node-free run has to be able
#: to turn it off. Nothing else in that branch has that property.
ALLOWED_IN_BRANCH = {"run_typescript_guards"}


def _no_typescript_branch() -> ast.If:
    """The `if not args.no_typescript:` statement that gates the guards.

    There are two in the file -- one for guards, one for the TypeScript
    test run inside `if not args.quick:`. This returns the guard one: the
    one whose body calls `run_typescript_guards`.
    """
    tree = ast.parse(VERIFY_BUILD.read_text(encoding="utf-8"))
    candidates = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)):
            continue
        operand = test.operand
        if not (
            isinstance(operand, ast.Attribute) and operand.attr == "no_typescript"
        ):
            continue
        called = {
            n.func.id
            for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        if "run_typescript_guards" in called:
            candidates.append(node)

    assert candidates, (
        "no `if not args.no_typescript:` block calling run_typescript_guards "
        "was found in verify_build.py. If the flag was renamed or the "
        "structure changed, this test must be updated deliberately -- it "
        "must not silently stop checking."
    )
    assert len(candidates) == 1, (
        f"expected exactly one such block, found {len(candidates)}. Two "
        "would mean the flag is honoured in two places and this test only "
        "constrains one of them."
    )
    return candidates[0]


def _guard_calls(node: ast.If) -> set[str]:
    return {
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id.startswith("run_")
        and call.func.id.endswith(("guard", "guards"))
    }


def test_the_flag_gates_only_the_typescript_group() -> None:
    inside = _guard_calls(_no_typescript_branch())

    assert inside == ALLOWED_IN_BRANCH, (
        "`--no-typescript` gates guard groups that are not about "
        "TypeScript.\n\n"
        f"  inside the branch: {sorted(inside)}\n"
        f"  allowed:           {sorted(ALLOWED_IN_BRANCH)}\n\n"
        "A flag documented as 'Skip TypeScript tests' that also turns off "
        "the prompt-injection scan, the ADR index or the mutation-table "
        "check is a way to make the tree look clean by not looking at it. "
        "Move the group out of the branch, or -- if it genuinely cannot "
        "run without a Node toolchain -- add it to ALLOWED_IN_BRANCH with "
        "the reason."
    )


def test_the_finder_would_notice_if_the_branch_disappeared() -> None:
    """The check above is worthless if `_no_typescript_branch` silently
    finds nothing and `inside` is compared as an empty set.

    It asserts rather than returning None, and this pins that: the failure
    mode of a structural test is finding nothing and calling it clean.
    """
    node = _no_typescript_branch()
    assert _guard_calls(node), (
        "the branch was located but no run_*_guard call was found inside "
        "it, so the assertion above would pass on an empty set"
    )
