# Stage 10, Part 22 — tests that could not fail

Stage: 10 · Part: 22 · 2026-08-11

## 1. One instance, or a class?

Part 20 left a vacuous assertion in `kcatProvenance.test.ts` on the open
list:

```ts
const provenance = resolved.parameterProvenance["enzyme_conc"];
if (provenance) {
  expect(provenance.origin).not.toBe("resolved");
  expect(provenance.citation).toBeUndefined();
}
```

`enzyme_conc` is absent from `RESOLVABLE_FIELDS` **by design**, so
`provenance` is always `undefined`, the guard is always false, and neither
assertion has ever executed.

Fixing that one line would have taken a minute. But this is the fourth time
this session the same shape has appeared — `cachedProvenance.test.ts`
returning early on a failed poll (Part 5), a Part 12 regression test that
passed against the very bug it was written for, and this. A guard for the
class is worth more than a fix for the instance.

`scripts/check_no_vacuous_tests.py` finds tests where **every** `expect(`
sits inside a conditional. First run: **twelve**, across seven files.

## 2. The defect has two shapes

The one above **skips**:

```ts
if (provenance) { expect(...) }        // guard false -> nothing runs
```

The other **accommodates**:

```ts
if (trajectory.length === 0) expect(validated).toBe(false);
else                         expect(validated).toBe(true);
```

Nothing is skipped there — and the test still cannot fail, because it has
an answer ready for both outcomes and therefore states no expectation about
which should happen. Its name was *"should reject simulation with no
trajectory points"*, while its input (km 5.2, comfortably inside the
literature range) guaranteed the other branch. The case it was named for
never ran.

Both shapes are one thing: **a test with no way to go red.** The guard
tracks `else` as part of the conditional it belongs to, so it catches both.

## 3. What honesty immediately exposed

Three `routes.test.ts` tests polled a job and did this:

```ts
if (getRes.body.status === "failed") {
  // Pipeline may fail if Python/Tellurium environment isn't available
  return;
}
```

Passing when the simulation worked **and** when it didn't. Replaced with an
`awaitJob` helper that throws with the job's own error text.

On the first honest run:

```
job fdab713c… failed: {"error":"MISSING_REQUIRED_INPUT","message":
"Cannot simulate 'sir': s0, i0, r0_recovered, end, points could not be
resolved from literature and were not supplied in the query."}
```

The query was `"simulate sir beta=0.5 gamma=0.1"` — missing all five
experimental conditions. **That test had never once run the pipeline.** Its
six assertions, including the two checking that beta and gamma survive the
round trip, had never executed. It reported green for as long as it has
existed.

This is the ADR 0012/0013 refusal working exactly as intended — conditions
are chosen, never defaulted — and a test written as though they were
optional.

## 4. Found by running the full suite: a validator stricter than its engine

Two failures turned up in `request-validator.test.ts`, a file I had not
touched. Not a flake:

```ts
// batch-processor.ts:197 — what the engine actually runs
parameters: { ...baseParameters, ...params }
```

```ts
// request-validator.ts — what the validator checked
const requiredParams = ['km', 'vmax', 's0'];
for (const param of requiredParams) {
  if (!(param in params)) { /* "km is required" */ }
}
```

The validator checked each `parameterSet` **in isolation** while the engine
merges `baseParameters` underneath it. So:

- `baseParameters` was decorative — every set had to repeat all three
  values in full, and the field could never carry anything.
- The rejection **named a parameter the caller had supplied**: *"s0 is
  required"* for a request whose `baseParameters` said `s0: 10`. That sends
  someone looking in the wrong place entirely.
- The engine would have run those requests without complaint.

The tests were right and the source was wrong. Now validated against the
merged effective set, with the error naming `baseParameters.s0` when that is
where the bad value lives. Four regression tests added — the merge had no
coverage at all, which is how the two drifted apart — and mutation-verified:
reverting `{...base, ...params}` to `{...params}` fails all four.

`Number.isFinite` added while there. `Infinity > 0` is true, so an infinite
Vmax passed the old check and produced a trajectory of `NaN` rather than an
error.

## 5. A third guard: tests that do not run at all

The family now has three members, covering the same blind spot from three
sides:

| guard | catches |
|---|---|
| Orphan Module | code nothing runs |
| Vacuous Test | tests that run but cannot fail |
| Disabled Test | tests that do not run, silently |

`check_no_disabled_tests.py` refuses `.only` outright — one committed
`describe.only` disables every sibling in its file while the suite still
reports green — and requires any `.skip` to **announce itself** on
`console.warn`. The three current skips (Python engine genuinely absent) all
do, in the shape Part 21 established for stdpopsim:

> The rule is not "never skip". It is "never skip quietly".

## 6. My own guard's first run was wrong

`check_no_disabled_tests.py` flagged two files that announce themselves
perfectly well. The announcement regex used `[^;]{0,600}?` — "stay inside
one statement" — and both messages contain a semicolon inside the string
literal:

```
'python3 unavailable; subprocess tests are SKIPPED, not passing.'
                    ^
```

A semicolon in a string is not a statement boundary, and only a parser can
tell the difference. `telluriumBridge.test.ts` passed purely because its
wording happened not to need one.

Worth recording because it is the exact failure mode the *other* guard's
docstring warns about: a check that flags correct code gets suppressed, and
then catches nothing. Fixed to a bounded `.` with `DOTALL`, and the reason
is in the source next to the regex.

## 7. Verification

| check | result |
|---|---|
| `check_no_vacuous_tests.py` | 12 → 0; mutation-caught on both shapes; clears three legitimate patterns; refuses an empty scan |
| `check_no_disabled_tests.py` | clean; catches `.only` and silent `.skip`; passes an announced skip |
| `check_guard_wiring.py` | 19/19 guards wired |
| api-server (vitest) | **427 / 427** |
| root (jest) — validation, reproducibility, integration, `__tests__` | **176 / 176** |
| `tsc --noEmit`, both trees | 0 errors |
| `check_documented_counts.py` | 1,289 = 1,014 + 275, unchanged |

The word-boundary check in the vacuous guard (`notif (x)` is not a
conditional) is mutation-verified too — a guard that invents violations is
worse than none.

## 8. Open

- **The count guard cannot see TypeScript.** `check_documented_counts.py`
  counts only `Tellurium/tests` and `Tests/`, so ~600 TypeScript tests are
  undocumented and a suite that stopped being discovered would not move the
  number. `vitest list` takes 150s (it imports every file), so the cheap fix
  isn't available; the Disabled Test Guard covers the most likely cause but
  not all of them.
- Opt-in locator consistency (`provenance.ts:322`).
- Four dormant silent skips in `verify_citations_live.py`.
- Three duplicate modules, read and harvested (Part 19), retirable at will.
