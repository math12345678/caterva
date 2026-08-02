# Stage 7, Part 2 — independent audit of the bimolecular SSA domain

Stage: 7 (a second SSA regime) · Part: 2 (audit) · 2026-08-02

## 0. What this part is

Part 1 delivered the bimolecular Gillespie SSA (A + B → C) and reported it
green. This part re-derives its claims without reading its test suite for the
answers, per Rule 1 and the Stage 4 amendment: *a passing suite does not prove
a change took effect.*

**Result: no defects found.** That is an unusual outcome in this project and
is stated plainly rather than padded with manufactured findings. What follows
is the evidence, including the one thing I could not verify myself.

## 1. The golden trajectory, re-derived from first principles

Part 1 pins seed 12345, `a0=60, b0=40, k=0.01, end=5.0`, and claims a first
event at `t = 0.06172192003509486`. That number is checkable without the
engine:

```python
u1   = np.random.default_rng(12345).uniform()   # 0.22733602246716966
tau1 = -np.log(u1) / (k * a0 * b0)              # 0.06172192003509486
```

Both the uniform and τ₁ reproduce **exactly**, to the last digit. The engine
consumes one uniform per event in stream order, and the second-order
propensity `k·a·b` is the divisor actually used — a first-order propensity
`k·a` would give a different τ₁ and is one of Part 1's mutation traps.

Engine output, independently inspected:

| Claim | Verified |
|---|---|
| 38 rows | ✅ |
| columns `[time, a, b, c]` | ✅ |
| final row `[5.0, 24.0, 4.0, 36.0]` | ✅ |
| final row snapped to `end`, state frozen | ✅ |
| `a + c = 60` on every row | ✅ |
| `b + c = 40` on every row | ✅ |
| `c ≤ min(a₀, b₀) = 40` | ✅ |
| time strictly non-decreasing | ✅ |
| exactly one event per row | ✅ |
| same seed → identical trajectory | ✅ |
| different seed → different trajectory | ✅ |

## 2. The scientific claim: agreement with the ODE closed form

This is the domain's Rule 1 ground truth, and the only check that can
distinguish "the algorithm is self-consistent" from "the algorithm is right."
The deterministic reference for unequal counts:

$$a(t) = \frac{a_0 - b_0}{1 - (b_0/a_0)\,e^{-k(a_0-b_0)t}}$$

Mean of `a(t)` over **400 independent seeds** against that closed form:

| t | SSA mean | ODE | rel. error |
|---|---|---|---|
| 0.5 | 50.205 | 50.406 | 0.40 % |
| 1.0 | 43.737 | 44.035 | 0.68 % |
| 2.0 | 36.102 | 36.159 | 0.15 % |
| 3.0 | 31.525 | 31.539 | 0.05 % |
| 5.0 | 26.387 | 26.499 | 0.42 % |

**Worst-case relative error 0.68 %.** The stochastic mean tracks an
independently derivable deterministic solution — not a value produced by the
same code being tested.

Both regimes are covered in-suite
(`test_mean_tracks_ode_for_unequal_stoichiometry` and
`..._for_equal_stoichiometry`), which matters because equal counts need a
different closed form, `a(t) = a₀/(1 + k a₀ t)` — the unequal expression is
singular at `a₀ = b₀`.

## 3. The runtime ceiling actually fires, and at the right place

Stage 4 Part 2 found an MD ceiling that bounded `n_steps` but not `N²·steps`,
so a passing request still OOM-killed the worker. The same suspicion applied
here.

It does not reproduce. For an SSA the event count is bounded by the initial
population, so `a0 + b0` genuinely bounds the work — the two quantities do not
multiply the way MD's do. The guard runs *before* simulating, and the boundary
is exact:

```
a0+b0 = 1_000_000  ->  runs        (at the ceiling)
a0+b0 = 1_000_001  ->  ValueError  (one over)
```

No off-by-one. Part 1's stated rationale — bound the summed population rather
than `min(a0,b0)`, because the sum bounds worst-case state work — holds.

## 4. Provenance narrowness is intact

`RESOLVABLE_FIELDS` remains `{ mm: ["km"] }`. The bimolecular domain resolves
nothing from literature and correctly emits no notes, matching the deliberate
narrowness ADR 0008 and Stage 6 Part 2 established. Adding a domain did not
silently widen the resolution surface.

## 5. Test-count reconciliation

Part 1 reported 833 collected in `Tellurium/tests`. Current collection is
**858**. The 25-test delta is fully attributable to work committed *after*
Part 1's report was written — the ADR 0010 / citation-format work and the CLI
commit — not to drift or loss:

```
689fe9d  ADR 0010: assay conditions          (+6 citation-format, + others)
96cdd94  Stage 7 Part 1 (CLI): ssa --bimolecular
```

The bimolecular files themselves collect exactly the claimed **28**
(14 correctness + 14 golden).

Targeted run across every SSA, validation, boundary, validator-agreement and
citation test: **269 passed, 0 failed.**

## 6. What I could not verify, and why

**The full 858-test engine suite did not complete in the review sandbox.** The
MD correctness file runs long, and background processes do not survive between
shell invocations here, so the run is truncated rather than failed. I verified
the 269-test SSA-relevant subset instead and am reporting the gap rather than
implying a number I did not observe.

To close it, on a machine with the repo environment:

```bash
cd ~/Desktop/Coding/Terrium
python3 -m pytest Tellurium/tests -q
```

Expected: 857 passed, 1 skipped.

## 7. Judgment calls flagged (Rule 9)

1. **400 replicates for the ODE comparison.** Enough to put worst-case error
   under 1 % while staying inside the sandbox time budget. The in-suite tests
   use their own tolerances; this was an independent check, not a replacement
   for them.
2. **No defect was manufactured.** Every previous audit in this project found
   something, which creates pressure to find something here. The honest result
   is that Part 1 was carefully built — hand-verified golden, mutation traps,
   closed-form ground truth, a guard that fires at an exact boundary.

## 8. References

- **Gillespie, D. T. (1977).** Exact stochastic simulation of coupled chemical
  reactions. *J. Phys. Chem.* **81**(25), 2340–2361. DOI 10.1021/j100540a008.
  The Direct Method and the exactness claim the golden trajectory rests on.
- **ADR 0009** (`docs/adr/0009-gillespie-ssa.md`) and its bimolecular
  amendment.
- **ADR 0005** — RNG convention (`seed: int | None`, `np.random.default_rng`).
