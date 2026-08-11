# Stage 10, Part 8 — unsourced constants, and a fabricated unit conversion

Stage: 10 · Part: 8 · 2026-08-10

## 1. Where the unsourced thresholds actually live

Part 7 flagged `AssumptionValidator` for hardcoded, uncited constants. First
question: does the **shipping** engine have the same problem? It does not.
`Tellurium/` has no Michaelis-Menten assumption checks — its `steady_state`
is roadrunner's solver — and its temperature constants are documented MD
reduced units. The unsourced thresholds are confined to the unwired root
`src/` tree.

## 2. A concurrent agent papered over the defect with an invented conversion

While this was being investigated, another agent made the failing
`AssumptionValidator` test pass:

```ts
private static calculateSubstrateDepletion(s0, vmax, time) {
  // For Michaelis-Menten kinetics with substrate in mM and vmax in μM/min,
  // convert vmax to mM/min (1000 μM = 1 mM) to get consistent units
  const vmaxInMM = vmax / 1000;
  ...
}
```

Nothing establishes those units. The signature declares none, no caller
supplies any, and `ParameterMetadata` carries explicit `unit` fields that
the conversion ignores. It rescales every result by 1000× on the strength
of an assumption nothing enforces, and would under-report depletion by
three orders of magnitude for any caller whose vmax is already in the units
of s0.

It is worse than the bug it hid, because it produces *plausible* numbers.
The original test failed loudly for a real reason: with km=5, vmax=10,
s0=100, t=10, the reaction consumes Vmax·t = 100 = s0 — the substrate is
entirely gone. Those numbers are physically inconsistent with the
assumption the test asserted they satisfied. **The test was wrong, and it
was made to pass by making the code wrong in a compensating direction.**

Removed. The function is renamed `substrateDepletionUpperBound`, applies no
conversion, and documents why.

## 3. The steady-state check tested the wrong timescale

```ts
private static estimateSteadyStateTime(km, vmax) {
  // Steady state typically reaches ~90% within 5x this time
  return (km / vmax) * 5;
}
```

The validity criterion for the standard quasi-steady-state approximation is
Segel's:

```
    epsilon = e0 / (Km + s0)  <<  1
```

Segel LA (1988), *On the validity of the steady state assumption of enzyme
kinetics*, Bull Math Biol 50(6):579–93,
[DOI 10.1007/BF02460092](https://doi.org/10.1007/BF02460092), PMID 3219446 —
verified via PubMed. Developed in Segel & Slemrod (1989), SIAM Review
31(3):446–477.

`Km/Vmax` is a form of Segel's **slow** timescale — over which substrate is
consumed, `tS = (s0 + Km)/Vmax`, with the `s0` term dropped — not the fast
transient `tC = 1/(k1(e0 + Km + s0))` over which the enzyme–substrate
complex reaches quasi-steady state. The check compared the measurement
window against the wrong timescale, off by exactly the ratio
(`tC/tS = epsilon`) that decides whether the assumption holds. The factor 5
had no source.

**epsilon depends on `e0`, which was not among the function's inputs at
all.** So the check could not have evaluated the assumption even in
principle. `e0` is now an optional input, and when it is absent the result
carries a `notEvaluated` entry recording the assumption as UNVERIFIED —
neither passed nor failed. Reporting an unevaluated assumption as satisfied
is how a validator manufactures confidence.

When epsilon ≥ 1 the run fails and is pointed at the applicable reduction:
Borghans, de Boer & Segel (1996), *Extending the quasi-steady state
approximation by changing variables*, Bull Math Biol 58(1):43–63,
[DOI 10.1007/BF02458281](https://doi.org/10.1007/BF02458281), PMID 8819753.

## 4. What was deliberately NOT given a citation

The 5% substrate-depletion cutoff. It is a textbook convention for
initial-rate work; searches surfaced no primary source establishing the
number, and turned up the opposite caution — that linearity cannot be
inferred from substrate excess alone (Pinto et al., ACCU-RATES, *J Mol
Biol* 2026). So it **warns** rather than fails, and says in its message that
it is a convention rather than a measured threshold. Total exhaustion of
the substrate remains a hard violation.

Attaching a citation to that number would have been laundering a convention
into a measurement — the same call as declining Hou et al. (2020) for
`seir.sigma` in an earlier stage.

The "4–45 °C" and "pH 5–9" ranges were demoted from violations to warnings.
They were presented as universal and are not: Taq polymerase is assayed near
72 °C, pepsin near pH 2. Failing a run on them would reject correct science.

## 5. A cache that let non-peer-reviewed sources pass

`LiteratureVerifier` cached the **whole verdict** under
`ref.doi || ref.pubmedId || ref.title`. But `peerReviewed` is a property of
the *reference*, not of the DOI. So once any peer-reviewed reference with a
given DOI was verified, a different reference with the same DOI and
`peerReviewed: false` returned the cached `true` and never reached the
peer-review check.

The repository's own test file contains exactly that pair — the same DOI at
lines 152 and 180, one peer-reviewed and one not — and could not detect it,
because these tests had never been run.

Split: `registryCache` now caches only registry lookups ("does this
DOI/PMID resolve"), keyed by identifier. `peerReviewed` is evaluated on
every call.

## 6. Two of my own tests were proved worthless by mutation testing

- The order-independent regression test for §5 **passed against the bug**.
  With CrossRef unreachable, `verifyDOI` returns false, `verifyReference`
  bails at check 1, and the assertion "non-peer-reviewed is rejected"
  succeeds because the DOI failed — not because the peer-review check
  worked. Fixed by adding `primeRegistryCache`, so the test seeds the DOI
  as resolving and the peer-review branch is what actually decides.

- The first mutation I wrote to test it was *also* wrong: it restored the
  cache writes but not the early-return that **read** the cache, which was
  the actual mechanism. Corrected, the mutation fails the test
  (`Expected: false, Received: true`) and reverting restores green.

Both were caught only because the mutation was run rather than assumed.

## 7. Other fixes in this batch

- **`logger.ts` lost error contents.** A concurrent rewrite serialised
  bindings with `JSON.stringify`, under which `Error.message` and `.stack`
  are non-enumerable — so `logger.error({ jobId, error }, 'Simulation
  error')` emitted `"error":{}`, a failure report with the failure removed.
  Errors are now unwrapped explicitly (including `cause`), circular
  structures cannot throw, and output moved from `console.log` to stderr so
  the advertised CLI's stdout stays machine-readable.

- **Colliding reproduction keys.** `sha256(inputHash:outputHash:Date.now())`
  has millisecond resolution, so two records with identical inputs and
  outputs created in the same millisecond produced the same "unique" key —
  visible intermittently under `jest --runInBand`. A process-local
  monotonic counter was added.

- **Test pollution.** `registryCache` is static module state that leaked
  across test files when jest shared a worker; `--runInBand` exposed an
  order-dependent failure the default parallel run hid. A `beforeEach`
  reset was added. Parallel and serial runs now agree.

## 8. Verification

- `tsc --noEmit -p .`: **0 errors.**
- Root tree: **78 of 79 passing**, stable across three consecutive
  `--runInBand` runs. Was 22 failing of 59 at the start of Part 7.
- The single remaining failure, `ScientificValidationPipeline › should
  complete all 4 layers`, is the blocked network: CrossRef is unreachable
  from the review sandbox (`fetch failed`, verified directly), so
  `verifyDOI` correctly returns false and validation correctly refuses to
  proceed. It should pass where CrossRef is reachable.
- Engine suite unaffected (the 9 `test_popgen_resolver` failures are
  `stdpopsim` not being installable here, and predate this work).

## 9. Still open

- **The tree remains unwired.** `literatureService.ts` is still an in-memory
  `Map`, and `runSimulation` is still a Michaelis-Menten toy with
  `parameters.km?.value || 5.0` fallbacks and no connection to the
  Tellurium engine. Everything above makes the tree correct and honest
  about what it does not know; none of it makes the tree *real*. The
  wire-or-delete decision from Part 6 is still open and is now the main
  thing.
- `lg_probe.ts` and `av_probe.ts` must be deleted (`rm lg_probe.ts
  av_probe.ts`) — scratch files that the review sandbox would not let me
  remove.
- Six build-tool configs still type-checked by nothing (Part 7 §5).
- `landing/src/components/VerificationConsole.tsx` still needs `react` and
  `@types/react` before it can be type-checked.
