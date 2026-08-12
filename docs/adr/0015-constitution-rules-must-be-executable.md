# ADR 0015: A constitution rule that nothing executes is not enforced

**Status:** Accepted

**Date:** 2026-08-02

## Context

Three consecutive rounds of work each ended in the same finding, in three
unrelated places:

| where | the stated rule | what the code did |
|---|---|---|
| `README.md`, `Terium/tests/` | test counts | drifted by 500+ |
| `requirements.txt` ×3 | "SBML extensions stop at cp312" | wrong package entirely |
| `schemas.ts` | "exactly one route must be available" | accepted zero routes |

The third is the sharpest. A comment two lines above the code stated the
rule; the `refine()` beneath it compared two presence flags for equality, so
a request supplying *neither* `vmax` nor `kcat`/`enzyme_conc` passed —
`false === false`.

At that point the pattern was clearly systemic rather than three accidents,
so the nine constitutional rules were audited directly: for each, is there
something that fails when it is broken?

## Findings

**Rule 7** — *never `pip install tellurium`* — was prose. It is listed among
the nine non-negotiable rules, has ADR 0001 behind it, and `requirements.txt`
devotes a paragraph to the consequences. Demonstrated before writing any
code: appending `tellurium==2.2.10` to `requirements.txt` passed
`check_dependencies_declared`, `check_engine_contract`,
`check_python_support_claim`, **and** `verify_build.py --quick`.

**Rule 8** — *every decision gets an ADR* — was also prose, and had already
failed twice, both caught by hand:

- ADR 0009 existed but was missing from `docs/adr/README.md` (Stage 5 audit)
- ADR 0007 was written **twice**, by two different implementers (Stage 4)

**Rules 2, 4, 5** were genuinely enforced, confirmed by mutation rather than
by inspection:

| rule | mutation | result |
|---|---|---|
| 2 (`ok`/`flagged`/`flag_reason`) | rename `flag_reason` → `flagReason` | engine-contract guard fails |
| 4 (shared constraints by test) | flip `allow_zero` on Vmax | `test_michaelis_menten_zero_vmax` fails |
| 5 (declared dependencies) | add an undeclared `import tomli` | dependency guard fails |

Rules 1, 3, 6, and 9 are judgment rules — "check against independent ground
truth", "decide continuous vs discrete explicitly", "mutation-test the
suite", "conservative defaults". They govern *how work is done* and cannot
be reduced to a file check without becoming a ritual. They stay enforced by
review.

## Decision

**Every constitutional rule that makes a checkable claim about the
repository gets a guard.** Rules 7 and 8 are now enforced by
`scripts/check_forbidden_packages.py`, wired into CI and
`verify_build.py --quick`.

Rule 5 already stated the principle for its own case — undeclared
dependencies are *"a category of bug with a permanent automated guard, not a
one-time fix"*. This ADR generalises that sentence to every rule of the same
shape. A **forbidden** dependency is the same category as an **undeclared**
one; it was simply policed by prose.

### Why the two guards live in one script

Both are constitution-rule enforcement over repository metadata, they share
`REPO_ROOT` and a failure vocabulary, and two scripts with near-identical
purposes become two scripts nobody remembers the difference between. Named
"Constitution Rules 7+8" in both harnesses so the name states its scope.

## Consequences

**Easier.** Breaking Rule 7 or 8 now fails the build with a message naming
the rule, the file, the line, and the reason. The reason is printed on
failure deliberately: a bare "forbidden" invites someone to delete the check.

**Harder.** Nothing. No rule changed; two became enforceable.

**Unchanged.** The nine rules themselves. This ADR adds no rule and relaxes
none.

## Verification

Every check mutation-tested, several against reproductions of defects that
actually occurred:

```
terium pinned in requirements.txt        -> caught
terium bare / range-specified            -> caught (PEP 503 normalised)
terium in pyproject [project]            -> caught
terium in [project.optional-dependencies]-> caught
ADR on disk but unindexed                   -> caught  (the real 0009 case)
index links a nonexistent ADR               -> caught
two files claiming one ADR number           -> caught  (the real 0007 case)
```

Confirmed the guard still parses all real dependencies across three
manifests after each scoping fix, so tightening never blinded it.

### Two false alarms worth recording

**A guard that cried wolf.** The first version scanned all of
`pyproject.toml` and reported `"Terium/tests/*.py"` — a ruff
per-file-ignore key — as a forbidden dependency. That is a real defect, not
cosmetic: a guard producing false positives gets ignored, then deleted, and
the next true positive rides along with it.

**A mutation aimed at the wrong file.** Checking Rule 4, the `allow_zero`
mutation was run against `test_validator_agreement.py` and passed, which
looked like a coverage gap. The mutation had applied correctly; the
assertion simply lives in `test_engine_api.py`. Re-run against the right
file, it fails as it should.

That is the third time in this session that a too-narrow mutation scope
produced a green result and briefly looked like a hole. **"The mutation did
not reach the test" and "no test caught the mutation" are indistinguishable
from the output alone** — the scope has to be verified separately.

## References

- `docs/CONSTITUTION.md` — the nine rules; Rule 5 states the principle this
  ADR generalises.
- **ADR 0001** — the tellurium umbrella package decision Rule 7 encodes.
- **ADR 0014** — the Python support claim, an instance of the same pattern
  found in the same sweep.
