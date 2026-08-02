# Stage 5, Part 7 — Literature audit of the provenance contract

Stage: 5 (the provenance contract) · Part: 7 (audit) · 2026-08-01

## 0. Scope

Stage 5 closed at Part 6. Stages 6 and 7 have since landed on top of it
(Gillespie SSA, bimolecular SSA). This part is a retrospective audit of
Stage 5's provenance contract against the **published standards for the data
it handles** — which Parts 1–6 did not consult.

The check: `grep -i "STRENDA|FAIR|PROV-O|Wilkinson|Schomburg"` across all six
Stage 5 documents returns nothing. The contract was designed from first
principles. It is good work — locatable citations, a two-tier citation status,
deliberate narrowness — and it is missing a requirement that the field settled
years ago.

## 1. The standard Stage 5 did not consult

STRENDA (Standards for Reporting Enzymology Data), Beilstein-Institut,
registered in FAIRsharing, recommended to authors by more than 60
international biochemistry journals. Its requirement, verbatim:

> "The temperature, pH and pressure (if other than atmospheric) of the assay
> **must** always be included, even if previously published."
>
> — STRENDA Guidelines v1.4.0

Not a recommendation. Not "where available." *Must*, *always*, *even if
previously published*.

## 2. Why this is physics, not paperwork

Km is not a property of an enzyme. It is a property of an enzyme **measured
under conditions**, and it moves with pH and temperature. The same enzyme and
the same substrate give different Km values in different assays.

So a Km without its pH and temperature cannot be reproduced by another lab and
cannot be compared against another lab's figure. It is not a reusable
scientific quantity — it is a number with a citation attached.

That distinction is the whole product.

## 3. What Terrium was actually doing

Three facts, each verified against the code:

**The provenance record had no field for it.**
`ParameterProvenance` carried `origin`, `source`, `citation`, `organism`,
`citationStatus`, `note`. No pH. No temperature. No buffer. (The one `Buffer`
match in the resolver is Node's binary type.)

**The data was available and being discarded.** BRENDA — the source Terrium
resolves from — stores pH optimum, temperature optimum, and an
experimental-conditions commentary alongside every Km entry (Schomburg *et
al.*, *Nucleic Acids Research*). `Tests/brenda_client.py` never extracts any of
them; the only `assay` matches in that file are prose in docstrings.

**And the value was still labelled `verified`.** So Terrium presented as
independently checked a number that, by the standard governing its own source,
was incompletely reported.

## 4. The fix

**ADR 0010.** Assay conditions become part of provenance, and their absence
degrades the citation tier rather than being silently tolerated.

- `AssayConditions { ph?, temperatureC?, buffer? }` on `ParameterProvenance`.
- `strendaStatus: "complete" | "incomplete"`, set only on resolved kinetic
  constants.
- `STRENDA_GOVERNED_FIELDS = {km, vmax, kcat, ki}`. Only `km` has a lookup
  path today; the rest are listed so adding one cannot silently bypass the
  requirement. **The set states the rule, not the implementation.**
- **A resolved kinetic constant with incomplete conditions cannot hold
  `citationStatus: "verified"`.** It degrades to `flagged` with a note naming
  the missing field.
- `buildResolvedKineticProvenance()` applies the degradation in one place, so
  no call site can forget it. It degrades only — a cross-species match with
  perfect conditions is still cross-species.

`pressure` omitted deliberately: STRENDA requires it only when non-atmospheric,
and no Terrium path resolves such a measurement.

### Why degrade rather than reject

The value may be correct; what is missing is the ability to *check* it. That
is exactly Rule 2's impossible/implausible distinction carried from physics to
reporting completeness — the simulation still runs, the warning travels with
it, nothing is silently accepted. Rejecting would also hide the problem: a
student sees `flagged` and a reason, where a rejected value would simply be
absent.

## 5. Verification

25 assertions against the compiled module, all passing:

```
strendaStatusFor                     7/7   incl. pH 0 and 0 °C accepted
missingStrendaFields                 3/3
buildResolvedKineticProvenance       6/6   incl. verified -> flagged
validateParameterProvenance          7/7   incl. the core rule
STRENDA_GOVERNED_FIELDS              2/2
```

Two cases worth naming:

- **pH 0 and 0 °C are accepted.** Both are real values; a truthiness check
  would silently reject them. The implementation tests presence and
  finiteness. NaN and Infinity are rejected.
- **A `strendaStatus` contradicting its own `assayConditions` is a hard
  violation**, not a warning. Self-inconsistent provenance is worse than
  absent provenance — the same reasoning that made a fabricated citation
  worse than no citation in Stage 4 Part 4.

`vitest` could not run in the review sandbox (rollup's native binary is
macOS-only there — the platform-override issue noted in Stage 4 Part 1's
audit). The suite in `src/__tests__/strenda.test.ts` is written and will run
in CI; the 25 assertions above were executed against the same compiled module
via node, and `tsc --strict` is clean.

## 6. Honest consequence

**Every currently-resolved Km degrades to `flagged`** until the BRENDA client
extracts assay conditions.

That is the correct state, not a regression. Terrium does not presently
capture pH or temperature, so it cannot honestly claim those values are
verified. The situation before this change was identical — it was just
labelled `verified`.

## 7. Carried forward

1. ~~**Extract pH and temperature in `Tests/brenda_client.py`** from the
   commentary field.~~ **Closed 2026-08-02.** See §10.
2. ~~**A golden tuple with real assay conditions.**~~ **Closed 2026-08-02.**
   See §11.
3. **`vmax` and `kcat`** are named in `STRENDA_GOVERNED_FIELDS` with no lookup
   path. When one is added, the requirement applies automatically.

## 8. One unrelated defect found

**ADR 0009 existed as a file but was absent from `docs/adr/README.md`.** Same
class as the duplicate ADR 0007 found in Stage 4 Part 1 — an ADR invisible to
anyone reading the index while still in the tree. Both 0009 and 0010 are now
indexed.

## 9. References

- **STRENDA Guidelines**, v1.4.0, Beilstein-Institut.
  <https://www.beilstein-strenda-db.org/strenda/public/guidelines.xhtml>
- **Wilkinson, M. D. *et al.* (2016).** The FAIR Guiding Principles for
  scientific data management and stewardship. *Scientific Data* **3**, 160018.
  DOI 10.1038/sdata.2016.18. Principle R1.2: detailed provenance.
- **Schomburg, I. *et al.*** BRENDA, the enzyme database. *Nucleic Acids
  Research* — kinetic entries carry pH optimum, temperature optimum and an
  experimental-conditions commentary.

## 10. Addendum (2026-08-02) — the enforcement shipped ahead of its producer

Part 7 landed the STRENDA rule in `validateParameterProvenance` and did not
update the one call site required to satisfy it. `queryResolver.ts` kept
hand-building the resolved-Km provenance object, so it emitted no
`strendaStatus`, and `resolveQuery` throws on any violation.

**Every Km resolution returned HTTP 500.** Sixteen vitest failures: eleven
integration (Targets B, C, E, F, G, H, I, Mutation 5, the MM route) and five
unit expectations whose fixtures predated the rule.

§6 above called the consequence "every currently-resolved Km degrades to
`flagged`." That was wrong in a specific and instructive way: it described
what the *contract* said while the *system* did something worse. A validation
rule and the producer that must satisfy it are one change, not two, and the
half that was written first was the half that could not be observed without
running the suite. This is the Stage 4 amendment — *a guard is not delivered
until something runs it unasked* — recurring in the opposite direction: the
guard ran, and nothing had been taught to satisfy it.

### What was built to close it

The extraction now reaches the API. The chain, each link previously absent:

| Layer | Change |
|---|---|
| `Tests/assay_conditions.py` | Parses the BRENDA commentary (already present) |
| `Tests/brenda_client.py` | Populates `assay_*` on `BRENDAKmEntry` |
| `Tests/fallback_logic.py` | **New** — `KineticResult` carries the fields; both exact and cross-species sites populate them |
| `science_agent_runner.py` | **New** — emits `assayConditions` across the JSON boundary |
| `scienceAgent.ts` | **New** — types the field |
| `queryResolver.ts` | **New** — both Km sites call `buildResolvedKineticProvenance()` |

`toAssayConditions()` drops JSON `null` rather than passing it through: the
runner uses null for "not reported" and `AssayConditions` uses absence for the
same thing, so a surviving null would be a present-but-empty field that
`strendaStatusFor` would have to interpret.

### Verification

- **182 Python tests pass** (up from 176). Six new: three asserting conditions
  survive `resolve_kinetic_value` on both the exact and cross-species paths,
  three pinning the runner's JSON contract.
- **Mutation-tested.** Deleting `assay_ph=best.assay_ph` from the exact-match
  site fails `test_ph_reaches_the_result_and_absent_temperature_is_reported`
  with `assert None == 8.0`. The test was confirmed to catch its own break
  rather than assumed to.
- **`test_runner_contract.py` caught the payload change unprompted** — a
  strict `==` on the runner's output shape, which is precisely why it is
  written that way. It was updated to assert the new key, not loosened.
- **`tsc --strict` clean**; seven assertions run against the compiled
  provenance module confirm the producer's output validates and that the five
  previously-failing unit shapes now yield exactly their intended violations.

### Measured outcome on real data

The LDH fixture's `(S)-lactate` rows read *"pH 8.0, temperature not specified
in the publication."* Km 10.73 mM now arrives with `ph: 8.0`,
`temperatureC: null`, `unreported: ["temperature"]` — and therefore
`citationStatus: "flagged"`, `strendaStatus: "incomplete"`, with a note naming
the missing field.

That is the correct result. The publication did not report its assay
temperature, so Terrium cannot claim the value is verified. It says so, and
says why.

## 11. The golden tuple, and what the fixture audit found

Two failures survived the §10 fix. Both traced to `GOLDEN_LDH_RESULT` — the
mock the whole provenance suite treats as ground truth — carrying no assay
conditions. The obvious repair was to add some. **That would have been
fabrication**, and checking first is what prevented it.

### Every row in the golden LDH record is STRENDA-incomplete

The Km 10.73 mM tuple — Terrium's canonical "exact match → verified" example —
is a real captured BRENDA row reading *"pH 8.0, temperature not specified in
the publication."* So is every other ref-740253 row. The two pyruvate rows
carry no commentary at all.

Adding a temperature to make the test pass would have invented a number the
source explicitly states was never reported, and written it into the one
fixture the suite trusts most. The Stage 4 fabricated-citation failure in a
new costume.

### The consequence: `verified` means something stricter now

Target H asserted *exact BRENDA match → `verified`*. Under ADR 0010 that is no
longer sound. Exactness of the organism match and completeness of the
reporting are independent axes, and the golden LDH row occupies a cell that
was previously assumed empty: **an exact match that is not verifiable.**

The test was split rather than relaxed:

- **`exact match + incomplete conditions → 'flagged'`** — asserts `organism`
  is still `Homo sapiens`, so the degradation is provably driven by the
  missing conditions and not by a cross-species fallback.
- **`exact match + complete conditions → 'verified'`** — the positive
  control. Without it, Target H would pass against a resolver that never
  returns `verified` at all.

### The golden tuple (carried item 2, closed)

A fixture sweep found 5 STRENDA-complete rows in 14. The LDH candidate
(Km 0.045, ref 998877, pH 7.4, 37 °C) was **rejected**: the fixture header
discloses that row as a synthetic structural edge case for testing
substrate-exclusion, not live-captured data. It would have looked perfect in
a diff.

The tuple used is documented as live-captured:

> **AChE** (EC 3.1.1.7) · *Homo sapiens* · Acetylcholine · **Km 0.0714 mM**
> *"in 0.1 M MOPS buffer (pH 7.4), at 37 °C"* · BRENDA ref 713996

Exact organism match, STRENDA-complete, real. It resolves as `verified` /
`complete` with no note.

### Target I's assertion was wrong, not its intent

Target I asserted a resolved km carries `note === undefined`. ADR 0010
deliberately attaches a note naming the missing field, so that assertion now
forbids the degradation message from reaching the student. Its actual intent —
the resolved entry must not inherit the *narrowness* note meant for
unresolvable parameters — was preserved by asserting the note is **not** the
narrowness string while **is** the STRENDA one. A paired test asserts a
complete record carries no note at all, so the note is provably a consequence
of incompleteness rather than boilerplate on every resolved entry.

### Verification

Eleven assertions against the compiled module, including the one that keeps
the rule from over-reaching: **complete conditions do not promote a
cross-species match to `verified`.** `buildResolvedKineticProvenance`
degrades only. `tsc --strict` clean; 182 Python tests pass; all five repo
guards exit 0.
