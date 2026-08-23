# ADR 0173: A failure wearing two costumes

**Status:** Accepted

**Date:** 2026-08-23

## Context

Two tests failed in `make test` for this entire session, and I flagged them
five times as "pre-existing, not mine" without ever finding out what they
were:

```
tests/test_citation_metadata.py::TestTheCitationFileItself::test_the_guard_passes
tests/test_guard_selftests.py::test_the_guards_selftest_passes[check_codegen_loads.py]
```

The first reports `UNREACHABLE  cffconvert is not installed`. The second
reports `SELFTEST FAILED: the load check rejected a module that is valid for
the installed zod`.

Both messages are accurate. Both name the wrong problem.

They are **one failure wearing two costumes**: a declared dependency that was
never installed. `cffconvert` is pinned in `requirements-dev.txt` and present
in no virtualenv on this machine. `zod` is declared in `lib/api-zod` and that
workspace had no `node_modules` — symlinking it made the codegen selftest
pass immediately, with no change to the check it was supposedly failing.

Neither guard is broken. Both did the right thing: the citation guard
correctly refused to call an unchecked file valid, and the codegen selftest
correctly refused to trust a load check it could not verify. What was missing
is anything that says *why*, in terms of the thing to install. The costume
sends a reader to debug the citation file or the zod pin — which is where I
would have gone, five times, if I had ever followed it up.

## Decision

**A check that names the missing dependencies, and nothing else.**

`scripts/check_dev_dependencies.py` parses `requirements-dev.txt` (following
`-r` includes), checks each distribution against the installed metadata, and
checks the JS packages that *Python* guards depend on — which no JS tooling
ever notices, and which is precisely how the zod costume arose.

Three states: **0** everything declared is present, **1** something is
missing with the exact install command, **3** could not determine. An
unreadable manifest yielding zero dependencies would report every dependency
satisfied, strongest exactly where it knows least.

**Advisory, not a gate.** Wired into `make doctor` and available as
`make deps-check`, deliberately *not* a prerequisite of `make test`: 1162 of
1164 tests pass without these packages, and blocking all of them to report
two would trade a small confusing failure for a large one.

## Verification

```
MISSING declared dependencies. Guards will report problems that
name the wrong cause until these are installed.

  Python (2):
    python-libsedml
    cffconvert

    python3 -m pip install -r requirements-dev.txt
```

`python-libsedml` was not previously known to be missing at all.

### It reported five, and three were installed

The first version resolved a distribution name to a module name with
`s/-/_/` plus a small override table. It reported **five** packages missing.
Three of them were installed:

| declared | imports as | actually |
|---|---|---|
| `libroadrunner` | `roadrunner` | installed 2.8.0 |
| `python-libsbml` | `libsbml` | installed 5.21.1 |
| `beautifulsoup4` | `bs4` | installed 4.15.0 |

**That failure is worse than the one this file was written to fix.** A real
dependency reported with a confusing message costs an hour. A checker that
invents three missing dependencies makes its own output untrustworthy and
buries the two real ones in noise — and the output looks entirely plausible
until somebody tries to install them.

Fixed by asking `importlib.metadata` for the distribution the manifest
actually names, which removes the mapping rather than extending it. There is
now no table to drift.

### And the test that disabled itself

Mutation **V1** restores the guessing, and was reported **NOT CAUGHT** on the
first run.

The test asserting "an installed package with a differing import name is not
reported missing" guarded itself with `if not guard.is_installed(...):
pytest.skip(...)`. V1 breaks `is_installed`, so under the mutation the
precondition failed and **every case skipped itself** — a test that switches
off under exactly the defect it exists to catch, which is indistinguishable
from a passing one in the summary line.

Fixed by asking `importlib.metadata` directly for the precondition. A test's
guard clause must not route through the code under test.

Mutations, `docs/mutations/adr-0173-dev-dependencies.json`, **3 caught, 0 not
caught** after that fix:

| id | mutation | caught |
|---|---|---|
| V1 | distribution names guessed from module names again | yes |
| V2 | an unreadable manifest parses as zero dependencies | yes |
| V3 | could-not-determine exits 0 instead of 3 | yes |

The guard ships a `--selftest`, so `test_guard_selftests.py` picks it up
without being told — the discovery mechanism ADR 0069 exists for.

## Consequences

`make deps-check` answers in one line what took five deferrals to look at.

`make test` on this machine is now **1 failed, 1175 passed**, down from two
failures. Be precise about why, because only half of that is this record's
doing: the codegen selftest passes here because the author symlinked
`lib/api-zod/node_modules` from another checkout while diagnosing it. **That
symlink is not committed and will not exist for anyone else** — on a fresh
clone without `pnpm install` in that workspace, that test fails exactly as
before. The citation test still fails, because `cffconvert` is still not
installed; putting it into a virtualenv shared with another agent is not this
record's decision to make.

So: one test is green here for an environmental reason, one is red for a
stated one, and the checker names both causes. Nothing about either guard
changed.

**What this does not check.**

- **`REQUIRED_JS` lists one package.** `zod`, found by running the failing
  selftest and reading what it needed. Nothing verifies that some other
  Python guard does not quietly depend on a different workspace's
  `node_modules`, and the same costume could recur there.
- **Version pins are ignored.** It checks presence, not that the installed
  version matches the pin. A wrong version would satisfy this and fail the
  guard that needs it, which is the same class of misleading message this
  record is about.
- **It does not install anything.** By design, but worth stating: the output
  is a command for a person to run.
- **Neither guard was changed, and neither test was fixed.** One passes here
  only because of an uncommitted symlink; the other still fails. This record
  makes the cause legible, not the tests green.
- **The JS check passes on this machine for the same accidental reason.**
  `REQUIRED_JS` finds `zod` present because of that symlink. On a clean
  checkout it would correctly report it missing — which is the intended
  behaviour, but is not what was observed here.
