# terium

Part of [**Terrium**](https://github.com/Terrium-sim/main) — scientific computing for teaching labs.

The simulation engine. 64 files, 38 test modules,
1,014 tests.

Fifteen domains: Michaelis-Menten (plain and competitively inhibited),
SIR/SEIR epidemiology, PCR amplification, Monte Carlo, Wright-Fisher
population genetics (single- and two-locus), Lennard-Jones molecular
dynamics, Gillespie SSA (first-order decay, bimolecular, replicate
ensemble), and three ODE oscillators — Lotka-Volterra, the Tyson (1991)
cdc2-cyclin cell cycle, and the Elowitz & Leibler (2000) repressilator.

```bash
python -m Terium.cli --help
python -m Terium.cli wf --population-size 100 --generations 200 --seed 42
```

## The name

This was `Tellurium/` until 2026-08-11. The upstream
[Tellurium](https://tellurium.analogmachine.org/) project is **unrelated to
this code** — `requirements.txt` has always said *"do NOT `pip install
tellurium`"* (ADR 0001), and this engine imports it nowhere, calling
`libroadrunner` and `antimony` directly. The old name implied a
relationship that does not exist.

Upstream Tellurium is Apache-2.0, so use was never a licensing problem. The
rename is about not claiming someone else's name.

## Rules this engine is held to

Every numerical claim is checked against an independent source of truth — a
closed-form solution, a known-correct solver, or a physical invariant.
Physical impossibility is rejected (`ok=False`); implausible-but-real is
flagged (`ok=True, flagged=True`), never silently accepted or silently
rejected.

See [`documents`](https://github.com/Terrium-sim/documents) for the constitution and the 23 ADRs.

---

This repository is a submodule of [`Terrium-sim/main`](https://github.com/Terrium-sim/main). Clone the whole system with:

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
```
