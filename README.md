# Terrium

> **Contributing, or just arrived? → [START_HERE.md](START_HERE.md)**
>
> One page: what this is, how to get it running, where things live, and a
> real first task. Everything else is linked from there.

Scientific computing for teaching labs. Students ask a question in plain
language; Terrium resolves the real parameters from the literature, runs the
simulation, and shows its work — every number traceable to a citation that has
been independently checked.

Fifteen simulation domains built so far: enzyme kinetics (plain and
competitively-inhibited Michaelis-Menten), SIR/SEIR epidemiological modeling,
PCR amplification, Monte Carlo simulation, population genetics
(Wright-Fisher, single- and two-locus), molecular dynamics (Lennard-Jones
cluster), Gillespie SSA stochastic chemical kinetics (first-order decay,
bimolecular association, and a multi-replicate ensemble view), and three
ODE oscillators: Lotka-Volterra predator-prey, the Tyson (1991) cdc2-cyclin
cell-cycle oscillator, and the Elowitz & Leibler (2000) repressilator.

> **Terrium is not Tellurium.**
>
> [Tellurium](https://tellurium.analogmachine.org/) is an established
> systems-biology environment from the Sauro lab at the University of
> Washington and collaborators including Lucian Smith and Matthias König.
> Terrium is an unaffiliated personal project. It is not a fork of
> Tellurium, not endorsed by its authors, and makes no claim to their work.
>
> Terrium is a *consumer* of that ecosystem: it runs on libRoadRunner and
> generates Antimony, both of which come from that group. The similar name
> is a mistake of mine and has already caused one researcher to reasonably
> read a cold email as a false claim of credit. Saying so here is cheaper
> than letting the next person work it out.

## Quick start

> **Not public.** The command below needs access: every `Terrium-sim`
> repository is private, and a plain `git ls-remote` on any of them prompts
> for a username. If you are reading this without a GitHub account that has
> been added, **line one is as far as you get** — that is a fact about the
> repository, not a mistake you made.
>
> `scripts/check_quickstart_clone_works.py` checks that no document promises
> a stranger anonymous access it does not have
> ([ADR 0143](docs/adr/0143-the-first-command-a-stranger-runs.md),
> [ADR 0179](docs/adr/0179-the-guard-that-could-not-go-green.md)). This
> notice is checked in the other direction too: publish the repositories and
> `check_availability_notice_matches_reality.py` fails until it is deleted,
> so it cannot outlive the thing it describes.

> **Private repository.** These repositories are private and are staying
> that way, so `gh repo clone` — which uses your GitHub credentials — is
> the command that works. A plain `git clone` URL stops at a username
> prompt. See [ADR 0179](docs/adr/0179-the-guard-that-could-not-go-green.md).

```bash
gh repo clone Terrium-sim/main
cd main
make setup     # creates .venv, installs everything (2-5 min)
make check     # verifies the stack genuinely works
make test      # runs all 2,350 tests (1,229 engine + 1121 literature)
```

### See what it produces, before anything else

```bash
make demo
```

Thirty seconds. No network, no BRENDA account, no Node. It reads a saved
BRENDA page committed under `Tests/fixtures/`, runs the real report builder
— the same one the CLI spawns — and prints the document a student would hand
in: the Km with its reference, the values you chose marked as yours, what
the published measurements disagree about, and a section listing what
Terrium refused to do and why.

Because it uses a saved page it demonstrates the pipeline rather than a live
lookup, and **the document says so itself** rather than leaving you to work
it out. Drop `--fixture` from the command it prints at the end to run the
same thing against BRENDA.

**`make test` takes six to eight minutes**, and prints nothing per-file
while it runs. That is normal. It is written here because the absence of a
figure is what makes a slow suite look like a broken one — the author of
this note spent a pass diagnosing a "hang" in
`Terium/tests/test_popgen_correctness.py` that was a 58-second file being
run inside a 175-second budget alongside others. It had never hung.

Measured on the reference container, `-p no:randomly`:

| suite | time |
|---|---|
| `Terium/tests` (engine) | ~3.5-4 min |
| `Tests/` (literature) | ~2.9 min |
| `test_popgen_correctness.py` alone | 58 s |

Test counts are deliberately absent from that table: they are stated once
above and checked by `check_documented_counts.py`, and a second copy here
would be a number that drifts with nothing watching it.

`make test-sim` and `make test-lit` run one half each if you only changed
one, and `pytest --durations=10` names the slowest tests when you want to
know where the time went.

`make setup` needs an interpreter in the supported window and downloads
about 120 MB of prebuilt wheels for the direct pins alone — libroadrunner is
50 MB of it. Every direct pin in `requirements.txt` publishes a wheel, so
nothing in that set compiles from source on x86_64 Linux, macOS or Windows.
Expect two to five minutes, and expect pip to print nothing at all while it
resolves.

**If anything above fails, run `make doctor`.** It reports every interpreter
it found and their versions, whether `.venv` exists and runs, which of the
seven required packages import and at what version against the pin, whether
`stdpopsim` is available, and whether Node is present for the TypeScript
guards — then lists what to do about each. It prints what it checked, not
just a verdict.

### The population-genetics resolver is opt-in

`stdpopsim` is **not** installed by `make setup`. It is GPL-3.0-or-later and
Terrium is Apache-2.0, so a default install would put copyleft code into the
environment of a project that declares a permissive licence — compatible in
one direction only, and not something a reader should have to derive by
comparing two licence files.

```bash
pip install -r requirements-popgen.txt     # adds GPL-3.0-or-later code
```

Nothing is violated either way: Terrium never bundles stdpopsim, and running
two separately-installed packages together is use rather than distribution.
Splitting it just means you can see what you have. See
[ADR 0061](docs/adr/0061-gpl-out-of-the-default-install.md) and NOTICE.

Without it, `test_popgen_resolver.py` skips its 19 tests and the resolver
returns `found=false` with a log saying stdpopsim is not installed — never a
substituted value. `make check` reports the skip as a warning so the gap is
visible; a silent skip would let the population-genetics literature path go
untested and still read as green.

The one platform where it reliably will not install is Linux on arm64:
`msprime`, stdpopsim's C-extension dependency, publishes wheels for
manylinux x86_64, macOS and Windows only, so pip builds it from source there
and needs `libgsl-dev` plus a compiler.

`make check` is not a version-string check. It builds a real Michaelis-Menten
model, translates it to SBML, integrates it, and compares the result to the
exact closed-form solution. If it passes, the numerics are trustworthy.

### Windows

The Makefile is POSIX shell — the interpreter resolver uses `command -v` and
shell functions, and every recipe calls `.venv/bin/...`, which a Windows
venv spells `.venv\Scripts\`. Use **WSL2** or the Dev Container below; both
are ordinary Linux from that point on, and both are what this project
actually exercises.

Nothing under the Makefile is Windows-specific — the steps are plain pip and
pytest — so the native equivalents are in CONTRIBUTING.md under "Windows".
They have not been run on a Windows machine by anyone here; if they fail,
that is a bug worth reporting rather than something you are doing wrong.

### Sandbox (Docker / Dev Containers)

If you'd rather not touch your local Python at all, there's a container that
gives you the same verified environment:

```bash
docker build -f .devcontainer/Dockerfile -t terrium-sandbox .
docker run -it --rm terrium-sandbox
# you're now in a shell where check_env.py has already passed
```

The `-f` matters. The Dockerfile at the repository root is a different
image: it builds the Node API server that `docker-compose.yml` runs and
contains no Python interpreter. The Python sandbox lives in
`.devcontainer/Dockerfile`.

This is also wired up as a [Dev Container](https://containers.dev/) — open
the repo in VS Code with the Dev Containers extension installed and it'll
offer to build and attach automatically. It adds Node 22 on top of the
Python image, because `scripts/verify_build.py --quick` type-checks
TypeScript and needs `npx`. Run `npm install` once inside it before using
that command; `node_modules` is not baked into the image.

## Using it

Terrium is a command-line tool. The point of it is the provenance: every
number it reports says where it came from, and anything it cannot source it
refuses to invent.

```bash
npx ts-node src/cli/scientificCLI.ts help
```

### Look up a measured parameter

```bash
scientific resolve "lactate dehydrogenase" \
  --substrate pyruvate --organism "Homo sapiens"
```

```
✓ KM = 2.5 mM

  System    lactate dehydrogenase / pyruvate
  Organism  Homo sapiens
  Source    brenda_exact
  Citation  BRENDA ref 740253
```

When the organism you asked for has no measurement, Terrium does **not**
quietly hand you another organism's:

```
✗ No KM measured in Homo sapiens for this system.

  BRENDA holds a KM for Oryctolagus cuniculus and Sus scrofa.
  Kinetic parameters are species-specific, so it was not substituted.
  Re-run with --allow-cross-species to use one, understanding that the
  resulting model is not a model of the organism you asked for.
```

That refusal is deliberate. It follows a recommendation from Lisa Jeske of
the BRENDA curation team: *"The simulation should rather abort or leave the
value empty if there is no exact organism match, instead of providing
incorrect data."* See [ADR 0024](docs/adr/0024-refusing-versus-defaulting-an-unsourced-parameter.md).

Opting in does not disable judgement. Candidates must still share a
taxonomic **class** with the organism you asked about, checked live against
NCBI Taxonomy — so a second mammal is offered and a *Plasmodium falciparum*
value for a mouse is not:

```
✗ Cross-species use was enabled, and no candidate passed the relatedness check.

  Plasmodium falciparum and Mus musculus diverge above the class level —
  their nearest shared ranked ancestor is the domain Eukaryota.

  Enabling cross-species data permits a value from a related organism;
  it does not permit one from any organism.
```

It resolves through BRENDA (exact match, then cross-species) and then
PubMed, and reports **three outcomes with three exit codes**:

| exit | meaning |
|---|---|
| 0 | found — a real measurement with its unit, organism and citation |
| 2 | the literature genuinely has nothing for this system |
| 1 | the lookup could not be performed at all |

Most tools collapse the last two. They are different facts, and a tool that
reports "no result" when it actually could not reach the registry teaches
you to read an absence of evidence as evidence of absence.

`--quantity km|ki|kcat` picks which measured parameter. `--json` for scripting.

Add `--allow-cross-species` to accept a value measured in a different but
sufficiently related organism when yours has none. Off by default, and
candidates must still pass an NCBI Taxonomy relatedness check.

### Run a simulation with everything sourced

```bash
scientific simulate mm --resolve \
  --enzyme "lactate dehydrogenase" --substrate pyruvate \
  --organism "Homo sapiens" --s0 10mM --enzyme-conc 0.001mM
```

```
Parameters and where they came from
  s0    10 mM      user
  e0    0.001 mM   user
  km    0.03 mM    brenda_exact  BRENDA ref 286469
  vmax  0.25 mM/s  brenda_cross_species → kcat x [E]0  BRENDA ref 741355
        ⚠ measured in Oryctolagus cuniculus, not the organism requested

  2 of 4 parameter(s) carry a literature citation.

Result
  initial    10.0000 mM
  final      7.5395 mM
  points     101
```

Anything it cannot source stops the run rather than being defaulted. Vmax is
not a BRENDA table — it is `kcat × [E]₀`, and BRENDA does not report an
enzyme concentration, so `--enzyme-conc` is required to bridge it.

**Write units onto the numbers.** `--km 5.2mM`, `--vmax 12.8uM/min`. A bare
number is accepted, but the assumed unit is reported — a Vmax in mM/s read
as μM/min is wrong by a factor of 60,000.

### Ask whether a shaky number matters

```bash
scientific simulate mm --resolve ... --sensitivity
```

```
Sensitivity  (±10% on each parameter)
  s0      13.2%   user
  vmax     3.3%   brenda_exact → kcat x [E]0
  km       0.1%   brenda_cross_species
```

Sensitivity on its own is ordinary. Paired with provenance it answers the
question you actually have: *my Km is a rabbit value — does that change my
conclusion?* Here it does not (0.1%), while the substrate concentration you
chose moves the answer 13.2%.

The report separates two different problems: a **weakly sourced
measurement** that is load-bearing means *measure it for your own system*;
a **load-bearing choice you made** means *state it precisely in your
methods*.

### Inhibition models

```bash
scientific simulate x --resolve --model noncompetitive \
  --enzyme ldh --substrate pyruvate --organism "Homo sapiens" \
  --s0 10mM --i0 0.1mM --enzyme-conc 0.001mM
```

`--model mm|competitive|noncompetitive|product`. Ki resolves from BRENDA's
Ki table with its own citation. Competitive inhibition uses the engine's
first-class domain; non-competitive and product inhibition are emitted as
SBML and run through the engine's `sbml` escape hatch — the same solver
either way, never a second simulator.

Supplying a Ki and running plain `mm` will prompt you: that combination
silently discards the inhibitor.

### Sweep a parameter

```bash
scientific sweep mm --parameter s0 --range 2:10:2 --km 0.5mM --vmax 0.1mM/s
```

```
      2  1.2393
      6  5.0829
     10  9.0499

  shape  ▁▃▄▆█
  trend  increasing  (slope 1.96e+0)
```

Points that break the pattern are flagged separately — usually where the
model stops behaving the way the rest of the range does.

### Past runs

```bash
scientific history
```

Every `--resolve` run is recorded with its full provenance to
`~/.terrium/history.json`, so a job id printed today still means something
tomorrow.

### Environment

| variable | effect |
|---|---|
| `TERRIUM_CONTACT_EMAIL` | identifies you to CrossRef's polite pool (better rate limits) |
| `TERRIUM_SKIP_DOI_VERIFICATION=1` | skip registry lookups offline. Results become **unverified**, never verified |
| `TERRIUM_ALLOW_UNVERIFIED_CITATIONS=1` | accept unverified citations. Cannot rescue a *rejected* one |
| `TERRIUM_HISTORY_FILE` | where run history is kept |
| `TERRIUM_PYTHON` | which interpreter runs the engine |

## Requirements

**Python 3.10–3.13.** This is a hard constraint, not a preference.
`libroadrunner` 2.8.0 and `numpy` 2.2.6 publish wheels through cp313 and keep
the cp310 floor (verified against PyPI). The 2.9.x libroadrunner line drops
cp310, so we stay on 2.8.0. See
[ADR 0014](docs/adr/0014-python-version-support.md).

## Do not `pip install tellurium`

The umbrella `tellurium` package pulls in `python-libcombine` and
`python-libnuml`, which exist to handle COMBINE archives and numerical markup.
Terrium uses neither. On any platform without prebuilt wheels for them, the
install dies at the cmake step.

Install the three packages that actually do the work instead — they are already
in `requirements.txt`:

| Package | Role |
|---|---|
| `libroadrunner` | ODE integration |
| `antimony` | human-readable model definition → SBML |
| `python-libsbml` | SBML validation |

## Domains

Fifteen simulation domains, two pipelines:

**Continuous (antimony → SBML → roadrunner):**
- **Michaelis-Menten** — irreversible single-substrate enzyme kinetics.
  Verified against the implicit closed form `Km·ln(S₀/S) + (S₀−S) = Vmax·t`.
- **Michaelis-Menten with competitive inhibition** — `v = Vmax·S / (Km·(1+I/Ki) + S)`.
  Verified against the apparent-Km closed form `Km_app = Km·(1 + I/Ki)`, and
  against plain Michaelis-Menten exactly at I=0.
- **SIR** — frequency-dependent epidemic model. Verified against conserved
  population, final-size relation, and peak condition `S = N/R₀`.
- **SEIR** — SIR with an explicit latent (exposed) compartment.
- **Lotka-Volterra** — predator-prey (Lotka 1925; Volterra 1926).
  `dP/dt = αP − βPV`, `dV/dt = γPV − δV`. Verified against the exact first
  integral `H = γP − δ·ln P + βV − α·ln V` (conserved to <1e-5 over the
  orbit), the coexistence fixed point `(δ/γ, α/β)`, the linearised
  small-oscillation period `2π/√(αδ)`, and scipy's `solve_ivp`. The default
  parameters give the classic ~10-year lynx-hare period (9.47).
- **Cell-cycle oscillator** — Tyson (1991) 2-variable cdc2-cyclin
  relaxation oscillator, DOI 10.1073/pnas.88.16.7328.
- **Repressilator** — Elowitz & Leibler (2000) synthetic three-gene ring.

**Discrete/stochastic (direct Python, no ODE solver):**
- **PCR amplification** — exact closed-form recurrence `N(c) = n₀ · (1+E)ᶜ`,
  optionally with a logistic plateau. Verified against copy-number conservation
  and plateau approach.
- **Monte Carlo π estimation** — uniform sampling in [-1,1]². Verified against
  the CLT error rate `1/√N`.
- **Molecular dynamics** — Lennard-Jones cluster, velocity Verlet. Verified
  against energy/momentum conservation, the O(Δt²) symplectic error rate,
  and published global-minimum energies (LJ13 = −44.326801 ε, Hoare & Pal
  1971). Not built through roadrunner — see ADR 0006.
- **Gillespie SSA** — exact stochastic simulation (ADR 0009) of a single
  first-order decay A → B. Verified against the closed form
  `E[a(t)] = a₀·e^(−kt)` (the count at time t is exactly Binomial(a₀, e^(−kt)))
  and a hand-verified seeded golden trajectory pinned through the API
  (`test_gillespie_ssa_golden.py`, `gillespieGolden.test.ts`).
- **Gillespie SSA bimolecular** — same Direct Method (Stage 7) for the
  association A + B → C with second-order propensity `k·a·b`, conserved
  `a+c = a₀`, `b+c = b₀`, halting at minor-species exhaustion. Verified
  against the ODE closed form
  `a(t) = (a₀−b₀)/(1 − (b₀/a₀)·e^(−k(a₀−b₀)t))` (equal counts:
  `a(t) = a₀/(1 + k·a₀·t)`) and a hand-verified seeded golden trajectory
  pinned through the API (`test_gillespie_ssa_bimolecular_golden.py`,
  `gillespieBimolecularGolden.test.ts`).
- **Gillespie SSA ensemble** (`simulate_gillespie_ssa_replicates`) — runs
  `n_replicates` independent SSA trajectories (first-order or bimolecular)
  and reports the sample mean trajectory on a fixed time grid alongside
  each replicate's final counts, for comparing stochastic spread against
  the deterministic reference. Replicate RNGs are derived deterministically
  from a single master seed (ADR 0005), so a fixed seed reproduces the
  whole ensemble bit-identically.
- **Wright-Fisher neutral drift** — binomial sampling of 2N allele copies each
  generation. Verified against the exact heterozygosity decay
  `Hₜ = H₀ · (1 − 1/(2N))ᵗ` and Kimura's fixation probability `P(fix) = p₀`.
  Also: selection with dominance (incl. over/underdominance), symmetric
  mutation, time-varying N, structured populations (island / stepping-stone
  migration with Fst), Kimura & Ohta expected fixation time, Ne estimation
  from heterozygosity decay, Wright's stationary distribution
  `Beta(4Nu, 4Nu)`, the island-model equilibrium Fst
  (`1/(1+4N(m+u))`), parameter sweeps (`wright_fisher_sweep`, CLI
  `sweep`), and an exact Markov-chain layer
  (`wright_fisher_transition_matrix`,
  `wright_fisher_fixation_probability`,
  `wright_fisher_expected_fixation_time`,
  `wright_fisher_expected_loss_time`,
  `wright_fisher_expected_absorption_time`,
  `wright_fisher_stationary_vector`) whose values cross-check
  the diffusion approximations -- and resolve Kimura's documented
  `dominance > 1` failure exactly. The three times obey
  `E[T] = E[T|fix]·P_fix + E[T|loss]·(1 − P_fix)` exactly, and
  `fixation_analysis()` reports the observed mean fixation, loss, and
  absorption times to compare against them; the exact stationary
  distribution (Perron-Frobenius eigenvector of the chain) matches
  both Wright's `Beta(4Nu, 4Nu)` density and long simulations within
  ~0.007 in central mass. The effective size of a time-varying-N
  trajectory is the harmonic mean of the census sizes
  (`effective_size_harmonic_mean`) -- the textbook bottleneck result,
  verified against the heterozygosity-decay estimator. Two-locus
  haploid simulation with recombination and symmetric mutation
  (`simulate_two_locus_wright_fisher`): linkage disequilibrium decays
  as `Dₜ = D₀·(1−r)ᵗ·(1−2u)²ᵗ·(1−1/N)ᵗ`, verified against simulation
  within ~3%, with D and r² reported per generation. Divergence after a
  split: `expected_fst_after_split` gives the exact Fst trajectory of
  two isolated daughter populations (matches simulation within 0.01),
  including its counterintuitive limit — Fst approaches the
  probability of *divergent* fixation `2p₀(1−p₀)`, not 1.

All discrete/stochastic domains share a common RNG convention
(`numpy.random.default_rng(seed)` with `seed: int | None = None`), formalised
in ADR 0005 (`docs/adr/0005-rng-convention.md`) and enforced automatically by
`scripts/check_rng_convention.py`.

## Layout

```
Terrium/
├── Terium/                  simulation engine (ODE + discrete/stochastic)
│   ├── terium_engine.py     public entry point (88 names)
│   └── tests/                1,229 tests
├── Tests/                      literature layer (BRENDA / KEGG / PubMed)
│   ├── brenda_client.py        BRENDA parser (Km, kcat, Ki tables)
│   ├── fallback_logic.py       kinetic-value resolver orchestrator
│   └── ...                   1121 tests
├── Science-Agent-Pipeline/     API server, database layer, landing page
│   ├── artifacts/api-server/   Express + TypeScript API
│   ├── lib/db/                 Drizzle ORM schema + migrations
│   └── lib/api-spec/           OpenAPI 3.1 spec
├── docs/                       ADRs, engineering constitution, API docs
│   └── adr/                    184 decision records (and counting)
├── Business/                   build stages, roadmap, fundraising
├── scripts/                    74 guard scripts + build verification
│   ├── verify_build.py         runs all guards + tests in one command
│   ├── check_guard_wiring.py   every guard must run somewhere, unasked
│   └── ...                     see scripts/README.md for the full list
└── Docw/                       original specs (Word documents)
```

## API server documentation

`Science-Agent-Pipeline/artifacts/api-server/` has its own docs, covering the
parts of the stack the ADRs and this README don't (day-to-day usage of the
running server, not the science behind it):

- [`API_USER_GUIDE.md`](Science-Agent-Pipeline/artifacts/api-server/API_USER_GUIDE.md)
  — natural-language query syntax, every domain's parameters and real
  current defaults, response shapes, error codes.
- [`INTEGRATION_EXAMPLES.md`](Science-Agent-Pipeline/artifacts/api-server/INTEGRATION_EXAMPLES.md)
  — working Python/JS client code, including SSE job-progress streaming.
- [`DEPLOYMENT_GUIDE.md`](Science-Agent-Pipeline/artifacts/api-server/DEPLOYMENT_GUIDE.md)
  and [`OPERATIONS_RUNBOOK.md`](Science-Agent-Pipeline/artifacts/api-server/OPERATIONS_RUNBOOK.md)
  — running and operating the server.
- [`SECURITY_HARDENING.md`](Science-Agent-Pipeline/artifacts/api-server/SECURITY_HARDENING.md)
  — current security posture and hardening options.
- [`TESTING_AND_CI_CD.md`](Science-Agent-Pipeline/artifacts/api-server/TESTING_AND_CI_CD.md)
  — the api-server's own vitest suite and the real `.github/workflows/tests.yml`
  pipeline.

These were first drafted ahead of the code they described and, on audit,
contained fabricated infrastructure (Kubernetes manifests, Prometheus/Grafana,
AWS Secrets Manager, invented test counts and coverage percentages) presented
as if already built. They've since been corrected against a live read of the
actual source: implemented behavior is described as implemented, and anything
without corresponding code — mostly in the deployment/ops/security docs — is
marked **"Proposed — not yet implemented"** rather than removed, so the
guidance isn't lost but also isn't mistaken for the current state of the
running server. Same discipline as the ADRs: a claim these docs make about the
API should be checkable against `Science-Agent-Pipeline/artifacts/api-server/src`,
not taken on faith.

## How the tests are built

The suites deliberately avoid checking the solver against itself. Numerical
claims are verified against one of:

- **Exact closed-form solutions** — the implicit MM solution
  `Km·ln(S₀/S) + (S₀−S) = Vmax·t`, the SIR conserved quantity, the final-size
  relation, and the peak condition `S = N/R₀`.
- **An independent integrator** — scipy's `solve_ivp`, which shares no code
  with roadrunner.
- **Physical invariants** — mass and population conservation, monotonicity,
  non-negativity — checked across the input space with Hypothesis.

The suite is mutation-tested: deliberate scientific errors are injected into
the engine (breaking the rate law, driving SEIR infection off the exposed
compartment instead of the infectious one, disabling validation, loosening
solver tolerances, dropping the diploid factor of 2 in Wright-Fisher's
binomial sampling) and confirmed caught, one at a time, as each domain is
built. Every mutation claimed in an implementation report is independently
reproduced by a reviewer before being trusted — see
`Business/build-stages/STAGE_01_PART_04.md` and `STAGE_02_PART_04.md` for
the worked examples, including two cases where the original claimed blast
radius was wrong and got corrected.

## Two gotchas worth knowing

**`gamma` is reserved.** Antimony treats `gamma` as the built-in gamma
function, so a parameter named `gamma` is a hard parse error. The recovery rate
is emitted as `gamma_rate`; the Python API still takes `gamma`, and generated
models carry a comment explaining the rename.

**Plausibility bounds are shared.** `KM_PLAUSIBLE_MIN_MM` and
`KM_PLAUSIBLE_MAX_MM` must stay identical between `brenda_client.py` and
`terium_engine.py`. They drifted once (1e3 vs 1e4), which meant a Km of
5000 mM was flagged by the literature layer and then silently accepted as
confirmed by the simulation layer. `Terium/tests/test_brenda_integration.py` now pins
them together.

## Common commands

```bash
make doctor      # diagnose a broken setup; reports everything it checked
make check       # verify the environment actually works (builds + integrates a real model)
make test        # run all 2,350 tests
make test-fast   # skip the slow property/robustness suites
make test-sim    # simulation engine only (1,229 tests)
make test-lit    # literature layer only (1121 tests)
python3 scripts/verify_build.py --quick  # all 74 guard scripts, incl. TypeScript compile
make clean       # remove caches
```