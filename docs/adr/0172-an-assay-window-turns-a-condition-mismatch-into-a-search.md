# ADR 0172: An assay window turns a condition mismatch into a search — re-selecting the row that actually sits at the reference's conditions

**Status:** Accepted

**Date:** 2026-09-07

**Relates to:** ADR 0171 (the blackboard architecture; this is the first
constraint kind it gains), ADR 0027 (a second threshold for a judgement the
model judge already makes is a second opinion that drifts), ADR 0028 (a
check that fires too broadly stops being read), ADR 0010 / STRENDA (assay
conditions), ADR 0008 (parameter provenance).

## Context

ADR 0171 left the pH / temperature gap a finding because the one-row answer
made it true that *"a pH requirement would be a demand nothing can satisfy"*.
That sentence was true of the resolver's one-row answer and false of the
frontier the resolver returned alongside it. `resolve_kinetic_value` already
survives **every** row through `_score_frontier` and returns them as
`ensemble_candidates` — the per-row scores exist because the sample weights
need them — and those same rows were never re-used as an answer set. The
coherence critic, the one agent that compares two values, was being handed
the fix and nobody looked.

The other half was already decided too. "How far is too far" is a statement
judgement the model judge has carried since it was built:
`PH_UNITS_SERIOUS = 1.0` and `TEMPERATURE_C_SERIOUS = 10.0`, each with its
own written reasoning. A window built on different thresholds would be a
second opinion about the same scientific question, and ADR 0027 records what
a second opinion that drifts is worth.

And ADR 0171's tie rule — two values from two organisms is always a tie, so
explore rather than choose — does not cover this case. A pH gap is not a
tie: often exactly one of the two frontiers has a row inside the other's
conditions, and then there is no choice to make, only the reference's
already-measured row to return.

## Decision

A new constraint kind, `assay_window`. The requirement text is the
**reference value's stated conditions**; the fix is the **row of the movable
value's own frontier that actually sits inside them**. Nothing is invented:
no interpolation, no averaging, no Q10 correction. Re-selection means
"return the row that actually sits at those conditions", never "adjust the
number to fit".

Three rules carry it.

### 1. The window is the judge's threshold, not a second one

`caterva/agents/assay_window.py` declares no new "how far is too far". Its
half-widths are the model judge's own `*_SERIOUS` thresholds. A candidate is
inside the window when, on every axis that **both** it and the reference
state, it lies within one of those thresholds of the reference. The metric
is a per-axis-normalised Chebyshev distance — "how far out is this row,
measured with the same ruler the model judge uses". An axis one side is
silent on is skipped. A candidate that states **no** conditions is
`unassessable` — distance `None`, never close, never chosen: reporting
silence as proximity is how a model becomes wrong quietly, and `None` is
deliberately distinguishable from distance 0. A constraint's identity is
`(kind, subject, requirement)`, so the requirement is rendered by exactly
one canonical `window_requirement` / `parse_window_requirement` pair, tested
round-trip, or the store would not deduplicate and the run would never
converge.

### 2. The critic emits only when one side can move

The coherence critic asks, for each value of the mismatch, "does my own
frontier hold a row inside the other value's conditions?".

- **Exactly one does**: that side is the subject; the other is the anchor.
  A constraint `assay_window [subject] must be <anchor's conditions>` is
  raised, because it is satisfiable and the search should be run.
- **Both do**: either could be re-selected and neither is privileged. The
  mismatch stays a finding with a note naming why — Caterva will not pick a
  side. This is ADR 0171's "explore, do not choose" applying to the case it
  was built for.
- **Neither does**: no re-search could remove the mismatch; it stands as a
  finding. Promising a search would converge the run and then hand the
  report a requirement no search ever applied — ADR 0171's exact argument
  for refusing unactionable constraints.

### 3. The scout re-selects, and reports what it replaced

Under an `assay_window` the scout restricts the source's frontier to rows
inside **every** active window, ranks them by distance to the reference, and
ties are broken by the resolver's own preference (smallest value) — so a
re-selection never behaves differently from the resolver on the question the
window leaves open. If the already-chosen value is the nearest inside row,
the choice stands with a note. Otherwise the source is replaced honestly:
value, ph and temperature_c from the row; buffer `None` (the frontier
carries no buffer axis); citation `reference_id:` of the chosen row;
`explicitly_unreported = ()`; and organism with `cross_species = True` when
the chosen row states a different organism. The build report records the
replacement in `rejected_values()`, so a reader sees both the row that won
and the resolver's default that lost. Emission and honouring use the literal
kind strings, which
`scripts/check_constraints_are_actionable.py` verifies by reading the agents'
ASTs.

## Consequences

**The gap that was a report becomes a search, and the loop closes it.** On
the real LDH pages: the lactate Km sits at pH 8.0 with no pH-6 row in its
table, so it is immovable — the anchor; the kcat table's frontier holds
32.0 1/s at pH 8.0 / 25, so `assay_window [kcat] must be pH 8` is raised and
the scout returns 32.0 over the resolver's default minimum 21.1 (pH 6.0 /
25). The run converges in two rounds and ends with no `ph_mismatch` finding.
Km was never reported as moved.

Added 2026-09-30: the two rows are of different substrates. That kcat
request names none, so its frontier holds every substrate the turnover
table has; 21.1 1/s (BRENDA ref 684519) is a pyruvate row and 32.0 1/s
(ref 670748) an NAD+ row. The re-selection line now says so ("re-selected
to 32.0 1/s for NAD+ ... replacing 21.1 1/s for pyruvate"), and the scout
carries the row's own commentary rather than the default's. Asked for
pyruvate's kcat, the same search raises no window and keeps 21.1 1/s, with
the pH gap reported (Tests/test_agent_architecture_on_real_brenda.py). Two
details of the replacement described above have also changed: the chosen
row is cited "BRENDA ref 670748", as the adapter cites the resolver's own
row, not `reference_id:670748`; and its buffer is the row's own as the
frontier carries it (ADR 0175), not `None`. Added 2026-10-01: whether the
row carried is already the nearest is decided by value and commentary, not
by value alone, so a row of the same value at another pH is not mistaken
for it.

**Nothing was multiplied, moved or manufactured.** 32.0 was already a row of
kcat's own frontier; the same guarantee holds in the metric by construction:
`unassessable` rows are never chosen, and re-selection only ever copies a
measured row.

**The two-direction concern resolves to a refusal, not a guess.** ADR 0171
drew the "neither value is privileged" rule for organisms; this ADR extends
it to conditions. When both frontiers can satisfy each other, the finding
stays and says why — consistent with the architecture's rule that an
invisible scientific decision is the worst one.

**Buffer stays permanently non-actionable.** The frontier carries no buffer
axis, so no `assay_window` can name one and no search could satisfy it; a
buffer gap remains a finding. ADR 0171's table now says so explicitly.

**The metric reuses the judge, so mutation-guarding it is cheap.** A
boundary flip, a both-can-move emission and a silenced re-selection each
fail a dedicated test; each was planted, caught and restored with the file
checksums matching.

`max_rounds`, non-convergence reporting and the rest of ADR 0171's contract
are unchanged. An endlessly narrowing window would still run forever and be
reported, not corrected.