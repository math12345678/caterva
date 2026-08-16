# `Science-Agent-Pipeline/` — the Express API server

A pnpm workspace holding the production HTTP API and the agent pipeline
behind it. Split out from the main tree because it has its own toolchain
(pnpm, its own `tsconfig`, its own test runner) and ships as its own
repository, `science-agent-pipeline-replit`.

## Layout

| path | what it holds |
|---|---|
| `artifacts/api-server/` | the server. `src/lib/` is where the interesting code is |
| `lib/api-spec/` | the OpenAPI spec and the orval codegen config |
| `lib/api-zod/` | the generated zod contract — **generated, do not hand-edit** |
| `scripts/` | workspace build and check scripts |

Modules worth knowing in `artifacts/api-server/src/lib/`:

| module | job |
|---|---|
| `queryResolver.ts` | resolves every parameter for a request and assembles the provenance |
| `scienceAgent.ts` | the boundary type between the Python runner and TypeScript. Read its field comments — most of them record a defect |
| `assayCoherence.ts` | cross-parameter coherence: `same_source` / `same_conditions` / `differing_conditions` / `unassessable` |
| `reliabilityScore.ts` | **types only.** The grading functions were deleted deliberately; see below |
| `provenance.ts` | buffer identity and effector types |

## Running it

```bash
pnpm install --frozen-lockfile
pnpm --filter @workspace/api-server run test
python scripts/check_codegen_loads.py        # from the repo root
```

## Things that will bite you

**`reliabilityScore.ts` exports no callable, on purpose.** It used to
recompute Bakker's three axes in TypeScript while the Python runner already
computed and emitted them — and the TypeScript copy was strictly worse,
because its call site never passed a `PhysiologicalReference` and one axis
was permanently `not_assessed`. A parity test asserted the two agreed; it
could not detect the disagreement, because it pinned the two
*implementations* against a shared fixture rather than the two *call sites*.
The test that guards the deletion asserts the module exports **no callable at
all**, not merely that four names are gone
([ADR 0027](../docs/adr/)).

**The zod contract is generated and committed.**
`scripts/check_codegen_loads.py` regenerates it into a scratch directory and
asserts the committed copy matches. That guard once passed for the wrong
reason: its probe config hardcoded `mode: "single"` while the shipped config
says `"split"`, so the guard regenerated using its own copy of the settings
and agreed with itself. The probe now spreads the shipped config and replaces
only the workspace path.

The mode was not the culprit, though it was blamed for a while. Measured
under the pinned orval 8.21.0, `single` and `split` emit **byte-identical**
output for the zod target — the "orval honours `coerce` in one mode and
ignores it in the other" claim this paragraph used to make is false. The
409-line diff that appeared the moment the probe was fixed was the
accumulated staleness the guard had never been able to see, arriving all at
once, and it was misread as a consequence of the setting that had just been
corrected. See [ADR 0036](../docs/adr/0036-the-shipped-codegen-config-does-not-reproduce-the-committed-contract.md).

**`brenda_ec` is deliberately excluded from `SOURCE_IDENTITY_KINDS`.** An EC
number names the enzyme, not the paper. Two values sharing an EC number are
not from the same source, and treating them as such would report coherence
that was never established.

**A buffer verdict sits beside the conditions verdict, never folded into
it.** Same reason: a reader must be able to see which of the two agreed.

**`node_modules/` and `attached_assets/` are large.** Restrict searches to
`artifacts/` and `lib/` or expect a slow grep.
