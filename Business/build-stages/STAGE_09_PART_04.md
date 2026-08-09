# Stage 9, Part 4 — the verifier was not verifying TypeScript; three phantom domains removed

Stage: 9 · Part: 4 · 2026-08-09

## 0. What this part does

Adds the guard that was missing, and uses it immediately to find two real
defects it was built to catch.

## 1. `verify_build.py` was not checking TypeScript at all

Repeatedly on 2026-08-09, `python3 scripts/verify_build.py --quick`
printed:

```
✅ ALL CHECKS PASSED
🎉 The codebase is in a deployable state!
```

on a tree where `tsc --noEmit` had **16 errors**. The claim was false, and
structurally so:

* No type-check step existed anywhere in the verifier.
* `run_typescript_tests()` (`npm test`) ran only in FULL mode — so
  `--quick`, the mode the README documents as the everyday command,
  exercised **zero** TypeScript.

Half the codebase was outside the aggregate verifier's reach while the
verifier asserted the whole thing was deployable. This is precisely the
failure ADR 0015 names: a rule nothing executes is not enforced.

**`scripts/check_typescript_compiles.py`** now type-checks every workspace
holding a `tsconfig.json` and a `src/` tree — discovered, not hardcoded,
since a hardcoded list is exactly how the original gap persisted. It finds
7 workspaces. It runs in **every** mode including `--quick`: type-checking
is a few seconds, deterministic, and offline, so there is no reason for it
to sit behind the slow-test flag — and every reason for it to run now that
multiple agents commit to this repository concurrently.

It refuses to report a workspace as passing when it cannot actually check
it (no local `node_modules/typescript`), rather than silently skipping —
the same mistake in miniature.

Mutation-tested: injected a type error, guard failed and named the
workspace, file, line and fix; reverted, green again. Verified end-to-end
that `--quick` now exits non-zero on a non-compiling tree.

## 2. What it caught within minutes: three domains that do not exist

On its first real run the guard failed on 13 errors that were not mine.
Investigating produced a worse finding than a broken build.

Another agent had added **`lotka_volterra`, `cell_cycle_oscillator`, and
`repressilator`** as first-class simulation domains: `SimulationDomain`
union members, Zod parameter schemas, test fixtures, `DISPATCH` entries,
and `run_*` handlers in `tellurium_runner.py`.

None of them exist in the engine:

```
simulate_lotka_volterra          in __all__=0  hasattr=False
simulate_cell_cycle_oscillator   in __all__=0  hasattr=False
simulate_repressilator           in __all__=0  hasattr=False
```

The `run_*` handlers called `tellurium_engine.simulate_lotka_volterra(...)`
— an attribute that has never existed. Any query routed to one of these
domains would have died with `AttributeError` at runtime. This was
fabricated API surface: a documented, schema-validated, type-checked
contract for capabilities the project does not have.

All three removed — from `DISPATCH`, the `HANDLERS` table, the three
`run_*` functions (55 lines), the `SimulationDomain` union, the Zod
schemas, and the test fixtures.

They are not intrinsically bad ideas — Lotka-Volterra and the repressilator
are legitimate teaching domains. But each needs what every existing domain
got: a real engine implementation, verification against a closed form or
published result, a mutation test, and an ADR. Declaring the API surface
first, with nothing behind it, inverts that entirely.

## 3. And a second, subtler one: the boundary contract had been inverted

`Tellurium/tests/test_boundary_contract.py` was failing 5 tests. The cause
was a `DISPATCH` comment reading:

> (monte_carlo_pi and gillespie_ssa_replicates are removed as they are not
> part of the TypeScript API contract.)

That has ADR 0007 backwards. Both **are** in the engine's `__all__`, both
have working `run_*` handlers, and Monte Carlo π is in the README's
documented domain list. ADR 0007's entire point is that the **engine's**
surface is the contract and the TypeScript side follows it — not the
reverse. Someone deleted two real, working domains from the dispatch table
to silence a stale TypeScript union.

Both restored to `DISPATCH` and added to `SimulationDomain`. All 33
boundary-contract tests pass.

Worth stating plainly: **two agents were fixing the same drift in opposite
directions** — one adding domains to TypeScript that the engine lacked,
another deleting domains from the engine's dispatch that TypeScript lacked.
Neither checked which side was authoritative. ADR 0007 already answers it.

## 4. Verification

- `check_typescript_compiles.py`: 7 workspaces clean; mutation-tested both
  directions.
- `verify_build.py --quick`: all 12 guards pass (was 11), now including
  TypeScript, in ~28s.
- TypeScript: 28 files, 398 tests passing; `tsc --noEmit` clean.
- Tellurium engine: full fast suite passing, including all 33
  boundary-contract tests (was 5 failing).
- Literature layer: 280 passing (9 `stdpopsim` sandbox failures unchanged).

## 5. Carried forward

1. **The three removed domains**, if genuinely wanted, need engine
   implementations + verification + ADRs first. Recommend Lotka-Volterra
   first: it has an exact conserved quantity
   `V = δp − γ·ln p + βv − α·ln v` that makes it verifiable against
   something other than itself, in the spirit of every other domain here.
2. **The 8 root-level `.md` summary files** — still committed, still bloat.
3. **`Tests/test_e2e_architecture_integration.py.disabled`** — still
   awaiting deletion.
4. **A domain-parity guard** would make §2 and §3 impossible rather than
   merely caught: assert that `DISPATCH.keys()`, the `SimulationDomain`
   union, and `SimulationParameterSchemas` are the same set. The Python
   half is covered by the boundary contract test; the TypeScript half is
   not covered by anything.

## 6. References

- ADR 0007 — engine/application boundary; the contract that was inverted.
- ADR 0015 — a rule nothing executes is not enforced; the principle the
  missing TypeScript check violated.
- `scripts/check_typescript_compiles.py` — full rationale in its docstring.
