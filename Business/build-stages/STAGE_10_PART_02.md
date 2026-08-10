# Stage 10, Part 2 — the literature claim was unfalsifiable. Now it isn't.

Stage: 10 · Part: 2 · 2026-08-09

## 0. The thing that was wrong

Terrium's central claim is that nothing is hardcoded and every number is
backed by literature. Until this part, **that claim could not be checked**,
and it was not true.

Three things were simultaneously the case:

- `RESOLVABLE_FIELDS` resolves five parameters live from primary sources.
  Real, cited, independently verified. That part was never in doubt.
- `DOMAIN_DEFAULTS` held **64 hardcoded numbers** across 14 domains that
  nothing checked against anything.
- `domain-literature.ts` attached a `defaultJustification` to those numbers
  reading "per Lehninger (2008)", "per Kermack & McKendrick (1927)", "per
  Gillespie (1976)" — attributions no test, guard, or human had verified.

An unfalsifiable claim of rigour is worth less than an honest admission of
its absence. Worse: it is the exact failure this project exists to refuse
in other people's science code.

## 1. The eight false attributions

Each of these named a real paper as the source of numbers that paper does
not contain. The papers are the source of the **models**; they say nothing
about these **values**.

| domain | claimed | reality |
|---|---|---|
| mm | "Km=2mM, Vmax=5 per Lehninger (2008)" | Lehninger derives the model, not these values |
| mm_competitive_inhibition | "per Copeland (2013)" | same |
| sir | "β=0.3, γ=0.1 per Kermack & McKendrick (1927)" | the 1927 paper derives the SIR model, not these rates |
| seir | "σ=0.2 per Anderson & May (1991)" | no source in this system reports a latent period at all |
| pcr | "n0=100, efficiency=0.95 per Mullis et al. (1986)" | Mullis describes the method, not these values |
| lotka_volterra | "α=1.1, β=0.4, γ=0.1, δ=0.4 per Lotka (1925)" | Lotka derives the model, not these four numbers |
| gillespie_ssa | "a0=100, k=0.1 per Gillespie (1976)" | **both numbers also wrong**: actual defaults are 1000 and 0.5 |
| gillespie_ssa_bimolecular | "a0=50, b0=50, k=0.01 per Gillespie (1976)" | **all three wrong**: actual are 100, 100, 0.005 |
| two_locus_wright_fisher | "recombination_rate=0.01, population_size=10000 per Wright (1931)" | **both wrong**: actual are 0.1 and 100 — off by 10x and 100x |

Four of the nine did not merely mis-attribute; they stated numbers that did
not match `DOMAIN_DEFAULTS` at all. That is what happens when a
justification is prose nothing checks: it drifts from the code silently and
keeps sounding authoritative.

All rewritten to state plainly that the paper is the source of the *model*,
that the value is an unverified teaching default, and where the real
resolution path is when one exists.

## 2. The mechanism: `scripts/check_literature_inventory.py` (guard 14)

Prose corrections rot. The guard does not.

Every number in `DOMAIN_DEFAULTS` must be declared in
`docs/literature-inventory.toml` as exactly one of:

- **RESOLVED** — fetched live per query from a primary source, citation
  attached to the value.
- **VERIFIED** — a constant checked against a named source, check automated.
- **UNVERIFIED** — a teaching default. Permitted, but it must *say so*.
- **NOT_SCIENTIFIC** — grid resolution, integration window. No claim made.

A number in the code but absent from the inventory is a hard build failure.
`RESOLVED` and `VERIFIED` must name a source — a verification nobody can
re-check is not a verification. The guard also fails when a declared value
drifts from the code, in either direction.

Crucially, it does **not** demand a citation for everything. `points=51` is
a plotting resolution; demanding a source would manufacture a fake one,
which is worse than none. The demand is *declaration*, not fabrication.

Mutation-tested both directions:

```
added `secret_fudge: 0.7` to DOMAIN_DEFAULTS
  -> mm.secret_fudge = 0.7 is hardcoded ... but absent from the inventory

changed km 2 -> 9.9 in code only
  -> mm.km is 9.9 in the code but the inventory records 2.
     The inventory has drifted from reality — one of them is a lie.
```

## 3. The honest number

Printed on every build:

```
OK: all 64 DOMAIN_DEFAULTS numbers declare their provenance.
    RESOLVED (live from a primary source) : 9
    VERIFIED (checked against a source)   : 1
    UNVERIFIED (teaching default)         : 30
    NOT_SCIENTIFIC (grid/window)          : 24

    Of the 40 numbers that carry a scientific claim, 10 (25%) trace to a source.
    30 are teaching defaults and must never be described as literature-backed.
```

**25%.** Not 100%. That is the truth, and the build now says it out loud
every time rather than letting a README imply otherwise.

What makes this defensible rather than embarrassing: the 30 unverified
numbers are, with few exceptions, quantities no source *can* supply —
`s0` (initial substrate concentration) is a property of an experiment the
user is designing; `i0` is a scenario choice; `population_size=100` is
chosen so drift is visible in a classroom-length run. The honest move is to
label them, not to attach a citation that would be a lie.

And the ones that *matter* — the ones that determine the physics — are the
resolved nine: `km`, `ki` (BRENDA), `mutation_rate` (stdpopsim),
`beta`/`gamma` (ADR 0017 registry). The hard rule blocks a simulation from
running on any of the unverified defaults.

## 4. Where the remaining gap actually is

Now visible, which is the point:

1. **`seir.sigma`** is the one unverified value with a real scientific
   claim attached and no path to resolution. ADR 0017's registry pairs R0
   with a serial interval only; nothing reports a latent period. Closing it
   means finding a source that reports both for the same disease with
   compatible methodology — the same bar ADR 0017 set.
2. **`molecular_dynamics.density = 0.85`** is "conventional near the LJ
   triple point", which is true and still not a citation.
3. **`pcr.efficiency = 0.95`** sits in the conventionally-reported band
   without coming from a measurement.

Each is a candidate for promotion from UNVERIFIED to RESOLVED, and each
needs a real source rather than a plausible-sounding one.

## 5. Scope note

The inventory currently covers `DOMAIN_DEFAULTS`. The plausibility bounds
in `core/data_structures.py` are separately documented and partly
verified (Bar-Even 2011 for kcat, checked against PubMed PMID 21506553;
`LV_PLAUSIBLE_MIN/MAX_RATE` explicitly self-declared as not
literature-anchored). Bringing those under the same guard is the obvious
next extension.

## 6. Verification

- 14 guards pass (`verify_build.py --quick`), including the new one.
- `tsc --noEmit` clean; 30 test files, 413 tests passing.
- Mutation-tested in both directions (§2).
