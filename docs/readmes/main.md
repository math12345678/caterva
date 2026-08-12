# Terrium

Scientific computing for teaching labs. Students ask a question in plain
language; Terrium resolves the real parameters from the literature, runs the
simulation, and shows its work — every number traceable to a citation that
has been independently checked.

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
cd main
make setup     # creates .venv, installs everything
make check     # verifies the stack genuinely works
make test      # 1,291 tests (1,014 engine + 277 literature)
```

`make check` is not a version-string check. It builds a real
Michaelis-Menten model, translates it to SBML, integrates it, and compares
the result to the exact closed-form solution. If it passes, the numerics are
trustworthy.

## What it does that other tools don't

```
Parameters and where they came from
  s0    10 mM      user
  e0    0.001 mM   user
  km    0.14 mM    brenda_exact  BRENDA ref 12345
  vmax  0.25 mM/s  brenda_cross_species → kcat x [E]0  BRENDA ref 649716
        ⚠ measured in Oryctolagus cuniculus, not the organism requested

  2 of 4 parameter(s) carry a literature citation.
  The rest are user inputs or experimental conditions, which is fine —
  but they are not literature-backed and must not be reported as such.
```

Three things are load-bearing there:

**It refuses to invent.** A parameter it cannot source stops the run. No
`km = 5.2` fallback, no plausible-looking default. `s0` and `end` are
*experimental conditions* — chosen by whoever runs the experiment — so they
are supplied, never resolved. `km` and `kcat` are *measurements*, so they
need a citation. A citation is required for what someone measured and
meaningless for what the experimenter chose.

**It distinguishes three outcomes, not two.** Exit `0` found, `2` the
literature genuinely has nothing, `1` the lookup could not be performed.
Most tools collapse the last two, which teaches you to read an absence of
evidence as evidence of absence.

**It says when a match is not the thing you asked for.** A rabbit Km is real
and citable, and it is not a human measurement. The warning is not
suppressible.

## This is an umbrella repository

The code lives in submodules, so no file exists in two places and nothing
can drift out of sync.

| repository | what |
|---|---|
| [`terium`](https://github.com/Terrium-sim/terium) | the simulation engine — 15 domains, 1,014 tests |
| [`tests`](https://github.com/Terrium-sim/tests) | the literature layer — BRENDA/PubMed resolvers, 277 tests |
| [`backend-main`](https://github.com/Terrium-sim/backend-main) | TypeScript library, CLI, web server |
| [`frontend-main`](https://github.com/Terrium-sim/frontend-main) | the dashboard UI |
| [`wiring-main`](https://github.com/Terrium-sim/wiring-main) | the 21 guards, CI, build config |
| [`science-agent-pipeline-replit`](https://github.com/Terrium-sim/science-agent-pipeline-replit) | the Express API service |
| [`documents`](https://github.com/Terrium-sim/documents) | constitution, 23 ADRs, API reference |
| [`business`](https://github.com/Terrium-sim/business) | strategy, and the build-stage record |
| [`terrium-site`](https://github.com/Terrium-sim/terrium-site) · [`landing`](https://github.com/Terrium-sim/landing) · [`mule`](https://github.com/Terrium-sim/mule) | the three web front ends |
| [`advanced-analysis`](https://github.com/Terrium-sim/advanced-analysis) · [`benchmark-results`](https://github.com/Terrium-sim/benchmark-results) | figures and measurements |
| [`archive`](https://github.com/Terrium-sim/archive) · [`miscellaneous`](https://github.com/Terrium-sim/miscellaneous) · [`worktrees`](https://github.com/Terrium-sim/worktrees) | superseded reports, loose files, scratch space |

Full reasoning: [`docs/REPO_MAP.md`](docs/REPO_MAP.md).

## How it keeps itself honest

21 guards run on every build. They exist because the alternative was tried
and failed — most were written *after* something claimed to be verified and
was not.

```bash
python scripts/verify_build.py --quick
```

The rule they all serve: **a check that cannot fail is worse than no check,
because it is trusted.** Several were themselves found reporting green on
work they had not done. One printed *"every collected test ran"* while 275
tests failed to collect. One promised regression detection in its docstring
and had an empty loop body. One reported 242 of 294 documented endpoints as
fake — it had been parsing half the route table, and the real figure was 19.

Each is written up in
[`business/build-stages/`](https://github.com/Terrium-sim/business), mistake
included. Those records are never rewritten to match the present.

## The engine's name

`terium`, not `tellurium`. The upstream
[Tellurium](https://tellurium.analogmachine.org/) project is unrelated to
this code — Terrium calls `libroadrunner` and `antimony` directly and has
never depended on the umbrella package (ADR 0001). The old directory name
implied a relationship that does not exist.

## Requirements

**Python 3.10–3.13**, a hard constraint. `libroadrunner` 2.8.0 and `numpy`
2.2.6 publish wheels through cp313 and keep the cp310 floor; the 2.9.x
libroadrunner line drops cp310. See ADR 0014.

Do **not** `pip install tellurium` — the umbrella package pulls in
`python-libcombine` and `python-libnuml`, neither of which Terrium uses, and
on any platform without prebuilt wheels the install dies at the cmake step.
`scripts/check_forbidden_packages.py` fails the build if it reaches a
manifest, or if a document tells you to install it.

## Licence

See [LICENSE](LICENSE). Citation metadata in
[CITATION.cff](CITATION.cff).
