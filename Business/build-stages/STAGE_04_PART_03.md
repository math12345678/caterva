# Stage 4, Part 3 — Domain Spec: Honest Parameter Provenance at the API Surface

Stage 4 of 100. Part 3.

## 0. Why this part exists

Part 2 specified the boundary contract and closed itself as "Part 2 of 2".
That work is sound and was independently audited. But making all eight domains
reachable exposed something that could not be seen while five of them had no
path to a user. This is not a defect in Part 2's work. It is a property of the
resolver that only becomes visible once every domain can actually be asked for.

## 1. ONE-SENTENCE DEFINITION

Make the API's provenance payload state what is actually known about each
returned parameter — distinguishing a value resolved from primary literature
from a teaching default that was never looked up — so the product's central
claim is either true of every number it returns or visibly qualified.

## 2. THE PROBLEM, MEASURED

### 2.1 Model citations are attached to invented parameters

Every domain in `DOMAIN_DEFAULTS` (`src/lib/queryResolver.ts`) carries a
`citations` array. In isolation this reads as the trust trail working across
all eight domains:

```typescript
{
  domain: "wright_fisher",
  parameters: { population_size: 100, starting_frequency: 0.5,
                generations: 100, replicate_runs: 100, ... },
  citations: ["Fisher R.A. (1930) The Genetical Theory of Natural Selection."],
}
```

**The citation describes the model. The parameters are hardcoded literals.**

`population_size: 100` did not come from Fisher 1930; nothing looked it up.
The molecular-dynamics entry is starker: `n_particles: 108, temperature: 0.4`
sit beside a citation to Hoare & Pal 1971 — a paper about cluster global
minima, which says nothing about either number. Terrium's own Stage 3 used
that paper correctly, for LJ13's energy. Here it is decoration.

### 2.2 Exactly one value in the product is genuinely resolved

The literature path is real, but it is reached by one branch:

```typescript
if (best.domain === "mm" && fallbackEntities?.ecNumber) {
  const agentResult = await resolveKineticValue(fallbackEntities);
  if (agentResult.found && agentResult.km !== undefined) {
    parameters = { ...parameters, km: agentResult.km };
    flags.push(`Resolved Km=${agentResult.km} ... from ${agentResult.source}`);
  }
}
```

`km`, in `mm`, when an EC number is extractable. That is the complete set of
values in Terrium that trace to a lookup. Every other number in every other
domain — including `vmax` and `s0` in Michaelis-Menten itself — is a default
with a model citation beside it.

### 2.3 Why this matters more than ordinary mislabelling

The claim is *"every number traces back to a citation that has been
independently checked."* The engine's verification work is genuinely
exceptional and none of it is in question here. But a student asking for a
Wright-Fisher simulation receives invented parameters presented next to a
1930 citation, inside a product whose entire design language says provenance.

The failure is not that the defaults are bad — `population_size: 100` is a
fine teaching value. It is that **the response cannot distinguish a default
from a resolved value.** A reader cannot tell which is which, so the one
honest citation is indistinguishable from the seven decorative ones.

This is Rule 2 applied to provenance. Rule 2 exists because silently
accepting an implausible value is worse than rejecting it loudly. A citation
that does not support the number beside it is worse than no citation, because
it converts *"we don't know"* into *"we checked."*

### 2.4 What already works and must not be rebuilt

- The `flags` array already does the honest thing in the `mm` path:
  *"Could not resolve a real Km value from BRENDA/KEGG/PubMed; using default
  Km."* That instinct is exactly right. It is unstructured, reached in one
  branch, and easy for a UI to drop.
- `PARAMETER_PATTERN` already extracts user-supplied values (`km=0.5`) — a
  third provenance category distinct from both default and resolved.
- Model citations are legitimately useful. Fisher 1930 *is* the right citation
  for the Wright-Fisher model. The error is presenting it as a citation for
  the parameters.

## 3. CONTINUOUS OR DISCRETE

Not applicable; no simulation is written. Noted rather than skipped, per Rule
3's requirement that the decision be explicit per stage.

## 4. PUBLIC INTERFACE

```typescript
export type ParameterOrigin =
  | "resolved"    // looked up in primary literature for THIS query
  | "user"        // supplied in the query text
  | "default";    // teaching default; nothing was looked up

export interface ParameterProvenance {
  origin: ParameterOrigin;
  source?: string;     // only when resolved, e.g. "BRENDA EC 1.1.1.27"
  citation?: string;   // only when resolved; supports THIS value
  organism?: string;   // only when resolved
  note?: string;       // why a lookup was attempted and failed
}

export interface ResolvedQuery {
  runId: string;
  domain: SimulationDomain;
  parameters: Record<string, unknown>;
  /** Exactly one entry per key in `parameters`. */
  parameterProvenance: Record<string, ParameterProvenance>;
  provenance: {
    reasoning: string;
    /** Renamed: describes the MODEL, never the parameter values. */
    modelCitations: string[];
    flags: string[];
  };
}
```

The rename from `citations` to `modelCitations` is the load-bearing change and
is deliberately breaking. A field named `citations` sitting beside a parameter
block will be read as citing those parameters — by a UI author, a reviewer, a
student. The name should make the wrong reading impossible.

## 5. VALIDATION CONTRACT

The provenance analogue of Rule 2's three states.

**Hard rejections — the response must not be returned:**

- A key in `parameterProvenance` absent from `parameters`, or vice versa. A
  parameter with no provenance entry is precisely the ambiguity this part
  removes.
- `origin: "resolved"` with no `citation`. A value claiming to be resolved
  must name what resolved it. This is the single most important assertion in
  this part.
- A `citation` on any entry whose origin is not `"resolved"`.

**Flags (returned, with the warning attached):**

- Every parameter has `origin: "default"`. Valid — it is what *"simulate
  genetic drift"* should produce — but the caller should know nothing here
  was looked up.
- A lookup was attempted and failed. Preserve the existing message; move it
  into that parameter's `note`.

**Explicitly not an error:** a response that is mostly defaults. That is the
normal case and must stay ergonomic. The requirement is that it be *legible*,
not that it be prevented.

## 6. VERIFICATION TARGET

No closed form applies. Rule 1's ground truth here is the correspondence
between two records, which is checkable exactly.

**Target A — structural correspondence.** For all eight domains,
`Object.keys(parameters)` equals `Object.keys(parameterProvenance)` as sets.
Exact, not approximate.

**Target B — no unsupported citation.** For all eight domains, no
`parameterProvenance` entry carries a `citation` unless `origin` is
`"resolved"`. **This test must fail against the pre-change code.** If it
passes before the change, it is not testing what it claims.

**Target C — the resolved path still resolves.** An `mm` query with a
recognisable EC number yields `km` with `origin: "resolved"` and a non-empty
`citation`. The one genuine literature path must not regress while the
structure around it is rebuilt.

**Target D — user values attributed to the user.** A query containing
`km=0.5` yields `km` with `origin: "user"` and no citation. Today
`PARAMETER_PATTERN` extracts this and the result is indistinguishable from a
default.

**Target E — the all-defaults case is flagged**, with a reason naming the
absence of resolved parameters.

### Pre-specified mutations (Rule 6)

| # | Mutation | Predicted catcher |
|---|---|---|
| 1 | Attach a `citation` to a default-origin parameter | Target B |
| 2 | Drop one key from `parameterProvenance` | Target A |
| 3 | Mark a default parameter `"resolved"` with no citation | validation rejection |
| 4 | Revert `modelCitations` to `citations` | a naming test asserting absence |
| 5 | Break the EC-number branch so `mm` silently uses the default `km` | Target C |

Mutation 5 is the one that matters — it is the real-world failure this part
exists to prevent. The prediction is a contract to check, not a claim to
trust; the implementation records what actually fired.

## 7. RELEVANT ADRs

- **ADR 0007** — directly applicable and extended. It records that structural
  checks belong on the TypeScript side, which is why this work lives there.
- **ADR 0008 (new)** — parameter provenance is per-parameter and typed; model
  citations are a separate field from value citations. Architecturally
  significant: it changes the API contract and constrains every future domain.
- **ADR 0003** — precedent for keeping this in one layer rather than mirroring
  it into Python.
- ADR 0001, 0002, 0005, 0006 — not applicable. Noted.

## 8. SHARED-CONSTRAINT CHECK

`parameters` and `parameterProvenance` are the same constraint expressed
twice — exactly the shape Rule 4 requires an executable test for, and exactly
the shape that produced the runner/`__all__` drift Part 1 fixed. Target A is
that test, and it must run for all eight domains rather than a sample, since
sampling is how the original drift survived.

## 9. OUT OF SCOPE

- **Provenance travelling through the Python engine.** Stage 5. This part
  makes the API honest about what it currently knows; it does not move
  information across the boundary.
- Extending the literature path to domains beyond Michaelis-Menten — real
  work, needs its own grounding, and is worth more once provenance is typed.
- A golden set of hand-verified enzyme/substrate/Km/citation tuples — Stage 5.
- Mutation testing the resolver's scientific correctness — Stage 5.
- UI work. The API is the deliverable.
- New simulation domains.

If any of these proves unavoidable mid-implementation, the correct action is
an ADR or a spec amendment written **at the time** — the Stage 2 audit
finding.

## 10. DELIVERABLES CHECKLIST

- [ ] `ParameterOrigin` / `ParameterProvenance` exported; `parameterProvenance`
      populated for every domain.
- [ ] `citations` → `modelCitations` throughout, including `openapi.yaml` and
      every generated client under `Science-Agent-Pipeline/lib/`.
- [ ] The `mm` EC path sets `origin: "resolved"` with source, citation, organism.
- [ ] `PARAMETER_PATTERN` extractions set `origin: "user"`.
- [ ] Validation rejecting mismatched keys and unsupported citations.
- [ ] Vitest coverage for Targets A–E; all five mutations run and recorded.
- [ ] `docs/adr/0008-*.md` plus its index row.
- [ ] Both suites green; both guard scripts clean.

## 11. The ready-to-paste implementation prompt

```
You are implementing a piece of Terrium, a scientific simulation engine
for teaching labs. Before you write any code, internalize these
non-negotiable standards — they exist because each one was learned from a
real bug in this exact codebase, not as generic best practice:

1. Every numerical claim you implement must be checked, in a test, against
   an exact closed-form solution, a known-correct independent solver, or a
   physical invariant. "The output looks like a reasonable curve" is not
   verification and will be rejected in review.

2. Distinguish physically-impossible parameters (reject with ok=False,
   raise ModelBuildError, never simulate) from physically-possible-but-
   implausible parameters (ok=True, flagged=True, flag_reason set,
   simulation still runs). Use exactly these field names. Do not collapse
   this distinction in either direction.

3. Before writing any simulation logic, explicitly state whether this
   domain is continuous-time (belongs in the antimony -> SBML -> roadrunner
   pipeline) or discrete (belongs as a direct Python recurrence, no ODE
   solver). Do not default to whichever pattern the last domain used
   without checking it's actually correct for this domain's physics.

4. If this domain shares any constraint (a bound, a unit, a name) with
   another part of the system, that sync must be enforced by an executable
   test that would fail if the two drifted apart — not just a comment.

5. Every new import needs a corresponding line added to requirements.txt
   (or package.json) in the same change. Do not leave this for CI to catch.

6. After writing your tests, perform at least one mutation test:
   deliberately break your own implementation in a specific, realistic way,
   confirm the relevant test fails, then revert and confirm the suite is
   clean again. Document exactly what you broke and which test caught it.

7. Never `pip install tellurium` (the umbrella package) or suggest it.
   Use libroadrunner, antimony, and python-libsbml directly.

8. If antimony model generation is involved, check every new
   variable/parameter name against antimony's reserved words before using
   it directly — `gamma` is one known collision, there may be others.

9. If you're making a decision that a different, equally-reasonable
   engineer might have made differently (not just a variable name, but a
   real architectural choice), flag it explicitly in your final report
   rather than silently picking one.

10. Report back explicitly: what you implemented, what closed-form/
    invariant/solver you verified against, what mutation test you ran and
    what it caught, and any judgment call you made that wasn't fully
    specified in the task. A bare "tests pass" is not sufficient.

---

STAGE 4, PART 3 — HONEST PARAMETER PROVENANCE

THIS IS TYPESCRIPT WORK. Do not modify tellurium_engine.py. Do not modify
tellurium_runner.py. Do not add simulation domains. Do not change any
parameter VALUE — the defaults are fine, only their labelling is wrong.

Read Business/build-stages/STAGE_04_PART_03.md first, and
docs/adr/0007-contract-test-for-engine-application-boundary.md, which
establishes that structural checks belong on the TypeScript side.

=========================================================
THE PROBLEM
=========================================================

In src/lib/queryResolver.ts every domain in DOMAIN_DEFAULTS carries a
`citations` array. Those citations describe the MODEL. The parameters
beside them are hardcoded teaching defaults that nothing looked up.

A Wright-Fisher query returns population_size=100 with "Fisher R.A.
(1930)" attached. Fisher 1930 says nothing about 100. A molecular-
dynamics query returns n_particles=108, temperature=0.4 citing Hoare &
Pal 1971 — a paper about cluster global minima.

Exactly one value in the product is genuinely resolved: `km`, in domain
`mm`, when an EC number is extractable. See the
`if (best.domain === "mm" && fallbackEntities?.ecNumber)` branch.

The product claims every number traces to a checked citation. Right now
a reader cannot tell a looked-up value from an invented one, which makes
the one honest citation indistinguishable from the seven decorative
ones. That is the bug.

=========================================================
WHAT TO BUILD
=========================================================

1. TYPES — in src/lib/queryResolver.ts or a new src/lib/provenance.ts:

     type ParameterOrigin = "resolved" | "user" | "default";

     interface ParameterProvenance {
       origin: ParameterOrigin;
       source?: string;     // only when resolved
       citation?: string;   // only when resolved; supports THIS value
       organism?: string;   // only when resolved
       note?: string;       // why a lookup failed, if attempted
     }

2. PER-PARAMETER RECORDS. ResolvedQuery gains
   `parameterProvenance: Record<string, ParameterProvenance>`, exactly one
   entry per key in `parameters`. Every DOMAIN_DEFAULTS parameter is
   origin "default".

3. RENAME `provenance.citations` -> `provenance.modelCitations`
   everywhere, including lib/api-spec/openapi.yaml and every generated
   client under lib/api-zod and lib/api-client-react. Breaking, and
   intended: a field called `citations` next to a parameter block will be
   misread by every future reader.

4. WIRE THE THREE ORIGINS.
   - the mm EC branch sets origin "resolved" with source, citation and
     organism from the agent result; keep the existing failure message,
     move it to `note` on the km entry
   - PARAMETER_PATTERN extractions set origin "user"
   - everything else stays "default"

5. VALIDATION. Reject (do not return) when: key sets of `parameters` and
   `parameterProvenance` differ; an entry is "resolved" with no citation;
   an entry has a citation but is not "resolved". Flag but return when
   every parameter is "default", and when a lookup failed.

6. ADR — docs/adr/0008-parameter-provenance.md (Status: Accepted,
   Context/Decision/Consequences) plus its row in docs/adr/README.md.

=========================================================
TESTS (vitest, src/__tests__/)
=========================================================

A  all 8 domains: keys(parameters) === keys(parameterProvenance) as sets
B  all 8 domains: no citation unless origin is "resolved"
C  mm + EC number -> km origin "resolved", non-empty citation
D  query containing "km=0.5" -> km origin "user", no citation
E  bare domain query -> flagged true, reason names the absent resolution

BEFORE changing anything, write Target B and run it. It MUST fail on the
current code. Include that failure output in your report. If it passes
before your change, the test is not testing what it claims.

MUTATIONS — run all five, report which tests ACTUALLY fired:
  1. attach a citation to a default-origin parameter
  2. delete one key from parameterProvenance
  3. mark a default parameter "resolved" with no citation
  4. rename modelCitations back to citations
  5. break the EC branch so mm silently uses the default km

Mutation 5 is the one that matters.

=========================================================
CONSTRAINTS
=========================================================

- TypeScript only. No Python or engine changes.
- Do not add literature lookup for new domains — Stage 5.
- Do not move provenance across the Python boundary — Stage 5.
- No new runtime dependency.
- Keep the existing flags array; you are generalising it, not replacing it.

=========================================================
FILE OWNERSHIP — READ THIS
=========================================================

Three implementers work from this prompt simultaneously. Stage 4 Part 1
produced TWO files both numbered ADR 0007, one per implementer, because
each wrote one independently. Only one was indexed, so the other sat
invisible in the tree while still being committed.

Therefore: if docs/adr/0008-parameter-provenance.md ALREADY EXISTS when
you start, do not create a second ADR under a different filename. Read
it, then adopt or amend it in place, and say in your report what you
changed and why. Same for any test file. A duplicate-numbered ADR is a
defect, not a merge conflict to work around.

=========================================================
REPORT BACK
=========================================================

Per Rule 10, plus:
 1. Eight-domain table: domain, parameter count, origin breakdown.
 2. Target B's failure output against the PRE-change code.
 3. All five mutations: predicted catcher vs. what actually fired.
 4. Every file touched by the citations -> modelCitations rename,
    including generated clients.
 5. Whether ADR 0008 already existed, and what you did about it.
 6. Full vitest run plus both Python guard scripts.
```

## 12. What Part 4 covers

Independent verification: check the claims rather than the reports. The two
highest-value checks are Target B against pre-change code (it must fail — a
green result there means the test is inert) and mutation 5, the only one that
reproduces the real failure. Both are cheap to reproduce and both are exactly
the kind of claim that has been wrong before in this project.
