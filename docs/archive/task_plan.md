# Repository-wide audit plan

## Goal
Inspect the entire Caterva codebase and produce an evidence-backed orientation and risk report without changing product code.

## Phases
- [x] Establish repository state, scope, and local instructions.
- [ ] Inventory tracked and untracked source, configuration, documentation, tests, generated artifacts, and nested projects.
- [ ] Trace architecture, entry points, data flow, and module boundaries.
- [ ] Review quality signals: tests, lint/type/build configuration, CI, security-sensitive patterns, TODOs, and dependency posture.
- [ ] Run safe verification commands and reconcile failures with repository state.
- [ ] Deliver prioritized findings and a concise codebase map.

## Constraints / decisions
- Preserve all pre-existing user changes.
- Treat vendored dependencies, virtual environments, caches, coverage output, and build artifacts as inventory targets but do not manually review every generated file.
- No product-code edits are authorized by this inspection request.

## Next Step
Build a file/count/configuration inventory and identify all independently runnable projects.

## Errors Encountered
| Error | Attempt | Resolution |
|---|---:|---|
| None | - | - |
