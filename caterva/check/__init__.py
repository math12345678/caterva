"""The independent checker: `caterva verify` (ADR 0179).

Everything in this package imports the standard library and nothing else:
not `caterva.evidence`, which wrote the bundles it reads, and not the
literature layer, whose parser produced the rows it re-finds. The point of
a second program is that it cannot share the first one's mistakes, and a
checker that imported the producer's canonical JSON, its digests or its row
parser would be the producer checking itself. `scripts/
check_checker_independence.py` walks every module here with `ast` and fails
on any import outside `sys.stdlib_module_names`, on anything named
`caterva`, `Tests`, `bs4`, `pydantic` or `numpy`, and on a relative import
that leaves this package.

    verify     verify_bundle(directory) -> Report: the eight checks
    __main__   `caterva verify DIR [--json]`: one line per check, a summary,
               exit 0 ok, 3 a check failed, 2 the bundle cannot be read

The words are "re-checkable" and "holds against the pinned bytes". The
checker checks derivations and stated reasons against bytes that were kept;
it does not check the biology, and nothing here says "verified" or
"correct".
"""
