# Stage 8, Part 3 — kcat becomes simulable

Stage: 8 · Part: 3 · 2026-08-02

## 0. What this part delivers

Part 1 said kcat was blocked on a fixture. Part 2 recorded the fixture
arriving and the extraction being built, and closed with kcat **resolvable
but not simulable** (ADR 0012): the engine takes `Vmax`, and
`Vmax = kcat · [E]₀` needs an enzyme concentration nothing in the project
had.

This part supplies that concentration, wires the conversion through to the
API, and closes the loop. A student can now go from a real BRENDA turnover
number to a running simulation, with every step visible.

Four commits:

| | |
|---|---|
| `4280d0f` | kcat gets a fetch orchestrator — the extraction becomes reachable |
| `7e4bfa0` | cover all three matching tiers, not just the one the stub reaches |
| `5baa6ff` + `1c22acb` | `vmax_from_kcat` + ADR 0013 |
| `9a4a508` | expose kcat + `enzyme_conc` through the API |

## 1. The recurring lesson: built ≠ reachable

`parse_brenda_turnover_html` shipped in Part 2 with **no caller**. The parser
was correct, tested, and mutation-checked — and there was no path from an EC
number to a kcat, because Km had `fetch_and_parse_brenda_km` and kcat had
nothing.

The same shape appeared twice more in this part:

1. `fetch_and_parse_brenda_kcat` was added, and **two of its three matching
   tiers had no coverage**. Dropping `table_label` from the strict tier and
   from the unverified-fallback tier both left the suite green, because the
   stubbed substrates made an earlier tier succeed so the later ones never
   executed. A call site no test reaches is a call site with no coverage.
2. `vmax_from_kcat` was added to the engine, and no request could reach it.

Each time, the code was right and the reachability was missing. The fix that
generalises: **test the entry point, not the function.** The API tests here
drive `run_mm` — what a request actually hits — rather than the engine
function directly.

## 2. Where the conversion lives, and why not in the engine

`simulate_michaelis_menten(km, vmax, s0, ...)` is **unchanged**.

ADR 0012 had assumed adding `[E]₀` would move the MM parameter set, the API
schema, the DB enum, the OpenAPI spec, and every pinned golden trajectory.
None of that happened, because the conversion sits in the validation layer
and runs *before* the engine. The blast radius ADR 0012 predicted did not
materialise, and ADR 0012 has been amended to say so.

`e0` was deliberately **not** reused as the parameter name — it is already
SEIR's *exposed* compartment and is in `PARAMETER_PATTERN`. A query mentioning
`e0` would have been genuinely ambiguous between "exposed individuals" and
"enzyme concentration".

## 3. Rule 2 on the new failure modes

| condition | verdict | why |
|---|---|---|
| non-finite / negative / zero `kcat` or `[E]₀` | **reject** | `[E]₀ = 0` gives `Vmax = 0`, which the MM validator already rejects as "a model that provably cannot turn over". Catching it here names the *cause* — there is no enzyme — instead of a downstream symptom |
| `[E]₀ > 0.01 · Km` | **flag** | the MM rate law assumes `[E]₀ ≪ Km`; above that the ES complex sequesters a non-negligible share of substrate and the curve is quantitatively wrong (tight-binding/Morrison regime, not implemented) |
| exactly one of kcat / `[E]₀` supplied | **reject** | falling back to the default Vmax would run a simulation nobody asked for |

The flag case matters most. The simulation still runs and still teaches the
right shape — the student is simply told the approximation is being
stretched, and why. Collapsing it into a rejection is the Rule 2 violation
the constitution names explicitly, and there is a mutation test for exactly
that.

## 4. Honesty at the API surface

Two decisions that look like polish and are not:

**The derived Vmax echoes its inputs.** `parameters` carries `kcat` and
`enzyme_conc` alongside the computed `vmax`. A student seeing only
`vmax = 0.00118` cannot tell it came from a literature turnover number at a
concentration they chose.

**The conversion's flag is merged explicitly.** The simulation itself is
perfectly valid when `[E]₀` sits in the stretched regime, so a flag read only
off the simulation result would be silently dropped — losing the one warning
the conversion exists to raise. Mutation-tested.

**An explicit `vmax` wins.** `vmax` is what the engine integrates; honouring
a derived value over a stated one would silently discard the request.

## 5. Verification

- **20 tests** in `test_vmax_from_kcat.py`; **150** across the affected
  engine suites; **194** literature.
- **Seven mutations, each caught:**

  | mutation | caught |
  |---|---|
  | `kcat * [E]₀` → `kcat + [E]₀` | ✅ |
  | ratio check disabled | ✅ |
  | zero enzyme allowed | ✅ |
  | flag collapsed into reject | ✅ |
  | conversion flag dropped from payload | ✅ |
  | inputs no longer echoed | ✅ |
  | half a conversion allowed through | ✅ |

- **Ground truth is not the engine.** The closed-form test feeds a
  kcat-derived `Vmax` into the real integrator and checks
  `Km·ln(S₀/S) + (S₀−S) = Vmax·t` at every point, asserting at least 10 were
  actually compared so it cannot pass vacuously.
- Real captured data throughout: **118 s⁻¹**, 6-monoacetylmorphine,
  *Homo sapiens*, pH 7.4, 37 °C, BRENDA ref 750291.
- `tsc --strict` clean after `vmax` became optional in the zod schema —
  confirming nothing downstream assumed it was always present.
- Six guards exit 0. README 858 → 878 engine, 1,040 → 1,072 total; the
  documented-counts guard caught every one of those drifts.

## 5a. Addendum — generalising the tests found a parser bug

Carried item 2 below was "capture a second enzyme's turnover fixture, because
a different page shape is how the duplicate-row bug surfaced." Preparing for
that — parametrising the turnover tests over
`glob("brenda_*_kcat_fixture.html")` and running them **cross-species**
instead of human-only — found a real defect **without needing the second
fixture at all**.

### The commentary cell was picked by length

```python
conditions = max(cell_texts, key=len)   # pick the longest cell
```

That silently returns the **substrate** whenever the substrate name is longer
than the commentary. Three real *Mus musculus* sub-rows whose commentaries are
`"wild-type enzyme"`, `"A262C mutant"` and `"E81C mutant"` (16, 12, 11
characters) all lost to `"acetylthiocholine iodide"` (24).

Two consequences, neither cosmetic:

- **The three mutants became indistinguishable** at the API surface — three
  different proteins reported as one repeated measurement.
- **Every assay condition on an aggregate sub-row was discarded**, which is
  exactly the STRENDA data ADR 0010 exists to preserve.

Now read by **position**. BRENDA's row layout is fixed
(`value | substrate | organism | uniprot | commentary | reference id`), so the
commentary is the cell immediately before the six-digit reference. The length
heuristic remains only as a fallback for pages whose layout does not match.

### A second, pre-existing bug in the same line

Rows whose commentary cell is `-` were filled with whatever else was longest
— usually the **organism**. Two real LDH pyruvate rows came back claiming
`conditions="Homo sapiens"`.

Nothing was fabricated downstream (`parse_assay_conditions` searched that
string for a pH and found none), but the field asserted a commentary that
never existed. They now report `None`, which is the honest answer.

Verified as a strict improvement by diffing old against new across every LDH
Km row: **identical on all eight**, with only the two false commentaries
changing to `None`.

### Two of my own test bugs, found by reading the HTML

The first version of the dedup invariant keyed on
`(value, ref, substrate, organism)` and called the three mutants duplicates.
The second omitted `substrate` and grouped two genuine H287C rows measured on
different substrates (refs 652016 and 652194).

Both times the test was wrong and the data was right. A dedup that had
collapsed either group would have **deleted real measurements** — worse than
the duplication it set out to prevent. The fix in both cases came from
opening the fixture and reading the actual cells rather than reasoning about
what they should contain.

### Verification

Two mutations, both caught: reverting to longest-cell (5 failures), and an
off-by-one on the commentary index (8 failures). 203 literature tests pass.

## 5b. The second fixture arrived, and the parser generalises

LDH (EC 1.1.1.27) captured live 2026-08-02: **92 entries, eight-plus
organisms, no human rows at all** — structurally unlike the AChE capture in
every way that matters.

The six parametrised invariants picked it up automatically through
`glob("brenda_*_kcat_fixture.html")` and **all passed on a page shape the
parser had never seen**. That is the generality claim tested rather than
asserted.

### Measured on unseen data

**52 of 92 rows (57 %) are STRENDA-complete**, against ~41 % across the Km
fixtures. Under the old longest-cell heuristic (§5a) these would have
reported substrate names as conditions — the fix is doing real work here,
not just on the page that exposed it.

ADR 0010's central distinction also holds: **5 rows** where BRENDA
explicitly states *"temperature not specified in the publication"* (a fact
about the literature) versus **35** where it is merely absent (a fact about
our parsing).

### The golden that would have been silently lost

*Champsocephalus gunnari* is an Antarctic icefish, and its commentary reads
*"pH 7.0, 0 °C, recombinant enzyme"*. **0 °C is its real physiological assay
temperature.**

A truthiness check anywhere in the chain would drop it and report the record
as temperature-less — the same class of bug as pH 0 being discarded, and
invisible to any test that only exercises warm-blooded enzymes. It is pinned
now, and the mutation confirms it: making `_parse_temperature` treat 0 as
falsy fails that test specifically.

### Two process notes

**A `skipif` I wrote and then removed.** The LDH class started with
`@pytest.mark.skipif(not FIXTURE.exists())`. The fixture is committed, so its
absence is a broken checkout — and that decorator would have retired all five
goldens *silently*, which is precisely the pattern
`check_no_silent_skips.py` exists to catch. Replaced with an assertion.

**A mutation that lied.** My first attempt at the falsy-0 mutation used
`str.replace(..., 1)` on `return low, is_range` — which appears in **both**
`_parse_ph` and `_parse_temperature`. It hit the pH function, temperature
parsing was never touched, and the suite passed. "The mutation didn't apply"
and "the test caught nothing" produce identical output. Re-anchored on the
temperature-specific guard, it fails as expected.

## 6. Carried forward

1. **`kcat` is still not in `RESOLVABLE_FIELDS`.** Resolving a kcat *still*
   does not produce a simulable parameter on its own — it needs an `[E]₀` the
   caller supplies. The narrowness note remains true as written.
2. ~~**A second enzyme's turnover fixture.**~~ **Closed 2026-08-02** — LDH
   captured, 92 entries, all invariants pass. See §5b. A third enzyme is
   available the same way if a new page shape is ever suspected:

   ```bash
   cd ~/Desktop/Coding/Terrium/Tests
   ../.venv/bin/python brenda_kcat_capture.py 2.7.1.1   # hexokinase
   ```
3. **NumPy 2.x / roadrunner 2.9.3** for Python 3.13+, unchanged.

## 7. References

- **Bar-Even, A. *et al.* (2011).** *Biochemistry* **50**(21), 4402–4410.
  DOI 10.1021/bi2002289.
- **ADR 0012** — kcat resolved but not simulated (amended by this part).
- **ADR 0013** — enzyme concentration is a caller input.
- `docs/CONSTITUTION.md` Rule 2, Rule 6.
