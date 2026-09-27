# Caterva Advanced Analysis System

> **Most of this document describes work that has not been built.**
>
> What is in this directory, in full:
>
> | path | status |
> |---|---|
> | `advanced_analysis/scripts/generate_figures.py` | **real** — drives the engine, writes the ten figures below |
> | `advanced_analysis/figures/*.png` | **real** — its output, 10 files |
> | `requirements.txt` | real, and installable since 2026-08-23 |
> | `README.md` | this file |
>
> Nothing else. The **eleven** paths named in *Directory Structure* below —
> `architecture/`, `performance/`, `provenance_visualization/`,
> `validation/` and every file inside them — **do not exist**, checked one
> by one. Three of the four components in *System Overview* are plans
> written in the present tense.
>
> Said here rather than discovered by `cd architecture`. The section
> headed *Figure Suite (working)* already carried the whole truth in one
> parenthesis; this notice makes it legible without having to notice which
> heading is qualified and which is not.
>
> The plan is kept rather than deleted — it is a real intent and deleting
> it loses that — but a plan in the present tense is a claim, and this
> project's rule is that a claim nobody can check should not read like a
> fact.

## System Overview

The Caterva Advanced Analysis System consists of four main components:

1. **Simulation Domain Architecture Graph** - Comprehensive visualization of all simulation domains
2. **Performance Analysis Dashboard** - Benchmarking and performance optimization tools
3. **Provenance Tracking Visualization** - Parameter lineage and literature integration tracking
4. **Simulation Validation System** - Golden dataset validation and theoretical invariant checking

## Installation

```bash
# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Figure Suite (working)

The figure generator in `advanced_analysis/scripts/generate_figures.py` produces 10 publication-quality
figures that run the real engine and overlay the closed-form/statistical reference
each domain is validated against:

```bash
# From the repo root, using the project venv (has libroadrunner + matplotlib):
.venv/bin/python advanced_analysis/scripts/generate_figures.py

# Outputs to advanced_analysis/figures/*.png (200 dpi)
```

| Figure | Contents |
|--------|----------|
| `01_michaelis_menten.png` | MM trajectory vs exact implicit solution, v-S curve with Km/Vmax annotations, normalized saturation curve (Km = 10.73 mM from BRENDA LDH/L-lactate, ref 740253) |
| `02_competitive_inhibition.png` | Inhibitor raises apparent Km (not Vmax) across I/Ki multiples (Km 10.73 mM ref 740253; Ki = 0.0014 mM, LDH/gossypol ref 711801) |
| `03_sir.png` | SIR compartments, R0 phase-plane peak at S=1/R0, N conservation |
| `04_seir.png` | SEIR compartments; incubation delays/flattens infectious peak vs SIR |
| `05_gillespie_ssa.png` | Single SSA trajectory vs a0·e⁻ᵏᵗ, 500-replicate ensemble mean ±2σ, endpoint CLT distribution |
| `06_wright_fisher.png` | 80 replicate drift trajectories, H decay vs (1-1/2N)ᵗ theory, selection vs closed form |
| `07_pcr.png` | Exponential closed form n0(1+e)ᶜ and logistic-plateau saturation |
| `08_monte_carlo.png` | π convergence with 2SE band; 1/√n error law |
| `09_molecular_dynamics.png` | NVE energy conservation drift, kinetic/potential exchange, momentum conservation |
| `10_benchmarks.png` | Wall time by domain × problem size (log), scaling ratios from `benchmark_results/benchmark_results.json` |

Each figure is simultaneously a visualization and a verification artifact: engine
output is drawn against the exact solution or theory envelope the codebase's
evidence engine checks in its test suite. Every figure also renders its
`modelCitations` and per-parameter provenance on the canvas (matching ADR 0008):
parameters resolved from literature carry their locatable citation (the
Michaelis–Menten and competitive-inhibition figures use the BRENDA golden-set
`K_m`/`K_i`, e.g. LDH/L-lactate `K_m = 10.73 mM`, ref 740253), while teaching
values are explicitly labeled `default` and never claim a citation.

## Usage

### 1. Simulation Domain Architecture Graph

```bash
# View the architecture diagram
# Open the Excalidraw JSON file at https://excalidraw.com
```

### 2. Performance Analysis Dashboard

```bash
# Run performance benchmarks
python performance/benchmark_all_domains.py

# Launch the Jupyter notebook for analysis
jupyter notebook performance/performance_analysis.ipynb
```

### 3. Provenance Tracking Visualization — NOT BUILT

There is no `provenance_visualization/` directory. This section previously
gave two commands for it:

    streamlit run provenance_visualization/scripts/dashboard.py
    python provenance_visualization/scripts/generate_report.py --model SIR

Neither script has ever existed. Anyone who followed them got a file-not-found
error and reasonably concluded the project was broken.

Kept as a stated gap rather than deleted, because the idea is worth building
and a silent deletion would lose it. What exists today for provenance is:

    scientific resolve ... --export-model model.txt      # Antimony with
                                                         # provenance in comments
    scientific resolve ... --export-citations refs.bib   # BibTeX / RIS

`scripts/check_commands_runnable.py` now fails the build on a documented
command that cannot run, which is what should have caught this the day it
was written.

### 4. Simulation Validation System

```bash
# Run the full validation pipeline
python validation/run_validation_pipeline.py \
  --model SIR \
  --golden-dataset validation/golden_datasets/sir_golden.csv \
  --literature validation/literature/sir_literature.json \
  --output validation/reports/sir_validation_report.md

# Launch the validation analysis notebook
jupyter notebook validation/validation_analysis.ipynb
```

## Directory Structure — PLANNED, not present

Every directory below is unbuilt; see the notice at the top of this file
for what is actually here.

```
/advanced_analysis/            # PLANNED LAYOUT — see notice above
├── architecture/
│   ├── architecture_diagram.excalidraw  # Excalidraw JSON for architecture
│   └── architecture_guide.md             # Documentation
├── performance/
│   ├── benchmarks/                       # Benchmarking scripts
│   ├── performance_analysis.ipynb        # Jupyter notebook for analysis
│   └── requirements.txt                  # Dependencies
├── provenance_visualization/
│   ├── scripts/                          # Visualization scripts
│   ├── data/                             # Sample data
│   ├── dashboard.py                      # Interactive dashboard
│   └── docs/                             # Documentation
├── validation/
│   ├── golden_datasets/                  # Curated golden datasets
│   ├── literature/                       # Literature database
│   ├── scripts/                          # Validation scripts
│   ├── reports/                          # Generated reports
│   ├── validation_analysis.ipynb         # Jupyter notebook
│   └── run_validation_pipeline.py       # Validation pipeline
├── requirements.txt                     # Main dependencies
└── README.md                            # This file
```

## Advanced Features

### Simulation Domain Architecture

- Interactive Excalidraw diagram with layers
- Color-coded by domain type (deterministic, stochastic, discrete)
- Clickable elements for detailed views
- Mathematical notation for core equations
- Literature citations as clickable references

### Performance Analysis

- Benchmarking scripts for all 11 simulation domains
- Time, memory, and scalability metrics
- Comparative analysis between domains
- Visualization of performance characteristics
- Identification of performance bottlenecks
- Optimization recommendations

### Provenance Tracking

- Parameter resolution flow visualization
- Provenance tree for parameter lineage
- Literature citation tracking
- Cross-species fallback visualization
- Error handling and validation visualization
- Interactive web-based dashboard

### Simulation Validation

- Golden dataset validation with statistical tests
- Theoretical invariant checking (conservation laws, etc.)
- Literature comparison with citation tracking
- Statistical validation (hypothesis testing, distribution fitting)
- Automated reporting with visualizations
- Comprehensive validation pipeline

## Running the Complete System

```bash
# 1. Generate architecture diagram (open in Excalidraw)
# 2. Run performance benchmarks
python performance/benchmark_all_domains.py

# 3. Launch performance analysis notebook
jupyter notebook performance/performance_analysis.ipynb

# 4. (there is no provenance dashboard -- see "NOT BUILT" above)

# 5. Run validation pipeline for a specific model
python validation/run_validation_pipeline.py \
  --model SIR \
  --golden-dataset validation/golden_datasets/sir_golden.csv \
  --literature validation/literature/sir_literature.json \
  --output validation/reports/sir_validation_report.md

# 6. Launch validation analysis notebook
jupyter notebook validation/validation_analysis.ipynb
```

## Documentation

Each component has detailed documentation:

- `architecture/architecture_guide.md`
- `performance/README.md`
- `provenance_visualization/docs/visualization_guide.md`
- `validation/README.md`

## License

This system is part of the Caterva project and is licensed under the same terms as Caterva.