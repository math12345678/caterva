# tests

Part of [**Terrium**](https://github.com/Terrium-sim/main) — scientific computing for teaching labs.

The literature layer and its 90 files — 277 tests.

This is what makes Terrium more than a solver: the resolvers that fetch real
kinetic constants from BRENDA and PubMed, the citation verifier, and the
tests that keep them honest.

```bash
python -m pytest . -q
```

## What lives here

| module | does |
|---|---|
| `brenda_client.py` | BRENDA KM/Ki/kcat tables, with the reference id that re-finds each value |
| `enzyme_lookup.py` | UniProt accession and taxon resolution |
| `epidemiology_resolver.py` | R0 and serial interval per disease, from a matched-methodology source |
| `popgen_resolver.py` | mutation rates via stdpopsim |
| `fallback_logic.py` | exact match → cross-species → not found, never a guess |

## The rule that shapes all of it

A value that cannot be sourced is **not** replaced with a plausible one. The
resolver returns "not found", the caller degrades honestly, and the run
stops rather than inventing a number.

`test_epidemiology_resolver.py::TestNoLatentPeriodIsOffered` is the clearest
example: SEIR's σ needs a *latent* period, the literature overwhelmingly
publishes *incubation* periods, and the test exists to stop anyone quietly
substituting one for the other. The two differ in a direction that would
make epidemics look slower than they are.

---

This repository is a submodule of [`Terrium-sim/main`](https://github.com/Terrium-sim/main). Clone the whole system with:

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
```
