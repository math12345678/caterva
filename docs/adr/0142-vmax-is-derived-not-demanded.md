# ADR 0142: Vmax is derived, not demanded — and a third kind of number

**Status:** Accepted, implemented

**Date:** 2026-08-20

**Context:** `scripts/report_lab.py`, `Tests/lab_report.py`,
`src/cli/scientificCLI.ts`

**Finishes:** ADR 0141's "Not done here", which named this as the largest
remaining barrier on this path

**Relates to:** ADR 0012 and ADR 0013 (the bridge and why [E]0 is a caller
input), ADR 0019 (kcat resolution, wired into `simulate` only), ADR 0116 (a
suggestion must not discard a flag the user typed)

## What was wrong

`report` required `--vmax`.

Vmax is a property of the student's **tube** — how much enzyme they pipetted
— not of the enzyme. No database reports it, and no student in a teaching
lab can look it up. It is the one required input they genuinely cannot
produce.

BRENDA reports kcat. `Vmax = kcat x [E]0` has been the documented bridge
since ADR 0012, and `simulate --resolve` has computed it since ADR 0019. So
the one command built *for* teaching labs was demanding a number it could
have derived, from a citation it could already fetch.

This is the fourth instance in a row of the same shape (ADR 0136, 0139,
0141): **`report` assembled from parts that each worked, with wiring written
fresh at the seam.**

## Decision

### A derived value is its own origin

This is the part that is not plumbing. The report had two origins:
`literature` (a value with a citation) and `yours` (a value the student
chose). A bridged Vmax is neither, and calling it either is a lie in a
specific direction:

| calling it | what it claims that is false |
|---|---|
| `literature` | that BRENDA reports a Vmax for this assay. It reports a kcat; the Vmax depends on a number the student picked |
| `yours` | discards the citation for the kcat, which is the entire reason the value is defensible |

So `DerivedValue` carries **both halves**, and the row shows both:

```
| vmax | 0.1707 mM/s | **derived** | Vmax = kcat x [E]0: kcat 170.7 1/s
  (BRENDA ref 741355), and [E]0 0.001 mM, which is yours |
```

A reader can check the cited half against the paper and see at a glance that
the other half was chosen. The relation is stated rather than implied,
because a reader who cannot see the operation cannot check the number.

`is_defensible` now counts three origins. A third kind that read as
"unaccounted for" would have made every derived report indefensible.

### Nothing about the bridge is reimplemented

The arithmetic, the unit convention (kcat s⁻¹ x [E]0 mM → Vmax mM/s) and the
validation all live in `caterva.core.validation.vmax_from_kcat`, which also
flags the `[E]0 << Km` assumption the Michaelis-Menten rate law rests on.
Multiplying two floats in `report_lab.py` would have been three lines and a
second definition of what the bridge means.

A **rejected** bridge returns no value at all. A zero [E]0 gives Vmax = 0, a
model that provably cannot turn over; emitting it anyway would put an
unrunnable number in the table with a real citation beside it, which is worse
than refusing because it looks sourced.

### A supplied Vmax is never overruled

Deriving only when Vmax is genuinely absent. A flag the student typed is a
decision, and replacing it with a computed number they cannot see is ADR
0116's defect in a new place. When `--enzyme-conc` is given *and* a Vmax was
supplied, the report says the [E]0 was not used rather than ignoring the flag
in silence.

## One page per run, because Jeske asked

Found while wiring this. `resolve_kinetic_value` fetches BRENDA inside
itself, and km, ki and kcat are separate **tables on one page** — so a
two-parameter report already fetched the same page twice, and adding the
kcat lookup would have made it three.

Lisa Jeske (BRENDA/DSMZ) asked directly that tools be gentle with their
servers, and this repository already refuses to auto-download a bulk corpus
for that reason. Re-requesting a page Caterva is still holding is the same
discourtesy in miniature, once per parameter.

`one_page_per_run` fetches each EC page once. **Scoped to a single run
deliberately** — a cache outliving the process would make a report
reproducible against a page nobody can see any more, which is a provenance
problem dressed as an optimisation (ADR 0016).

The test asserts a **count**, not the existence of a cache. A cache that is
built and never consulted passes every test that checks for its presence.

## Consequences

- 13 tests: six on the bridge as a unit, seven through the whole command.
- Five mutations, each asserted to have applied before measuring:

  | mutation | result |
  |---|---|
  | render a derived value as `literature` | 2 failed |
  | drop the chosen half from the row | 1 failed |
  | overrule a supplied vmax with a derived one | 1 failed |
  | derive a vmax with no [E]0 (invent one) | 2 failed |
  | fetch the page per lookup again | 1 failed |

- The two row-level assertions read the `| vmax |` **row**, not the
  document. The prose below the table explains what "derived" means, so a
  document-wide `contains` check would have passed for free — ADR 0133's
  lesson, applied while writing rather than after.
- The fixtures are split per table, so the test concatenates the km and kcat
  fixtures to stand in for a real BRENDA page. Without that, a kcat lookup
  against the km fixture correctly finds nothing and the test measures the
  fixture rather than the bridge — which is what the first run did.

## Still not done

**No end-to-end run against live BRENDA or UniProt.** This sandbox has no
route to either; every command verified here stops at `403 Forbidden`, and
the fixtures are snapshots. `parse_brenda_km_html` has never been checked
against current live markup. That is the largest untested surface in the
project and no amount of local work closes it.

**The kcat is resolved for the first substrate in the request.** A report
asking for km on one substrate and ki on another bridges Vmax from the
first, which is right for the single-substrate case and unexamined for any
other. Recorded rather than guessed at.
