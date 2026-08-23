# ADR 0175: A package nobody declared

**Status:** Accepted

**Date:** 2026-08-23

## Context

The owner installed `requirements-dev.txt`, which ADR 0173 had asked for. The
two failures that record was about went away, and three different ones
appeared.

That is not a regression. It is the same masking ADR 0174 described, one
level up: `make test` runs the engine suite and then the literature suite,
and stops at the first that fails. While the engine suite was red, **the
literature suite had not run at all**.

With the engine suite green, the interpreter that has the packages reports:

```
1215 passed, 0 skipped      (engine — was 1175 passed, 4 skipped, 1 failed)
```

and then, for the first time, the literature suite runs.

Two things fell out of the install itself, both worth recording because both
look alarming and only one is.

**The `pip` conflict is expected and already documented.** The install
downgraded `antimony` 3.1.3 → 2.14.0 and printed
`tellurium 2.2.13 requires antimony>=3.1.0, but you have antimony 2.14.0`.
`requirements.txt` line 26 says, in as many words: *"do NOT `pip install
tellurium`"* — the umbrella package pulls in libcombine and libnuml, which
Terrium does not use and which fail to build where no wheels exist. The
install restored exactly the versions this project pins. The conflict is with
a package the project tells you not to have.

**PyYAML is imported by two guards and declared in no requirements file.**
`check_ci_toolchain.py` and `check_ci_red_step_is_last.py` both `import
yaml`. Neither `requirements.txt` nor `requirements-dev.txt` mentions it. On
an interpreter without it — which the freshly-installed venv was — both
guards fail.

They fail differently, and the difference is the point:

| guard | behaviour without PyYAML |
|---|---|
| `check_ci_toolchain.py` | `PyYAML is not installed. This is 'could not check', NOT 'checked and fine'. Exiting 3.` |
| `check_ci_red_step_is_last.py` | unhandled `ModuleNotFoundError`, traceback, no verdict |

And `check_dependencies_declared.py` reported **"OK: every third-party import
is declared in a requirements file"** throughout. Honestly, given its scope —
it excludes `scripts/`, on reasoning written into the file:

> `scripts/` isn't scanned for imports (it's tooling, not product code or
> tests) […] its imports are stdlib-only — **If it ever grows third-party
> imports, those must be declared**

The second sentence is a promise nothing kept. `scripts/` grew one, and the
check whose job is to notice had been told not to look.

## Decision

Three changes, one per finding.

**Declare PyYAML** in `requirements-dev.txt`, with the pin and licence note
the file's conventions require. `check_ci_toolchain.py` already carried the
comment `# pragma: no cover - PyYAML is in requirements-dev`, which was not
true when it was written. It is now.

**Give `check_ci_red_step_is_last.py` the three-state import** its sibling
already had. A traceback is not a verdict: the guard-selftest harness
recorded the crash as a failing *check* rather than as a check that could not
run, which is the same conflation the exit-3 convention exists to prevent.

**Scan `scripts/` in `check_dependencies_declared.py`.** An assumption that
is stated and not enforced is the shape this repository keeps finding. The
person it protects is a contributor whose machine lacks a package some guard
needs — and that is exactly who was hit here.

## Verification

The extended check catches the thing, proven by removing the declaration
again:

```
Undeclared dependencies found:

  import yaml
    used in scripts/check_ci_toolchain.py
    used in scripts/check_ci_red_step_is_last.py
```

Restored and re-run: `OK`. The restore was verified byte-identical with
`diff`.

Both previously-crashing selftests now exit 0 with PyYAML present, and
`check_ci_red_step_is_last.py` exits **3** rather than 1 without it —
confirmed by running it under an interpreter that lacks the package.

Also fixed in passing: `check_no_silent_skips.py` emitted
`SyntaxWarning: invalid escape sequence '\d'` on every import, because a
docstring containing `(\d+)` was not raw. Verified silent under
`python -W error::SyntaxWarning`.

`make deps-check` under the interpreter that has the packages: **OK, all 15
declared dev dependencies importable**.

## Consequences

The engine suite is green and the literature suite runs for the first time
this session. It reports **5 failures**, which this record does not fix and
does not claim to have caused:

- `test_investor_claims` — `terrium_pitch_deck.pptx` says 1,852 automated
  tests; the repository has 2,332. A documented-count drift in a file another
  agent currently has uncommitted changes to.
- `test_lab_report`, `test_runner_contract` — assertions about report text
  and output shape.

They became visible by fixing what was in front of them, which is what ADR
0174's runner was built to stop needing.

**What this does not check.**

- **Whether those 5 literature failures pre-date this session.** They could
  not run before, so there is no earlier observation to compare against. At
  least one is partly *worsened* by this session: the pitch deck's drift is
  larger because ~40 tests were added. The drift itself is older.
- **Whether `scripts/` has other undeclared imports on other platforms.** The
  scan sees what this interpreter's stdlib list says is not stdlib; a module
  that is stdlib here and not elsewhere would pass here and fail there.
- **The `advanced_analysis/venv` is not the repository's `.venv`.** The
  packages went where the owner's shell pointed. `make` picks that
  interpreter only when the venv is active or `TERRIUM_PYTHON` names it — on
  a bare shell it still resolves to a system Python without them, and the
  original failures reappear. Nothing here changes interpreter selection.
- **PyYAML's version was chosen, not derived.** `6.0.2` is the current stable
  line; no constraint in this repository required that number over another.
