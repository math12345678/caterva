# Stage 4, Part 1 — Domain Choice and Grounding: the Engine/Application Boundary

Stage 4 of 100. 96 remain after this one closes.

## 1. This stage has no scientific domain, and that is the point

Stages 1 through 3 each took a piece of physics or biology, grounded it in
literature, specified it, built it twice independently, and verified it
against exact mathematics. Stage 4 breaks that pattern deliberately.

The subject of this stage is the **boundary between the engine and the
product**. There is no new science in it. There is, however, a verification
problem of exactly the kind the constitution exists for, and it is currently
sitting outside every guard the project has built.

The case for interrupting the domain sequence is in
`Business/ARCHITECTURE_ASSESSMENT.md` and was accepted in Stage 3 Part 5's
amendment A1, which overturned that report's own recommendation of Gillespie
SSA as the Stage 4 domain. Summarised: the engine has eight simulation
functions and the product can reach three of them. Adding a ninth does not
help.

## 2. What is actually there, measured rather than assumed

Everything below was verified by reading and running the code, not from the
data-flow diagram.

### 2.1 The boundary works

```
$ echo '{"domain":"mm","parameters":{"km":2.0,"vmax":5.0,"s0":10.0,
        "end":1.0,"points":3}}' \
  | PYTHONPATH=. python3 .../src/lib/tellurium_runner.py

{"ok": true, "domain": "mm",
 "parameters": {...},
 "trajectory": [{"time": 0.0, "[S]": 10.0, "[P]": 0.0}, ...],
 "flagged": false, "flagReason": null}
```

This is real. `tellurium_runner.py` does `from Tellurium import
tellurium_engine` and calls the same `simulate_michaelis_menten` the test
suite verifies against the implicit closed form. The application is not
running a copy or a reimplementation.

Note what survives the crossing: `ok`, `flagged`, `flagReason`. **Rule 2's
contract holds across the language boundary.** That is the load-bearing thing
this stage does not need to fix, and it is worth stating plainly before
cataloguing what is broken.

### 2.2 Five of eight domains are unreachable

```python
if domain == "mm":      result = run_mm(params)
elif domain == "sir":   result = run_sir(params)
elif domain == "seir":  result = run_seir(params)
else:
    raise ValueError(f"unknown domain: {domain!r}")
```

Asking the product for anything else produces, verbatim:

```
$ echo '{"domain":"pcr","parameters":{}}' | python3 tellurium_runner.py
{"ok": false, "error": "unknown domain: 'pcr'"}
```

| engine function | reachable |
|---|---|
| `simulate_michaelis_menten` | yes |
| `simulate_sir` | yes |
| `simulate_seir` | yes |
| `simulate_pcr` | **no** |
| `simulate_monte_carlo_pi` | **no** |
| `simulate_wright_fisher` | **no** |
| `simulate_two_locus_wright_fisher` | **no** |
| `simulate_molecular_dynamics` | **no** |

The three reachable domains predate Stage 1. **Every domain built under the
constitution is unreachable.** The mutation contracts, Kimura's fixation
probability, LJ13 against Hoare & Pal — none of it is in the product.

### 2.3 The application layer has 53 tests and CI runs none of them

`package.json` already defines `"test": "vitest run"`. The tests exist:

```
src/__tests__/queue.test.ts       23 tests
src/__tests__/routes.test.ts      29 tests
src/__tests__/rateLimit.test.ts    1 test
```

`.github/workflows/tests.yml` contains zero occurrences of `npm`, `pnpm`,
`vitest`, or `api-server`. Fifty-three tests, written, passing presumably,
and not enforced by anything.

This is the cheapest finding in the stage to fix and among the most valuable:
the work is already done, it just isn't gated.

### 2.4 `validateParameters()` does much less than the diagram implies

The data-flow diagram shows a `validateParameters()` node parallel to
`resolveQuery()`. In the code, `src/lib/validate.ts` exports exactly one
thing:

```typescript
export function validate(schema: ZodSchema, target: ValidationTarget = "body")
```

A generic Zod middleware factory. And `schemas.ts` defines schemas for
`WaitlistBody`, `ResolveBody`, `CancelJobParams`, `ExportJobParams` — **and
no simulation-parameter schema at all.**

So simulation parameters are not validated at the HTTP boundary. They are
coerced with `float(params.get("km", 2.0))` in the runner and then validated
by the engine. That is not a disaster — the engine's validation is the good
validation, and it runs. But it means:

- a malformed request reaches Python before being rejected,
- the defaults live in the runner (`km=2.0`, `vmax=5.0`) where no domain
  spec governs them, invisible to the constitution,
- and a caller passing `km="abc"` gets a `ValueError` string rather than a
  structured `ok:false` validation response.

Whether to push validation to the boundary or leave it in the engine is a
real architectural decision, and Part 2 must make it explicitly rather than
inherit it.

### 2.5 One latent fragility worth fixing now

```typescript
const LEVELS_UP = _dirname.replace(/\\/g, "/").endsWith("/dist") ? 4 : 5;
const REPO_ROOT = path.resolve(_dirname, ...Array(LEVELS_UP).fill(".."));
```

`REPO_ROOT` is derived by counting directory levels. Checked: from
`artifacts/api-server/src/lib`, five levels up is the repo root; from
`artifacts/api-server/dist`, four is. Both correct **today**.

They are correct because of where this directory currently sits, and this
directory has already moved once — when Science-Agent-Pipeline was folded
into the main repo. A hardcoded depth count is a silent coupling between a
path and a constant, and it fails by pointing `PYTHONPATH` at the wrong
directory, which surfaces as `ModuleNotFoundError: No module named
'Tellurium'` far from its cause.

This is the same failure shape as the eigenvector sign bug and the
`Tellurium.tellurium_engine` import removed in Stage 3's audit: correct under
one configuration, silently wrong under another, with the error appearing
somewhere unrelated.

## 3. The verification problem this stage exists to solve

Applying Rule 1 — *every claim checked against an independent source of
truth* — to the boundary rather than to numerics.

The engine's claim is *"this simulation is mathematically correct."* It backs
that with closed forms, published values, and mutation tests. Strong.

The product's claim is *"every number traces back to a citation that has been
independently checked."* **Nothing verifies that claim.** Not one test.

Here is the mechanism, traced through the real code:

```
BRENDA row  ->  fallback_logic  ->  queryResolver  { citations: string[] }
                                         |
                                    parameter value only
                                         v
                              tellurium_runner.py  (citations dropped)
                                         v
                              tellurium_engine     (no citation field exists)
                                         v
                              SimulationResult     (validation, no provenance)
                                         v
                              api-server           (citations re-attached
                                                    from the resolver)
```

The number and its citation travel in **separate channels** and are rejoined
at the end. `grep -c citation Tellurium/tellurium_engine.py` finds nothing —
the engine has no citation, source, or organism field. Its
`SimulationResult` docstring says *"provenance needed for the trust trail,"*
and the class carries validation state only.

The consequence, stated as plainly as it deserves: **if the resolver returns
a Km from the wrong organism, the engine simulates it faithfully and the
product returns `ok: true, flagged: false` with a citation attached.** The
system reports VERIFIED for a wrong number. No existing test would fail.

That is the precise failure the product exists to prevent, in the one layer
the constitution has never been applied to.

## 4. Scope: what Stage 4 does, and what it deliberately defers

Stage 4 is the **mechanical** half. Stage 5 is the provenance contract, which
is a design problem and deserves its own grounding.

**In scope for Stage 4:**

1. Expose the five unreachable domains through `tellurium_runner.py`,
   following the existing `run_mm` shape exactly, including `ok` / `flagged` /
   `flagReason` propagation.
2. Add an application-layer CI job that runs `vitest run`.
3. **A cross-boundary contract test** (Rule 4 — shared constraints enforced
   by a test, not a comment): fail if `tellurium_engine.__all__` gains a
   `simulate_*` function the runner does not dispatch. Without this the gap
   reopens the first time Stage 6 adds a domain, and reopens silently.
4. Replace the `LEVELS_UP` depth heuristic with an anchored root discovery
   (walk upward for a marker file), plus a test.
5. Decide, explicitly and in writing, whether simulation parameters get Zod
   schemas at the HTTP boundary or stay engine-validated.

**Explicitly out of scope, deferred to Stage 5:**

- Provenance carried through the engine — the `ParameterSource` design.
- A `verified` / `flagged` / `rejected` contract for citations as distinct
  from values.
- A golden set of hand-verified enzyme/substrate/Km/citation tuples.
- Mutation testing the resolver.

**Out of scope entirely:**

- Rewriting the application layer. It is reasonable code and Rule 2 already
  survives it.
- Moving the api-server into the Python package. The language split is fine;
  the boundary needs a contract, not a merge.
- New simulation domains. Gillespie SSA is first in the queue at Stage 6.

## 5. Applying the nine rules to a non-scientific stage

**Rule 1 (independent verification).** The ground truth here is not a closed
form — it is the engine's own `__all__`. The contract test compares the
runner's dispatch table against it, so the two cannot drift. That is the
boundary's equivalent of checking against an exact solution.

**Rule 2 (`ok`/`flagged`).** Already satisfied across the boundary; the new
domains must not break it. Each new `run_*` must propagate `flagged` and
`flagReason` — Wright-Fisher and MD both have real flag conditions
(`replicate_runs < 10`, `temperature > 0.8`), so this is testable, not
theoretical.

**Rule 3 (continuous vs. discrete).** Not applicable — no simulation is being
written. Noted rather than skipped.

**Rule 4 (shared constraints enforced by test).** The central rule of this
stage. The dispatch table and `__all__` are the same constraint written in
two places; item 3 makes drift fail loudly.

**Rule 5 (dependency declarations).** No new Python dependency. The CI job
adds Node, which is new tooling and must be pinned in the workflow.

**Rule 6 (mutation testing).** Applies, in a new form. Pre-specified: delete
one `elif` branch from the dispatch table and confirm the contract test
fails. If it passes, the contract test is decorative — the same check applied
to Stage 3's regression tests during its audit.

**Rule 7 (no umbrella package).** Not applicable; noted.

**Rule 8 (ADRs).** One anticipated: **ADR 0007**, recording that the
engine/application boundary is enforced by a contract test rather than by a
shared schema or a code-generation step. That is architecturally significant
and someone will otherwise propose generating the runner from `__all__`.

**Rule 9 (conservative defaults, judgment calls flagged).** Two flagged here
for Part 2: the parameter-validation question (§2.4) and whether Monte Carlo
and MD belong in a request/response API at all, given both can run for
seconds — the queue exists, but no `run_*` has yet had a genuine runtime
concern.

## 6. What Part 2 must resolve

1. The dispatch shape for five new domains, including their default
   parameters — which currently live in the runner, ungoverned by any spec.
2. The contract test's exact mechanism: parse `__all__`, or import and
   introspect? Chosen with a reason.
3. Runtime bounds. `simulate_molecular_dynamics` at `n_steps=10000` is not a
   sub-second request; `simulate_monte_carlo_pi` at large `n_samples` neither.
   Does the runner enforce a ceiling, does the queue handle it, or does the
   spec cap the parameters?
4. The CI job: Node version, package manager (the repo has both a
   `pnpm-lock.yaml` and npm usage — that inconsistency needs resolving), and
   whether the job blocks merges.
5. The `LEVELS_UP` replacement, with a test that fails if the api-server
   directory moves.
6. The parameter-validation decision from §2.4, stated with its reason.

Part 2 writes the full spec using the ten-field template in
`docs/CONSTITUTION.md` Section 4, adapted where a field genuinely does not
apply — and saying so explicitly rather than leaving it blank.
