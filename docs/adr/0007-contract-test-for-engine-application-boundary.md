# ADR 0007: Enforce the engine/application boundary with a contract test, not a shared schema or code generation

**Status:** Accepted

## Context

The Terium engine (Python) exposes its simulation API through
`terium_engine.__all__`. The application layer (TypeScript) reaches it
through a single JSON bridge, `terium_runner.py`, which the API server
spawns as a subprocess. Before Stage 4 Part 1, the runner dispatched only
three domains (`mm`, `sir`, `seir`) while the engine exposed eight — every
domain built under the constitution was unreachable from the product, and
nothing in CI detected it. The engine's test suite and the application's
53-test vitest suite were each green while the boundary between them was
broken.

The failure is structural: the dispatch table and `__all__` are the same
constraint written in two languages. Nothing in either language's test
suite can see the other side.

Two mechanisms would close the gap "for real":

1. A shared schema (JSON Schema / zod + Pydantic) that both sides import,
   or code generation of the runner from `__all__` at build time.
2. A contract test that imports the engine's `__all__` and the runner's
   dispatch table and asserts they are in lockstep, run in CI on every
   push.

## Decision

Enforce the boundary with a **contract test** (`Terium/tests/
test_boundary_contract.py`), not a shared schema and not code generation.

The test loads the actual `terium_runner.py` file the API server spawns
(not a copy), collects every `simulate_*` in the engine's `__all__`, and
asserts that the runner's `DISPATCH` table dispatches exactly that set —
and that every dispatched function still exists in the engine. Mutation
tests (pre-specified by the stage spec, Rule 6) delete one dispatch entry
and confirm the test fails; they also simulate an engine gaining a
`simulate_*` the runner does not dispatch.

The runner is the single point of contact. It maps the eight product
domains plus the typed `sbml` raw-SBML escape hatch to engine functions,
preserving the `ok` / `flagged` / `flagReason` contract across the language
boundary.

### Where validation lives

Scientific validation stays authoritative in Python. The TypeScript layer
checks only the structural presence and transport type of parameters; it
does not restate physical bounds. This is the decision Stage 4 Part 1 §2.4
left open, and it is made deliberately rather than inherited: duplicating a
bound like `MD_PLAUSIBLE_TEMPERATURE_HIGH` in a Zod schema creates two
sources of truth for one scientific constraint, and Rule 4 exists because
that pair silently drifts. The Km bounds already drifted once between the
literature and simulation layers, which is what ADR 0003 was written to
stop.

Separately, the runner applies **API runtime ceilings**
(`MAX_API_MONTE_CARLO_SAMPLES`, `MAX_API_MD_STEPS`). These are not
scientific bounds and must not be confused with them: a ten-million-sample
Monte Carlo run is perfectly valid science and an unacceptable synchronous
HTTP request. They bound request cost without touching the engine's
scientific contract, and they live in the runner because that is the layer
that knows it is serving a request.

## Why not the alternatives

- **Code generation from `__all__`** would put the boundary under build
  tooling that must run in both build environments, and would regenerate
  the domain-specific serialisation logic (parameter coercion, result
  shape mapping) that is genuinely hand-written. It fixes drift by
  removing the human from the loop — but it also removes the human from
  the *review* loop: a new `simulate_*` would silently appear in the
  product with no decision about whether it should be exposed there.
  The contract test fails loudly and hands the question to a person.
- **A shared schema** (zod/Pydantic) would couple the two layers through
  a schema artifact that must be versioned, published, and imported by
  both — in this repo, a nested pnpm workspace plus a Python package
  that is not published at all (no umbrella package, ADR 0001). It is
  the heaviest mechanism for the simplest constraint (a set of names).
  The interesting validation — scientific bounds — correctly lives in
  the engine where the physics is, not in a schema both sides import.
- The existing test suites individually miss this class of failure. The
  contract test is deliberately one test file run in the Python CI job
  that already exists, costing nothing new in infrastructure.

## Consequences

- A new engine `simulate_*` fails CI until the runner dispatches it —
  making reachability a first-class requirement instead of an accident
  of the product layer.
- A deleted dispatch entry fails CI with a message naming the orphaned
  engine function, pinning the fix to the boundary.
- The serialisation logic remains hand-written in one file
  (`terium_runner.py`), where its per-domain mapping is visible to
  review. The contract test guards the *set* of domains; the runner's
  execution tests guard each domain's `ok`/`flagged`/`flagReason` shape.
- No new build tooling, no published schema package, no code generation
  step. CI gains one test file on the existing Python job (and the
  application layer's vitest suite gains a job of its own).
- The runner's dispatch table becomes the place where "is this domain
  reachable from the product?" is answered, reviewable in a diff.
