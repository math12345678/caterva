# ADR 0093: A linter configured and never run

**Status:** Accepted, implemented

**Date:** 2026-08-15

**Context:** `pyproject.toml`, `scripts/verify_build.py`,
`scripts/check_python_bug_lints.py`

## How this was found

Last pass I nearly shipped a duplicate declaration of another agent's field,
and wrote it up as a discipline problem — *re-check immediately before
writing.* This project's own standard is that a lesson in prose stops being
checked, so the next question was whether a mechanism already caught it.

**It does.** `tsc` reports `TS2300: Duplicate identifier` — verified by
re-creating the duplicate and running the compiler. No guard needed, and the
write-up over-claimed.

But `KineticResult` is **Python**, and pydantic accepts a duplicate field
silently:

```python
class M(BaseModel):
    value: int = 1
    value: int = 2      # no error, no warning
M().value               # 2
```

So: does anything catch it on the Python side? `pyproject.toml` configures
ruff with forty-odd rule families selected, including `F` — which contains
F811, exactly this. And ruff **is executed by nothing.** Not CI, not the
Makefile, not `verify_build.py`.

## What it cost

```
scripts/verify_build.py:813  F821  Undefined name `CATERVA_DIR`
scripts/verify_build.py:822  F821  Undefined name `CATERVA_DIR`
```

`run_python_tests()` referenced a constant that does not exist. It is called
unconditionally on the non-`--quick` path, so:

```
>>> run_python_tests(quick=True)
NameError: name 'CATERVA_DIR' is not defined
```

**The script that verifies the build crashed in the branch that runs the
tests** — before executing a single one, and taking every check sequenced
after it down with it. I had been recording "the engine suite was not run
this pass" for many passes and attributing it to the sandbox's time limit.

F821 finds it in under a second. The linter that finds it was configured,
declared as a dev dependency, and invoked by nobody.

Also found: a duplicate `ache_kcat_provider` pytest fixture (F811) —
identical to the first, silently shadowing it, because pytest takes the last
definition. The same class TypeScript's compiler catches for free and Python
does not.

## The shape

A `[tool.ruff.lint]` block listing forty rule families is the most
convincing possible statement that a project lints thoroughly. It is also
completely compatible with never linting.

That is this codebase's recurring defect wearing new clothes — a check that
cannot fail, because it never runs. The same shape as `check_rng_convention`
sitting dead for a whole stage (the reason `check_guard_wiring.py` exists),
and as the citation guard that parsed zero entries and printed OK.

`check_guard_wiring.py` already enforces *"a guard is not delivered until
something runs it unasked"* — for guards in `scripts/`. It had nothing to
say about a linter configured in `pyproject.toml`.

## Decision

`check_python_bug_lints.py` runs the ruff rules that find **defects rather
than preferences**, and is wired into `verify_build.py`:

| rule | what it catches |
|---|---|
| F821 | undefined name — a `NameError` waiting for its line to run |
| F811 | redefinition — two definitions, the last silently wins |
| E9 | syntax and IO errors — the file does not parse |

### Why not the whole configured ruleset

It reports **249 findings** across `Tests/` and `scripts/`. Wiring that
would make the shared build red on arrival, and this project has a standing
rule against exactly that: a red guard is one people learn to skip. It is
the same reason `check_investor_claims.py` was left unwired two passes ago
until somebody had verified it green.

### Why F401 and F841 are excluded, and counted

They are bug-class too — an unused import is often the residue of a deleted
call site — and they find 23 findings today. They sit in `NOT_YET_GREEN`,
printed on **every run**, so the gap is a number somebody can decide about
rather than a silence. Same arrangement as the mutation-table debt
(ADR 0072) and the unwired exports (ADR 0090).

They are also not mine to fix in bulk: most sit in files other agents are
actively editing, and a nineteen-file autofix landing under somebody
mid-edit is a worse outcome than the lint.

### A missing tool is not a pass

If ruff is absent the guard **fails** rather than skipping. A check that
silently passes when its tool is missing reports OK on every machine that
lacks it — which is every machine where nobody installed it, which is how
this went unrun in the first place.

## Verification

Re-introduced the exact defect by deleting the `CATERVA_DIR` definition:

```
with the NameError back: exit=1
restored:                exit=0
```

The guard catches the specific historical failure it was written for, which
is the standing rule for guards here.

## Consequences

- `CATERVA_DIR` is defined, so `verify_build.py`'s Python-test path runs at
  all for the first time. What that path then reports is a separate
  question, and this ADR does not claim to have answered it — the engine
  suite exceeds the sandbox's per-call limit.
- The other 226 style findings remain. Deliberately: this guard exists to
  catch defects, and widening it should come with the findings fixed first.

## Related

- [ADR 0090](0090-the-capability-nobody-could-reach.md) — configured and
  unreachable, at the scale of a capability
- [ADR 0072](0072-evidence-that-can-be-re-derived.md) — the counted-debt
  arrangement reused here
