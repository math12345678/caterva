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
