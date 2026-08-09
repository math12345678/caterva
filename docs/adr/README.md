# Architecture Decision Records

These document real decisions already made in this codebase, with the
reasoning behind them -- most of that reasoning previously only existed as
scattered code comments and README asides. Formalizing it here means a new
contributor (the backend hire, a Kickstart mentor doing technical
diligence) can find *why* a decision was made without archaeology through
git blame.

New ADRs should be added, never edited after acceptance -- if a decision
changes, write a new ADR that supersedes the old one and says so explicitly
(see the "Status" field convention below).

## Format

Each ADR has:
- **Status**: Proposed / Accepted / Superseded by ADR-000X
- **Context**: what problem or constraint forced a decision
- **Decision**: what was actually decided
- **Consequences**: what this makes easier, harder, or forecloses

## Index

| ADR | Title |
|---|---|
| [0001](0001-no-tellurium-umbrella-package.md) | Do not depend on the `tellurium` umbrella package |
| [0002](0002-pcr-not-modeled-as-an-ode.md) | Model PCR as a discrete recurrence, not through antimony/roadrunner |
| [0003](0003-shared-plausibility-bounds.md) | Km plausibility bounds must be identical across the literature and simulation layers |
| [0004](0004-gamma-reserved-keyword.md) | Emit the SIR/SEIR recovery rate as `gamma_rate`, not `gamma` |
| [0005](0005-rng-convention.md) | Discrete/stochastic domains share a single RNG convention |
| [0006](0006-md-direct-python-not-roadrunner.md) | Model molecular dynamics as direct Python (velocity Verlet), not through antimony/roadrunner |
| [0007](0007-contract-test-for-engine-application-boundary.md) | Enforce the engine/application boundary with a contract test, not a shared schema or code generation |
| [0008](0008-parameter-provenance.md) | Honest parameter provenance at the API surface: per-parameter origins and a breaking `citations` → `modelCitations` rename |
| [0009](0009-gillespie-ssa.md) | Gillespie SSA domain — single first-order decay reaction (A → B) |
| [0010](0010-strenda-assay-conditions.md) | A resolved kinetic constant without assay conditions cannot be `verified` (STRENDA) |
| [0011](0011-llm-parameter-origin.md) | An LLM-supplied parameter is its own origin, not a `default` |
| [0012](0012-kcat-resolved-but-not-simulated.md) | kcat is resolved from literature but is not a simulation parameter |
| [0013](0013-enzyme-concentration-bridges-kcat-to-vmax.md) | Enzyme concentration is a caller input, and it bridges kcat to Vmax |
| [0014](0014-python-version-support.md) | Python 3.10–3.13, and what actually constrains it |
| [0015](0015-constitution-rules-must-be-executable.md) | A constitution rule that nothing executes is not enforced |
| [0016](0016-cached-results-lose-parameter-provenance.md) | Cached results serve no per-parameter provenance |
| [0017](0017-epidemiology-parameter-resolution.md) | Epidemiology parameters (R0, infectious period) are resolved from a hand-curated registry, not yet wired to RESOLVABLE_FIELDS |
| [0018](0018-ki-inhibition-constant-resolution.md) | Ki (inhibition constant) resolved via per-quantity BRENDA table lookup, wired end-to-end into RESOLVABLE_FIELDS |
| [0019](0019-kcat-resolution-exposed-not-yet-wired-to-vmax.md) | kcat is now literature-resolvable via BRENDA's Turnover Numbers table, and bridges to a simulable Vmax when the caller supplies enzyme_conc |
| [0020](0020-epidemiology-parameters-wired-to-resolvable-fields.md) | Epidemiology (R0, infectious period) is wired end-to-end into the SIR domain via a beta/gamma bridge |
| [0021](0021-strenda-applies-only-to-governed-parameters.md) | The STRENDA rule applies only to STRENDA-governed parameters, enforced by a mandatory `parameterKey` |
