# wiring-main

Part of [**Terrium**](https://github.com/Terrium-sim/main) — scientific computing for teaching labs.

The guards, CI and build configuration. 27 files.

Not backend, not frontend: the machinery that decides whether a change is
allowed to land.

## The 21 guards

```bash
python scripts/verify_build.py --quick
```

A sample of what they refuse:

| guard | fails when |
|---|---|
| `check_no_vacuous_tests` | a test's only assertions sit inside an `if` — it cannot go red |
| `check_no_disabled_tests` | a committed `.only`, or a `.skip` that says nothing |
| `check_no_orphan_modules` | a module nothing imports |
| `check_example_endpoints` | a documented endpoint no server serves |
| `check_typescript_suites_discovered` | a test file on disk its runner never collects |
| `check_no_silent_skips` | a suite that did not run reported as zero skips |
| `check_forbidden_packages` | `tellurium` in a manifest — or a doc telling you to install it |
| `check_literature_inventory` | a hardcoded scientific constant with no declared provenance |
| `check_guard_wiring` | a guard that runs in no harness, or lost one it used to |

## The rule they all serve

**A check that cannot fail is worse than no check, because it is trusted.**

Several of these exist because a previous guard was found reporting green on
work it had not done — one printed "every collected test ran" while 275
tests failed to collect; another promised regression detection in its
docstring and had an empty loop body. The build-stage records in
[`business`](https://github.com/Terrium-sim/business) document each one.

---

This repository is a submodule of [`Terrium-sim/main`](https://github.com/Terrium-sim/main). Clone the whole system with:

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
```
